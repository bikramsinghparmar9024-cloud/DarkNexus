"""
Tests for the local semantic correlation layer.

Two of these are regression tests for defects that reached stored evidence:
an ISBN extracted as a suspect's phone number, and two collections of one web
page reported as a network link between sources. Both produced confident,
plausible-looking intelligence that was simply untrue, which is the failure
mode this system can least afford.
"""

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from ai.entity_extractor import PHONE_REGEX
from ai.semantic_correlation import (
    SemanticCorrelator, cosine_matrix, MIN_RECORDS_FOR_CLUSTERING,
)
from database.vector_store import chunk_text, CHUNK_CHARS


def _record(record_id: int, url: str, sha: str = "abc", level: str = "MEDIUM",
            source: str = "SURFACE_WEB", hours_ago: float = 0.0):
    return SimpleNamespace(
        id=record_id, source_url=url, sha256_hash=sha, threat_level=level,
        source_type=source,
        created_at=datetime.utcnow() - timedelta(hours=hours_ago),
    )


def _analysis(drugs=(), phones=(), wallets=(), handles=(), locations=()):
    return {
        "entities": {
            "drugs": list(drugs),
            "phones": list(phones),
            "handles": list(handles),
            "crypto_wallets": {"btc": list(wallets)},
            "upi_ids": [],
            "locations": list(locations),
        },
        "geo_markers": [],
    }


# ── Regression: identifier fabrication ───────────────────────────────

class TestPhoneExtractionBoundaries:
    """
    An ISBN is not a phone number.

    `ISBN 978-8185107769` was extracted as the Indian mobile number
    8185107769, because the pattern anchored only its right-hand edge and so
    could start part-way through a longer digit run. Correlation then treated
    that number as a shared identifier and reported two unrelated records as
    a confirmed link. A fabricated identifier is worse than a missed one.
    """

    @pytest.mark.parametrize("text", [
        "ISBN 978-8185107769",
        "ISBN 9788185107769",
        "reference 1234568185107769",
        "order 8185107769-22",
        "978-81-85107-76-9",
    ])
    def test_embedded_digit_runs_are_not_phones(self, text):
        assert PHONE_REGEX.findall(text) == []

    @pytest.mark.parametrize("text,expected", [
        ("call me on 9876543210", ["9876543210"]),
        ("+91 9876543210", ["+91 9876543210"]),
        ("+91-9876543210", ["+91-9876543210"]),
        ("contact 8123456789 or 7012345678",
         ["8123456789", "7012345678"]),
    ])
    def test_genuine_numbers_still_extracted(self, text, expected):
        assert PHONE_REGEX.findall(text) == expected


# ── Chunking ─────────────────────────────────────────────────────────

class TestChunking:
    """
    The embedding model truncates at roughly 1,000 characters. A long page
    indexed whole was represented by its opening paragraph alone, so anything
    below the fold was unreachable by search and invisible to correlation.
    """

    def test_short_text_is_one_chunk(self):
        assert chunk_text("500g chitta available, escrow only") == [
            "500g chitta available, escrow only"]

    def test_long_text_is_split(self):
        text = "Sentence about chitta near Majitha. " * 200
        chunks = chunk_text(text)
        assert len(chunks) > 1
        assert all(len(c) <= CHUNK_CHARS for c in chunks)

    def test_content_past_the_first_window_is_indexed(self):
        """The detail that matters is rarely in the first paragraph."""
        text = ("Filler about general policy. " * 120
                + " Contact 9876543210 for wholesale supply.")
        chunks = chunk_text(text)
        assert any("9876543210" in c for c in chunks)

    def test_empty_text_produces_no_chunks(self):
        assert chunk_text("") == []
        assert chunk_text("   ") == []


# ── Link scoring ─────────────────────────────────────────────────────

class TestLinkScoring:

    def _correlator(self):
        correlator = SemanticCorrelator()
        correlator._devices = {}
        return correlator

    def test_same_url_pair_is_never_a_link(self):
        """
        Two collections of one page share every signal and mean nothing.

        Before this guard the pair scored 68 as a confirmed LINK, carrying
        "shared phone" and similarity 1.0 - a network finding invented out of
        one Wikipedia article crawled twice.
        """
        correlator = self._correlator()
        ids = [1, 2]
        records = {
            1: _record(1, "https://example.org/page"),
            2: _record(2, "https://example.org/page", sha="def"),
        }
        analyses = {
            1: _analysis(drugs=["Heroin / Chitta"], phones=["9876543210"]),
            2: _analysis(drugs=["Heroin / Chitta"], phones=["9876543210"]),
        }
        similarity = [[1.0, 1.0], [1.0, 1.0]]

        assert correlator.score_links(ids, similarity, analyses, records) == []

    def test_shared_wallet_across_urls_is_a_link(self):
        correlator = self._correlator()
        ids = [1, 2]
        records = {
            1: _record(1, "https://market-a.onion/listing"),
            2: _record(2, "https://market-b.onion/listing"),
        }
        wallet = "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh"
        analyses = {
            1: _analysis(wallets=[wallet]),
            2: _analysis(wallets=[wallet]),
        }
        similarity = [[1.0, 0.2], [0.2, 1.0]]

        links = correlator.score_links(ids, similarity, analyses, records)
        assert len(links) == 1
        assert links[0]["verdict"] == "LINK"
        assert "shared_wallet" in links[0]["hard_signals"]

    def test_similarity_alone_is_only_a_lead(self):
        """
        Wording is not evidence of a relationship.

        Two articles on the same subject are near-identical in vector space
        while having nothing to do with each other. Similarity opens a lead;
        an identifier is what makes it a link.
        """
        correlator = self._correlator()
        ids = [1, 2]
        records = {
            1: _record(1, "https://news-a.example/story"),
            2: _record(2, "https://news-b.example/story"),
        }
        analyses = {1: _analysis(), 2: _analysis()}
        similarity = [[1.0, 0.93], [0.93, 1.0]]

        links = correlator.score_links(ids, similarity, analyses, records)
        assert len(links) == 1
        assert links[0]["verdict"] == "LEAD"
        assert links[0]["hard_signals"] == []

    def test_circumstantial_signals_accumulate_below_the_similarity_floor(self):
        """
        Evidence adds up even when the wording does not quite match.

        Two paraphrases of one deal - same substance, same village, same day -
        sat at similarity 0.51 against a 0.55 floor and were discarded, taking
        25 points of other evidence with them. Weight of combination decides,
        not whether one particular signal cleared its threshold.
        """
        correlator = self._correlator()
        ids = [1, 2]
        records = {
            1: _record(1, "https://t.me/ch1/44"),
            2: _record(2, "https://t.me/ch2/91"),
        }
        analyses = {
            1: _analysis(drugs=["Heroin / Chitta"], locations=["Majitha"]),
            2: _analysis(drugs=["Heroin / Chitta"], locations=["Majitha"]),
        }
        similarity = [[1.0, 0.51], [0.51, 1.0]]

        links = correlator.score_links(ids, similarity, analyses, records)
        assert len(links) == 1
        assert links[0]["verdict"] == "LEAD"
        assert "semantic" not in links[0]["signals"]

    def test_one_shared_attribute_is_not_enough(self):
        """
        In a corpus about heroin in Punjab, a shared substance matches almost
        everything. Reporting that as a lead is how an analyst gets buried.
        """
        correlator = self._correlator()
        ids = [1, 2]
        records = {
            1: _record(1, "https://a.example", hours_ago=400),
            2: _record(2, "https://b.example", hours_ago=0),
        }
        analyses = {
            1: _analysis(drugs=["Heroin / Chitta"]),
            2: _analysis(drugs=["Heroin / Chitta"]),
        }
        similarity = [[1.0, 0.3], [0.3, 1.0]]

        assert correlator.score_links(ids, similarity, analyses, records) == []

    def test_weak_similarity_reports_nothing(self):
        correlator = self._correlator()
        ids = [1, 2]
        records = {
            1: _record(1, "https://a.example", hours_ago=500),
            2: _record(2, "https://b.example", hours_ago=0),
        }
        analyses = {1: _analysis(), 2: _analysis()}
        similarity = [[1.0, 0.2], [0.2, 1.0]]

        assert correlator.score_links(ids, similarity, analyses, records) == []

    def test_every_link_carries_its_evidence(self):
        """A score an analyst cannot inspect is one they cannot defend."""
        correlator = self._correlator()
        ids = [1, 2]
        records = {
            1: _record(1, "https://a.onion/x"),
            2: _record(2, "https://b.onion/y"),
        }
        analyses = {
            1: _analysis(phones=["9876543210"], drugs=["Opium / Bhukki"]),
            2: _analysis(phones=["9876543210"], drugs=["Opium / Bhukki"]),
        }
        similarity = [[1.0, 0.8], [0.8, 1.0]]

        link = correlator.score_links(ids, similarity, analyses, records)[0]
        assert link["signals"]["shared_phone"] == ["9876543210"]
        assert link["basis"]
        assert 0 < link["strength"] <= 100


# ── Clustering and mirrors ───────────────────────────────────────────

class TestClustering:

    def test_small_corpus_is_refused_not_guessed(self):
        correlator = SemanticCorrelator()
        ids = [1, 2]
        result = correlator.cluster(ids, [[1.0, 0.0], [0.0, 1.0]], {}, {})
        assert result["status"] == "INSUFFICIENT_DATA"
        assert result["clusters"] == []
        assert str(MIN_RECORDS_FOR_CLUSTERING) in result["message"]

    def test_single_document_cluster_is_flagged(self):
        """Re-crawls of one page cluster perfectly and prove nothing."""
        correlator = SemanticCorrelator()
        ids = [1, 2, 3, 4, 5]
        vectors = [[1.0, 0.0], [1.0, 0.01], [1.0, 0.02],
                   [0.0, 1.0], [0.0, 0.99]]
        records = {i: _record(i, "https://example.org/one") for i in (1, 2, 3)}
        records.update({i: _record(i, f"https://other.org/{i}") for i in (4, 5)})
        analyses = {i: _analysis() for i in ids}

        result = correlator.cluster(ids, vectors, analyses, records)
        assert result["status"] == "SUCCESS"
        single = [c for c in result["clusters"] if c["single_document"]]
        assert single, "a cluster drawn from one URL must be marked as such"
        assert single[0]["distinct_urls"] == 1


class TestMirrors:

    def test_same_url_is_a_revision_not_a_mirror(self):
        correlator = SemanticCorrelator()
        ids = [1, 2]
        records = {
            1: _record(1, "https://example.org/page", sha="aaa"),
            2: _record(2, "https://example.org/page", sha="bbb"),
        }
        mirrors = correlator.find_mirrors(ids, [[1.0, 0.99], [0.99, 1.0]], records)
        assert mirrors[0]["kind"] == "REVISION"
        assert "not evidence of a relationship" in mirrors[0]["interpretation"]

    def test_different_url_same_bytes_is_a_mirror(self):
        correlator = SemanticCorrelator()
        ids = [1, 2]
        records = {
            1: _record(1, "https://market-a.onion/x", sha="same"),
            2: _record(2, "https://market-b.onion/y", sha="same"),
        }
        mirrors = correlator.find_mirrors(ids, [[1.0, 0.999], [0.999, 1.0]], records)
        assert mirrors[0]["kind"] == "MIRROR"
        assert mirrors[0]["identical_bytes"] is True


class TestCosineMatrix:

    def test_identical_vectors_score_one(self):
        matrix = cosine_matrix([[1.0, 0.0], [1.0, 0.0]])
        assert matrix[0][1] == pytest.approx(1.0)

    def test_orthogonal_vectors_score_zero(self):
        matrix = cosine_matrix([[1.0, 0.0], [0.0, 1.0]])
        assert matrix[0][1] == pytest.approx(0.0)

    def test_zero_vector_does_not_divide_by_zero(self):
        matrix = cosine_matrix([[0.0, 0.0], [1.0, 0.0]])
        assert matrix[0][1] == pytest.approx(0.0)
