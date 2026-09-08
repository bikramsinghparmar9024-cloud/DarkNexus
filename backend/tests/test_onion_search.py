"""
Multi-engine hidden-service discovery.

The safety property under test matters more than the feature. Only Ahmia
filters child sexual abuse material from its index; the other fifteen engines
filter nothing. This system stores whatever it fetches, and the surveillance
scheduler collects from ACTIVE targets unattended - so registering unfiltered
search output as ACTIVE would eventually pull illegal imagery into an evidence
database with no person having chosen to fetch it.

Addresses from non-filtering engines must therefore be held as PENDING_REVIEW,
which the scheduler does not select.
"""

import pytest

from scrapers.dark_web.onion_search import (
    OnionSearch, ENGINES, extract_onion_links, ONION_V3_RE,
)

A = "juhanurmihxlp77nkq76byazcldy2hlmovfu2epvl5ankdibsot4csyd.onion"
B = "3bbad7fauom4d6sgppalyqddsqbf5u5p56b5k5uk2zxsy3d6ey2jobad.onion"


class TestEngineRegistry:

    def test_every_engine_declares_whether_it_filters_abuse(self):
        for engine in ENGINES:
            assert isinstance(engine["filters_abuse"], bool), engine["name"]

    def test_only_ahmia_is_marked_as_filtering(self):
        """
        If another engine is ever marked as filtering, that claim must be
        verifiable - it decides whether its results can be collected unattended.
        """
        filtering = [e["name"] for e in ENGINES if e["filters_abuse"]]
        assert filtering == ["Ahmia"]

    def test_every_engine_url_carries_a_query_placeholder(self):
        for engine in ENGINES:
            assert "{query}" in engine["url"], engine["name"]

    def test_every_engine_is_a_valid_v3_service(self):
        for engine in ENGINES:
            assert ONION_V3_RE.search(engine["url"]), engine["name"]


class TestLinkExtraction:

    def test_addresses_are_found_in_anchors_and_text(self):
        html = f"<a href='http://{A}/x'>one</a> and bare http://{B}"
        found = extract_onion_links(html)
        assert A in found and B in found

    def test_the_engine_is_not_reported_as_its_own_result(self):
        html = f"<a href='http://{A}/search'>self</a><a href='http://{B}'>hit</a>"
        found = extract_onion_links(html, engine_host=A)
        assert A not in found
        assert B in found

    def test_duplicates_are_collapsed(self):
        html = f"http://{A} http://{A} <a href='http://{A}'>x</a>"
        assert extract_onion_links(html) == [A]

    def test_empty_input_is_safe(self):
        assert extract_onion_links("") == []
        assert extract_onion_links(None) == []


class TestSafetyDefaults:

    async def test_unfiltered_results_are_held_for_review(self, db):
        from sqlalchemy import select
        from database.postgres import Target

        outcome = await OnionSearch().register_targets(
            [{"url": f"http://{B}", "engines": ["Tor66"],
              "from_filtering_engine": False}], query="chitta")

        assert outcome["pending_review_count"] == 1
        assert outcome["activated_count"] == 0
        target = (await db.execute(select(Target))).scalars().first()
        assert target.status == "PENDING_REVIEW"

    async def test_pending_targets_are_invisible_to_the_scheduler(self, db):
        """
        The scheduler selects only ACTIVE targets, which is what makes
        PENDING_REVIEW an actual safeguard rather than a label.
        """
        from sqlalchemy import select
        from database.postgres import Target

        await OnionSearch().register_targets(
            [{"url": f"http://{B}", "engines": ["Tor66"],
              "from_filtering_engine": False}], query="chitta")

        due = (await db.execute(
            select(Target).where(Target.status == "ACTIVE"))).scalars().all()
        assert due == []

    async def test_filtered_results_still_default_to_review(self, db):
        """Auto-activation is opt-in even for the one filtering engine."""
        outcome = await OnionSearch().register_targets(
            [{"url": f"http://{A}", "engines": ["Ahmia"],
              "from_filtering_engine": True}], query="chitta")
        assert outcome["pending_review_count"] == 1

    async def test_opting_in_activates_only_filtered_results(self, db):
        from sqlalchemy import select
        from database.postgres import Target

        outcome = await OnionSearch().register_targets(
            [{"url": f"http://{A}", "engines": ["Ahmia"],
              "from_filtering_engine": True},
             {"url": f"http://{B}", "engines": ["Tor66"],
              "from_filtering_engine": False}],
            query="chitta", auto_activate_filtered=True)

        assert outcome["activated_count"] == 1
        assert outcome["pending_review_count"] == 1
        active = (await db.execute(
            select(Target).where(Target.status == "ACTIVE"))).scalars().all()
        assert len(active) == 1
        assert A in active[0].identifier


class TestSearchGuards:

    async def test_an_empty_query_is_refused(self):
        result = await OnionSearch().search("  ")
        assert result["status"] == "INVALID"

    async def test_search_requires_tor(self, monkeypatch):
        """Every engine is a hidden service; without Tor none are reachable."""
        searcher = OnionSearch()
        monkeypatch.setattr(searcher.settings, "TOR_ENABLED", False)
        result = await searcher.search("chitta")
        assert result["status"] == "TOR_DISABLED"
        assert "Tor" in result["message"]

    async def test_an_unknown_engine_name_is_reported(self, monkeypatch):
        searcher = OnionSearch()
        monkeypatch.setattr(searcher.settings, "TOR_ENABLED", True)
        result = await searcher.search("chitta", engines=["NotAnEngine"])
        assert result["status"] == "INVALID"
