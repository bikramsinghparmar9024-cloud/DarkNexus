"""
Tests for the analysis chain: speech act, entity extraction, geography,
and the threat scoring that depends on all three.

These lock in behaviour that was measured and corrected by hand, so a future
change cannot silently undo it.
"""

import pytest

from tests.conftest import (
    DEALER_OFFER, NEWS_REPORT, WIKI_ARTICLE, PRECURSOR_OFFER, BENIGN_TEXT,
)


# ── Speech act ───────────────────────────────────────────────────────

class TestSpeechAct:
    """
    A dealer's offer, a buyer's request and a news report share the same
    nouns. Only the speech act separates them, and getting this wrong means
    either flagging journalists or missing traffickers.
    """

    @pytest.mark.parametrize("text,expected_act", [
        (DEALER_OFFER, "OFFER"),
        (PRECURSOR_OFFER, "OFFER"),
        ("Grade-A heroin available for sale, 5kg bulk ready, send escrow payment", "OFFER"),
        ("Looking for chitta near Amritsar, anyone selling? How much for 10g?", "DEMAND"),
        (NEWS_REPORT, "REPORT"),
        (WIKI_ARTICLE, "REPORT"),
        (BENIGN_TEXT, "CHATTER"),
    ])
    def test_act_classification(self, text, expected_act):
        from ai.speech_act import detect_speech_act
        assert detect_speech_act(text)["act"] == expected_act

    def test_past_tense_offer_is_not_a_report(self):
        """
        Regression: past-tense verbs alone once made a live offer look like
        journalism. A reporting marker is now required.
        """
        from ai.speech_act import detect_speech_act
        text = ("Maal was dropped at the usual spot last night. "
                "Next consignment ready tomorrow, send payment.")
        result = detect_speech_act(text)
        assert result["act"] == "OFFER"
        assert result["is_operational"] is True

    def test_verdict_carries_its_evidence(self):
        """Every verdict must be explainable - this is court-bound evidence."""
        from ai.speech_act import detect_speech_act
        result = detect_speech_act(NEWS_REPORT)
        assert result["reason"]
        assert "police" in result["evidence"]["reporting_markers"]

    def test_empty_text_is_safe(self):
        from ai.speech_act import detect_speech_act
        assert detect_speech_act("")["act"] == "UNKNOWN"


# ── Entity extraction ────────────────────────────────────────────────

class TestEntityExtraction:

    def test_extracts_identifiers_from_a_real_offer(self):
        from ai.entity_extractor import entity_extractor
        e = entity_extractor.extract(DEALER_OFFER)

        assert "Heroin / Chitta" in e["drugs"]
        assert "Attari" in e["locations"]
        assert "9814098211" in e["phones"]
        assert "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa" in e["crypto_wallets"]["btc"]

    def test_recognises_precursor_chemicals(self):
        """
        The extractor knows 'acetic anhydride' is a precursor even though the
        threat scorer's keyword list does not. That mismatch is problem #16.
        """
        from ai.entity_extractor import entity_extractor
        assert "Precursor Chemicals" in entity_extractor.extract(PRECURSOR_OFFER)["drugs"]

    def test_benign_text_yields_nothing(self):
        from ai.entity_extractor import entity_extractor
        e = entity_extractor.extract(BENIGN_TEXT)
        assert e["drugs"] == []
        assert e["phones"] == []


# ── Geography ────────────────────────────────────────────────────────

class TestGeoResolution:

    def test_resolves_a_named_border_town(self):
        from ai.geo_resolver import resolve_location
        r = resolve_location("Attari")
        assert r["distance_to_border_km"] == 2.5
        assert r["in_critical_border_corridor"] is True

    def test_resolves_raw_coordinates_from_a_photograph(self):
        from ai.geo_resolver import resolve_coordinates
        r = resolve_coordinates(31.6026, 74.6033)
        assert r["nearest_known_location"] == "Attari"
        assert r["in_critical_border_corridor"] is True

    def test_distant_coordinates_are_not_flagged(self):
        from ai.geo_resolver import resolve_coordinates
        r = resolve_coordinates(28.6139, 77.2090)  # Delhi
        assert r["in_punjab_region"] is False
        assert r["in_critical_border_corridor"] is False

    def test_unknown_place_returns_none(self):
        from ai.geo_resolver import resolve_location
        assert resolve_location("Atlantis") is None


# ── Threat scoring end to end ────────────────────────────────────────

class TestThreatScoring:

    def test_dealer_offer_stays_severe(self):
        from ai.enrichment import analyze_text
        a = analyze_text(DEALER_OFFER)
        assert a["threat"]["threat_level"] == "SEVERE"
        assert a["threat"]["speech_act"]["act"] == "OFFER"

    @pytest.mark.parametrize("text", [NEWS_REPORT, WIKI_ARTICLE])
    def test_reporting_is_downgraded(self, text):
        """
        Regression: both of these once scored SEVERE, identically to a real
        trafficking offer, because they contain the same keywords.
        """
        from ai.enrichment import analyze_text
        a = analyze_text(text)
        threat = a["threat"]

        ladder = ["LOW", "MEDIUM", "HIGH", "SEVERE"]
        assert threat["threat_level"] in ("LOW", "MEDIUM")
        assert threat["semantic_adjustment"]["direction"] == "DOWNGRADE"
        # Assert the property, not a fixed starting band: what matters is that
        # the speech act lowered whatever the keywords produced.
        assert ladder.index(threat["threat_level"]) < ladder.index(threat["rule_threat_level"])

    def test_rule_score_is_preserved_after_adjustment(self):
        """An analyst must always be able to see the unadjusted score."""
        from ai.enrichment import analyze_text
        threat = analyze_text(NEWS_REPORT)["threat"]
        assert threat["rule_threat_level"] != threat["threat_level"]
        assert threat["semantic_adjustment"]["reason"]

    def test_border_escalation_skipped_for_reporting(self):
        """
        A news story naming a border town must not be escalated by geography
        after the speech act identified it as reporting.
        """
        from ai.enrichment import analyze_text
        a = analyze_text(NEWS_REPORT)
        assert "Attari" in [m["location"] for m in a["geo_markers"]]
        assert a["threat"].get("border_escalated") is False

    def test_benign_text_stays_low(self):
        from ai.enrichment import analyze_text
        assert analyze_text(BENIGN_TEXT)["threat"]["threat_level"] == "LOW"

    def test_empty_text_is_safe(self):
        from ai.enrichment import analyze_text
        a = analyze_text("")
        assert a["threat"]["threat_level"] == "LOW"
        assert a["entities"]["drugs"] == []

    def test_analysis_shape_is_stable(self):
        """
        Both ingest paths and every reader depend on these keys. Renaming one
        is the class of change that quietly broke this system before.
        """
        from ai.enrichment import analyze_text, ANALYSIS_SCHEMA_VERSION
        a = analyze_text(DEALER_OFFER)
        for key in ("schema_version", "analyzed_at", "normalized_text",
                    "detected_slang", "entities", "threat", "geo",
                    "geo_markers", "border_alert", "speech_act"):
            assert key in a, f"analysis block lost key '{key}'"
        assert a["schema_version"] == ANALYSIS_SCHEMA_VERSION


# ── Known-failing: documented defects ────────────────────────────────

class TestNarcoticsGate:
    """
    Contextual terms - border, delivery, bulk, escrow, crypto - describe
    logistics, not drugs. Before the gate existed, a tractor-parts advert
    shipping to Fazilka scored SEVERE, because "border" alone is worth 30
    points and the border rule then escalated it. Flooding investigators with
    that kind of noise is its own failure mode.
    """

    @pytest.mark.parametrize("text", [
        "Tractor spare parts available in bulk. Overnight transit to Fazilka godowns, contact me for rates.",
        "Rooms available near Attari border, book now, contact us for rates.",
        "Courier delivery service to Amritsar and Attari, bulk rates available.",
    ])
    def test_commerce_near_the_border_is_not_a_drug_threat(self, text):
        from ai.enrichment import analyze_text
        threat = analyze_text(text)["threat"]
        assert threat["narcotics_evidence"] is False
        assert threat["threat_level"] == "LOW"
        assert threat["suppressed_reason"]

    def test_suppression_does_not_apply_when_drugs_are_present(self):
        from ai.enrichment import analyze_text
        threat = analyze_text(DEALER_OFFER)["threat"]
        assert threat["narcotics_evidence"] is True
        assert threat["suppressed_reason"] is None

    def test_precursor_chemical_counts_as_narcotics_evidence(self):
        """
        Regression for problem #15. The scorer's keyword list has no entry for
        'acetic anhydride', so the rule score is zero - but the extractor
        recognises it as a precursor, and the speech act shows a live offer.
        Together those must still produce a real threat level.
        """
        from ai.enrichment import analyze_text
        a = analyze_text(PRECURSOR_OFFER)
        threat = a["threat"]

        assert "Precursor Chemicals" in a["entities"]["drugs"]
        assert threat["narcotics_evidence"] is True
        assert threat["threat_level"] != "LOW"

        # The category scorer now recognises the precursor directly, rather
        # than relying on the speech-act upgrade to rescue a zero score.
        assert threat["rule_threat_level"] != "LOW"
        assert threat["score_categories"]["substance"]["score"] > 0
        assert "Precursor Chemicals" in threat["score_categories"]["substance"]["signals"]


class TestScoreRanking:
    """
    Problem #14. Scores used to saturate: three or four keywords reached the
    100 cap, so every serious record looked identical. Worse, the ordering was
    inverted - a passing mention of chitta near the border scored 55 while a
    500g offer with a dead drop and BTC escrow scored 50.
    """

    def test_distinct_offers_get_distinguishable_scores(self):
        from ai.enrichment import analyze_text
        small = analyze_text("chitta available near border, contact me")
        large = analyze_text(
            "5kg bulk chitta wholesale, border transit, dead drop, "
            "escrow BTC, precursor supply also available, contact me"
        )
        assert large["threat"]["risk_score"] > small["threat"]["risk_score"]


class TestScoreCategories:
    """
    The scorer asks five separate questions and caps each one, so breadth of
    evidence outranks repetition of the same idea.
    """

    def test_severity_ordering_is_monotonic(self):
        """
        The property that makes triage possible. Previously a passing mention
        scored 55 while a 500g offer with dead drop and BTC escrow scored 50.
        """
        from ai.enrichment import analyze_text

        ladder = [
            "the weather in Ludhiana is pleasant today",
            "someone was talking about chitta near the border",
            "chitta available 2g, contact me, Amritsar",
            "500g chitta available, dead drop Majitha, BTC escrow",
            "5kg bulk chitta wholesale, border transit via drone, dead drop, "
            "BTC escrow, precursor acetic anhydride also available, rate list",
        ]
        scores = [analyze_text(t)["threat"]["risk_score"] for t in ladder]

        assert scores == sorted(scores), f"severity ordering broken: {scores}"
        assert len(set(scores)) == len(scores), f"scores not distinguishable: {scores}"

    def test_synonyms_do_not_double_count(self):
        """
        'chitta' and 'heroin' in one message describe one substance. Summing
        both was a large part of why scores saturated.
        """
        from ai.enrichment import analyze_text
        one = analyze_text("chitta available, contact me")["threat"]
        both = analyze_text("chitta heroin smack available, contact me")["threat"]

        assert both["score_categories"]["substance"]["score"] <= \
               one["score_categories"]["substance"]["score"] + 3

    def test_breadth_outranks_repetition(self):
        from ai.enrichment import analyze_text
        repeated = analyze_text("chitta chitta chitta heroin smack powder available")
        varied = analyze_text("chitta available 1kg, dead drop, BTC escrow, rate list")
        assert varied["threat"]["risk_score"] > repeated["threat"]["risk_score"]

    def test_quantity_moves_the_score(self):
        from ai.enrichment import analyze_text
        small = analyze_text("chitta available 2g, contact me")["threat"]
        large = analyze_text("chitta available 5kg, contact me")["threat"]
        assert large["risk_score"] > small["risk_score"]

    def test_no_category_can_exceed_its_cap(self):
        from ai.threat_scoring import score_threat, CATEGORY_CAPS
        from ai.entity_extractor import entity_extractor

        text = ("chitta heroin smack opium tramadol meth precursor acetic anhydride "
                "5kg 10kg bulk wholesale container drone dead drop courier postal "
                "transit escrow hawala btc xmr upi barcode rate list gps coordinates")
        result = score_threat(text, entity_extractor.extract(text), [])

        for name, category in result["categories"].items():
            assert category["score"] <= CATEGORY_CAPS[name]
        assert result["risk_score"] <= 100

    def test_score_names_its_contributors(self):
        """A score an analyst cannot inspect is not one they can defend."""
        from ai.enrichment import analyze_text
        threat = analyze_text("500g chitta, dead drop Majitha, BTC escrow")["threat"]

        assert "substance" in threat["categories_triggered"]
        assert threat["score_explanation"].startswith("Score ")
        assert "Heroin / Chitta" in threat["score_categories"]["substance"]["signals"]


class TestBorderEscalation:

    def test_border_raises_an_actual_offer(self):
        from ai.enrichment import analyze_text
        threat = analyze_text(
            "Veere Attari border te chitta ready aa, 100g, barcode bhejo")["threat"]
        assert threat["border_escalated"] is True
        assert threat["threat_level"] == "SEVERE"

    def test_border_does_not_raise_a_passing_mention(self):
        """
        CHATTER means no speech-act markers were found. Geography alone is too
        weak to push such a record to the top band.
        """
        from ai.enrichment import analyze_text
        threat = analyze_text("someone was talking about chitta near the border")["threat"]
        assert threat["speech_act"]["act"] == "CHATTER"
        assert threat["border_escalated"] is False
        assert threat["threat_level"] != "SEVERE"

    def test_border_does_not_raise_a_news_report(self):
        from ai.enrichment import analyze_text
        threat = analyze_text(
            "Punjab Police seized 2 kg of chitta near Attari yesterday. "
            "Three men were arrested.")["threat"]
        assert threat["border_escalated"] is False
        assert threat["threat_level"] == "LOW"


class TestLongDocumentHandling:
    """
    Scraped pages are tens of thousands of characters and accumulate
    incidental markers of every kind. Judging them by share-of-total made a
    decisive reading look uncertain purely because the document was long.
    """

    def test_dominance_is_stable_across_document_length(self):
        from ai.speech_act import detect_speech_act

        short = "Punjab Police seized 2 kg of chitta near Attari. Three men were arrested."
        padded = short + " " + ("The consignment was recovered and the accused "
                                "were produced in court. " * 200)

        short_result = detect_speech_act(short)
        long_result = detect_speech_act(padded)

        assert short_result["act"] == long_result["act"] == "REPORT"
        # Both readings are decisive even though the long one has lower share.
        assert short_result["is_decisive"] is True
        assert long_result["is_decisive"] is True

    def test_long_reference_page_is_not_an_operational_threat(self):
        """
        A full encyclopedia article on darknet markets scores highly on
        keywords - it discusses every substance, payment method and tactic -
        but it is reference material, not an offer.
        """
        from ai.enrichment import analyze_text

        article = (
            "Darknet market. Police seized large quantities of heroin and "
            "arrested several vendors. According to officials, the marketplace "
            "offered chitta, opium and methamphetamine with escrow payment in "
            "bitcoin. Authorities reported that 5kg consignments were shipped "
            "by courier across the border. " * 40
        )
        threat = analyze_text(article)["threat"]

        assert threat["speech_act"]["act"] == "REPORT"
        assert threat["semantic_adjustment"]["direction"] == "DOWNGRADE"
        assert threat["threat_level"] in ("LOW", "MEDIUM")
