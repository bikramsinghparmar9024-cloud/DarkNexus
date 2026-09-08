"""
Tests for actor dossiers, network centrality, and the tiered drug lexicon.

The lexicon tests are regressions for a defect with real consequences: the
word "post" identified opium, which meant the narcotics gate in
ai/enrichment.py - the check that decides whether a record is drug
intelligence at all - could be disarmed by an ordinary English sentence.

The dossier tests are regressions for the opposite failure: an over-eager
merge that turned a six-person network into one actor by treating everyone
named in a conversation as the same person.
"""

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from ai.entity_extractor import detect_drugs, entity_extractor
from ai.actor_dossier import (
    DossierBuilder, owned_identifiers, mentioned_handles,
)
from ai.network_analysis import NetworkAnalyzer, MIN_NODES_FOR_CENTRALITY


# ── Tiered lexicon ───────────────────────────────────────────────────

class TestDrugLexiconTiers:

    @pytest.mark.parametrize("text", [
        "I saw a white car parked near the post office.",
        "Please post your comment below.",
        "The ice cream was crystal clear.",
        "The powder coating on the white fence needs work.",
        "Grade-A customer service, would recommend.",
    ])
    def test_everyday_english_is_not_narcotics(self, text):
        """
        Ordinary sentences must not identify a controlled substance.

        This is not just a noisy label. ai/enrichment.py decides whether a
        record counts as drug intelligence by asking whether this extraction
        found anything, so a false hit here disarms the narcotics gate and
        unlocks border escalation on a sentence about a fence.
        """
        assert detect_drugs(text)["categories"] == []

    @pytest.mark.parametrize("text,expected", [
        ("Grade-A chitta 500g available", "Heroin / Chitta"),
        ("Police seized 2kg heroin near Attari", "Heroin / Chitta"),
        ("bhukki consignment intercepted", "Opium / Bhukki"),
        ("tramadol strips wholesale", "Tramadol / Synthetic Opioids"),
        ("acetic anhydride shipment", "Precursor Chemicals"),
    ])
    def test_specific_terms_stand_alone(self, text, expected):
        assert expected in detect_drugs(text)["categories"]

    @pytest.mark.parametrize("text,expected", [
        ("500g of white available, escrow only", "Heroin / Chitta"),
        ("ice and crystal available in bulk, wholesale rates",
         "Methamphetamine / Ice"),
        ("2kg powder for sale, courier delivery", "Heroin / Chitta"),
    ])
    def test_street_terms_count_with_transaction_context(self, text, expected):
        assert expected in detect_drugs(text)["categories"]

    def test_the_basis_of_each_finding_is_recorded(self):
        """A reviewer must be able to tell 'chitta' from 'white'."""
        specific = detect_drugs("chitta available")
        contextual = detect_drugs("500g of white available, escrow")
        assert specific["basis"]["Heroin / Chitta"]["tier"] == "SPECIFIC"
        assert contextual["basis"]["Heroin / Chitta"]["tier"] == "CONTEXTUAL"

    def test_rejected_terms_are_explained_not_silently_dropped(self):
        basis = detect_drugs("the white fence and the post office")["basis"]
        assert "_rejected" in basis
        assert "Heroin / Chitta" in basis["_rejected"]

    def test_extractor_exposes_the_basis(self):
        entities = entity_extractor.extract("Grade-A chitta 500g available")
        assert entities["drugs"] == ["Heroin / Chitta"]
        assert entities["drug_basis"]["Heroin / Chitta"]["tier"] == "SPECIFIC"


# ── Ownership vs mention ─────────────────────────────────────────────

def _analysis(handles=(), wallets=(), phones=()):
    return {"entities": {
        "handles": list(handles), "phones": list(phones),
        "crypto_wallets": {"btc": list(wallets)},
        "upi_ids": [], "pgp_fingerprints": [], "drugs": [], "locations": [],
    }, "geo_markers": []}


class TestIdentityVersusRelationship:
    """
    Whom you message is not who you are.

    Merging identifiers because they appeared in one message collapsed a
    six-actor network into a single actor: everyone in a conversation lands in
    the same connected component, so the graph had one node and no structure.
    """

    def test_wallets_and_phones_belong_to_the_sender(self):
        analysis = _analysis(wallets=["bc1qtest"], phones=["9876543210"])
        owned = owned_identifiers(analysis)
        assert ("wallet", "bc1qtest") in owned
        assert ("phone", "9876543210") in owned

    def test_handles_are_never_treated_as_owned(self):
        analysis = _analysis(handles=["@someone_else"])
        assert owned_identifiers(analysis) == []

    def test_mentioned_handles_exclude_the_author(self):
        analysis = _analysis(handles=["@broker_raja", "@supplier_one"])
        mentioned = mentioned_handles(analysis, "@supplier_one")
        assert ("handle", "@broker_raja") in mentioned
        assert ("handle", "@supplier_one") not in mentioned

    def test_author_handle_is_normalised(self):
        analysis = _analysis(handles=["@Broker_Raja"])
        assert mentioned_handles(analysis, "@BROKER_RAJA") == []


# ── Dossier construction ─────────────────────────────────────────────

def _record(record_id, author, source="TELEGRAM", level="MEDIUM", hours_ago=0):
    return SimpleNamespace(
        id=record_id, author_or_handle=author, source_type=source,
        source_url=f"https://t.me/x/{record_id}", threat_level=level,
        created_at=datetime.utcnow() - timedelta(hours=hours_ago),
        published_at=None,
    )


class TestDossierBuilding:

    def test_a_conversation_does_not_become_one_person(self):
        builder = DossierBuilder()
        records = [_record(1, "@a"), _record(2, "@b"), _record(3, "@c")]
        analyses = {
            1: _analysis(handles=["@b"]),
            2: _analysis(handles=["@c"]),
            3: _analysis(handles=["@a"]),
        }
        profiles, ownership, interactions = builder._profile_identifiers(
            records, analyses, {})
        groups = builder._group(profiles, ownership)

        assert len(groups) == 3, "three correspondents are three actors"
        assert len(interactions) == 3

    def test_a_wallet_in_your_own_message_merges_with_you(self):
        builder = DossierBuilder()
        records = [_record(1, "@vendor")]
        analyses = {1: _analysis(wallets=["bc1qvendor"])}
        profiles, ownership, _ = builder._profile_identifiers(records, analyses, {})
        groups = builder._group(profiles, ownership)

        assert len(groups) == 1
        assert len(groups[0]) == 2

    def test_a_wallet_reused_under_two_handles_joins_them(self):
        """This is the alias chain the merge exists to find."""
        builder = DossierBuilder()
        records = [_record(1, "@alias_one"), _record(2, "@alias_two")]
        analyses = {
            1: _analysis(wallets=["bc1qshared"]),
            2: _analysis(wallets=["bc1qshared"]),
        }
        profiles, ownership, _ = builder._profile_identifiers(records, analyses, {})
        groups = builder._group(profiles, ownership)

        assert len(groups) == 1, "one wallet under two handles is one actor"
        assert len(groups[0]) == 3

    def test_a_single_record_join_is_graded_weak(self):
        builder = DossierBuilder()
        records = [_record(1, "@vendor")]
        analyses = {1: _analysis(wallets=["bc1qvendor"])}
        profiles, ownership, _ = builder._profile_identifiers(records, analyses, {})
        groups = builder._group(profiles, ownership)

        confidence = builder._join_confidence(groups[0])
        assert confidence["grade"] == "WEAK"
        assert "single record" in confidence["note"]

    def test_role_inference_states_what_it_rests_on(self):
        from collections import Counter
        builder = DossierBuilder()
        role = builder._role(Counter({"OFFER": 4, "REPORT": 1}))
        assert role["role"] == "SUPPLIER"
        assert "4 of 5" in role["basis"]

    def test_no_dominant_pattern_is_reported_as_mixed(self):
        from collections import Counter
        builder = DossierBuilder()
        role = builder._role(Counter({"OFFER": 2, "DEMAND": 2}))
        assert role["role"] == "MIXED"


# ── Centrality ───────────────────────────────────────────────────────

class TestNetworkAnalysis:

    def test_interpretation_names_the_disruption_target(self):
        analyzer = NetworkAnalyzer()
        text = analyzer._interpret(betweenness=0.6, degree=4, is_cut=True)
        assert "splits the observed network" in text

    def test_a_hub_is_distinguished_from_a_bridge(self):
        """
        Volume and position are different things. A retail seller with many
        contacts who all know each other is not a broker, and arresting him
        does not disconnect anything.
        """
        analyzer = NetworkAnalyzer()
        text = analyzer._interpret(betweenness=0.01, degree=8, is_cut=False)
        assert "not a bridge" in text

    def test_peripheral_actors_are_described_as_such(self):
        analyzer = NetworkAnalyzer()
        assert "peripheral" in analyzer._interpret(0.0, 1, False)

    async def test_small_graphs_are_refused_not_ranked(self, db):
        """
        In a four-node graph everyone is central. Publishing a ranking would
        imply a precision the data cannot support.
        """
        from ai.enrichment import store_intelligence

        for i in range(2):
            await store_intelligence(
                source_type="TELEGRAM", source_url=f"https://t.me/x/{i}",
                raw_content="Chitta available, escrow only.",
                author=f"@vendor_{i}", session=db)

        result = await NetworkAnalyzer().analyse()
        assert result["status"] == "INSUFFICIENT_DATA"
        assert result["brokers"] == []
        assert str(MIN_NODES_FOR_CENTRALITY) in result["message"]


# ── Regression: identifiers mined out of undecoded binary ────────────

class TestIdentifierFabricationFromBinary:
    """
    A page served in an encoding the client never negotiated arrived as 360 KB
    of binary and was stored as text. The identifier patterns then mined it:
    twelve UPI IDs and six Telegram handles that never existed, each promoted
    to an actor with its own dossier. Three separate guards now stop that.
    """

    BINARY_JUNK = "R5z\x01cVQ\x17\x14'@.\x1c@ETyD@UFgDF UR@Zb 9P@ec q9ik@BFd"

    def test_binary_yields_no_handles(self):
        from ai.entity_extractor import TELEGRAM_HANDLE_REGEX
        assert TELEGRAM_HANDLE_REGEX.findall(self.BINARY_JUNK) == []

    def test_binary_yields_no_upi_ids(self):
        from ai.entity_extractor import UPI_REGEX
        assert UPI_REGEX.findall(self.BINARY_JUNK) == []

    def test_email_addresses_are_not_payment_identifiers(self):
        from ai.entity_extractor import UPI_REGEX
        assert UPI_REGEX.findall("write to press@thetribune.com") == []

    @pytest.mark.parametrize("text,expected", [
        ("pay 9876543210@ybl", ["9876543210@ybl"]),
        ("raja.singh@paytm please", ["raja.singh@paytm"]),
        ("user@okhdfcbank", ["user@okhdfcbank"]),
    ])
    def test_real_upi_addresses_still_extracted(self, text, expected):
        from ai.entity_extractor import UPI_REGEX
        assert UPI_REGEX.findall(text) == expected

    def test_genuine_handles_still_extracted(self):
        from ai.entity_extractor import TELEGRAM_HANDLE_REGEX
        assert TELEGRAM_HANDLE_REGEX.findall(
            "contact @jagga_drops today") == ["jagga_drops"]

    def test_handle_must_start_with_a_letter(self):
        from ai.entity_extractor import TELEGRAM_HANDLE_REGEX
        assert TELEGRAM_HANDLE_REGEX.findall("@12345abc") == []


class TestUndecodableContent:
    """Undecodable bytes are a collection failure, not evidence."""

    def test_binary_is_rejected_as_text(self):
        from scrapers.content_extraction import is_decoded_text
        assert is_decoded_text("\x01\x02\x03\ufffd" * 100) is False

    def test_ordinary_html_is_accepted(self):
        from scrapers.content_extraction import is_decoded_text
        assert is_decoded_text("<html><body>Chitta seized at Attari</body></html>")

    def test_extraction_refuses_undecodable_pages(self):
        from scrapers.content_extraction import extract_readable_text
        result = extract_readable_text("\x00\x01\ufffd\x02" * 500,
                                       url="https://example.test/x")
        assert result["strategy"] == "undecodable"
        assert result["text"] == ""

    def test_a_little_binary_does_not_reject_a_real_page(self):
        """Stray control characters occur in legitimate pages."""
        from scrapers.content_extraction import is_decoded_text
        assert is_decoded_text("Chitta seized near Attari. " * 200 + "\x01\x02")
