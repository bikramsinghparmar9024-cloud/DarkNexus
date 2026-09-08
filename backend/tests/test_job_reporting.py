"""
A job must report what actually happened.

Jobs were marked COMPLETED whenever the worker did not raise, with
`items_scraped` hardcoded to 1. Because the scrapers signal failure by
*returning* {"status": "FAILED"} rather than raising, an .onion fetch
attempted with no Tor daemon was recorded as a completed job that collected
one item, while the database received nothing. The jobs table - the one place
an operator looks to confirm collection worked - was reporting success for
collection that never happened.
"""

import pytest

from routes.scraper_routes import _interpret_result


class TestFailuresAreNotReportedAsSuccess:

    def test_a_failed_onion_fetch_is_a_failed_job(self):
        result = {"status": "FAILED", "url": "http://x.onion",
                  "error": "SOCKS connection refused",
                  "note": "Tor daemon must be active on socks port 9050"}
        status, items, error = _interpret_result(result, "scrape")
        assert status == "FAILED"
        assert items == 0
        assert "SOCKS" in error

    def test_a_bot_challenge_is_a_failed_job(self):
        status, items, _ = _interpret_result(
            {"status": "BLOCKED", "error": "Bot challenge detected"}, "scrape")
        assert (status, items) == ("FAILED", 0)

    def test_an_error_key_alone_marks_failure(self):
        """Some paths return an error without a status field."""
        status, items, error = _interpret_result(
            {"error": "Unknown scheme for proxy URL socks4://..."}, "scrape")
        assert (status, items) == ("FAILED", 0)
        assert "socks4" in error


class TestSuccessesAreCountedHonestly:

    def test_a_saved_record_counts_as_one(self):
        assert _interpret_result({"status": "SAVED", "id": 4}, "scrape") == (
            "COMPLETED", 1, None)

    def test_a_duplicate_collects_nothing_new(self):
        """Re-collection is a successful visit, but not new evidence."""
        status, items, _ = _interpret_result({"status": "DUPLICATE"}, "scrape")
        assert (status, items) == ("COMPLETED", 0)


class TestCrawlCounting:

    def test_only_stored_pages_are_counted(self):
        """`len(result)` counted attempts, including the ones that failed."""
        crawl = [{"status": "SAVED"}, {"status": "FAILED", "error": "timeout"},
                 {"status": "SAVED"}]
        status, items, error = _interpret_result(crawl, "crawl")
        assert (status, items) == ("COMPLETED", 2)
        assert "1 of 3" in error

    def test_a_crawl_that_stored_nothing_is_a_failure(self):
        status, items, _ = _interpret_result(
            [{"status": "FAILED"}, {"status": "BLOCKED"}], "crawl")
        assert (status, items) == ("FAILED", 0)

    def test_an_empty_crawl_is_not_reported_as_success(self):
        assert _interpret_result([], "crawl")[0] == "FAILED"


class TestRevisitIsNotAFailure:
    """
    A source revisited before it publishes anything new returns DUPLICATE.
    That is the expected outcome of most polls, and it was being recorded as
    a failure - so a healthy target accumulated consecutive failures on every
    scheduler tick and was auto-paused once it hit the threshold. The better
    the source behaved, the sooner collection from it stopped.
    """

    @staticmethod
    def _patch_scraper(monkeypatch, result):
        """Replace the surface scraper the scheduler builds with a stub."""
        import scrapers.surface_web.scraper as module

        class Stub:
            active_target_id = None
            async def scrape(self, identifier):
                return result

        monkeypatch.setattr(module, "SurfaceWebScraper", Stub)

    @staticmethod
    def _target(**kwargs):
        from database.postgres import Target
        return Target(identifier="https://example.test/listing",
                      source_type="SURFACE_WEB", status="ACTIVE",
                      scan_interval_minutes=60, **kwargs)

    async def test_a_duplicate_visit_clears_the_failure_count(self, db, monkeypatch):
        from scheduler import intel_scheduler

        self._patch_scraper(monkeypatch, {"status": "DUPLICATE", "record_id": 1})
        target = self._target(consecutive_failures=2, last_error="status=DUPLICATE")

        ok = await intel_scheduler._collect_target(target)

        assert ok is True, "a successful check must not count as a failure"
        assert target.consecutive_failures == 0
        assert target.last_error is None

    async def test_a_duplicate_adds_no_records_to_the_total(self, db, monkeypatch):
        from scheduler import intel_scheduler

        self._patch_scraper(monkeypatch, {"status": "DUPLICATE"})
        target = self._target(total_records_collected=7)

        await intel_scheduler._collect_target(target)

        assert target.total_records_collected == 7, (
            "nothing new was collected, so the count must not move")

    async def test_a_saved_visit_still_counts_records(self, db, monkeypatch):
        from scheduler import intel_scheduler

        self._patch_scraper(monkeypatch, {"status": "SAVED", "record_id": 9})
        target = self._target(total_records_collected=7)

        await intel_scheduler._collect_target(target)

        assert target.total_records_collected == 8

    async def test_a_real_failure_still_counts(self, db, monkeypatch):
        from scheduler import intel_scheduler

        self._patch_scraper(
            monkeypatch,
            {"status": "FAILED", "error": "All connection attempts failed"})
        target = self._target()

        ok = await intel_scheduler._collect_target(target)

        assert ok is False
        assert "connection attempts failed" in target.last_error
