"""
Semantic Correlation - pattern recognition across records, computed locally.

The existing correlation engine aggregates exact matches: it can tell you that
two records contain the same phone number. It cannot tell you that

    "500g chitta ready, dead drop near Majitha"
    "white powder available, drop point Majitha side, escrow only"

describe the same operation, because they share no literal token that matters.
That is the gap this module fills, using the sentence embeddings already held
in ChromaDB. Nothing here calls an external service; the model is the local
MiniLM encoder Chroma ships with, so evidence text never leaves the machine.

Three things are computed:

  mirrors    near-identical content republished at a different URL - a vendor
             rotating domains, or one listing syndicated across markets
  clusters   groups of records that describe the same activity, found by
             agglomerative clustering over cosine distance
  links      pairwise connections scored from several independent signals

A deliberate restriction runs through all of it. Semantic similarity alone is
never enough to assert a link. Two Wikipedia articles about narcotics are 0.9
similar because they share a register, not because they share a network - and
a system that reports that as an association will bury an investigator in
noise the first time it meets a real corpus. Similarity opens a lead; a shared
identifier, device, or location is what promotes it to a link.
"""

from typing import Any, Dict, List, Optional, Sequence, Tuple
from collections import Counter, defaultdict
from datetime import datetime, timedelta
import logging
import math

logger = logging.getLogger("semantic_correlation")

# ── Thresholds, stated so they can be argued with ────────────────────
# Cosine similarity above which two records are treated as the same content.
MIRROR_SIMILARITY = 0.97
# Cosine distance ceiling for two records to join the same cluster.
CLUSTER_DISTANCE = 0.45
# Below this similarity, wording is not treated as a signal in its own right.
LINK_MIN_SIMILARITY = 0.55
# Total score a pair must reach to be reported as a lead when no hard
# identifier is shared. Set so that one shared substance (8) or one shared
# location (12) is never enough on its own - in a corpus about heroin in
# Amritsar, those match almost everything and would bury the analyst in
# pairings. Drug plus location plus temporal proximity reaches it; that
# combination is specific enough to be worth a look.
LEAD_MIN_SCORE = 25
# Similarity at which wording alone is worth reporting, with no other signal.
# A paraphrased re-listing shares no identifier by construction - that is the
# point of paraphrasing it - so there has to be a route to a lead that rests
# on the text itself. The bar is set high because below it, similarity mostly
# reflects shared register rather than shared origin.
STRONG_SEMANTIC_LEAD = 0.85
# A corpus smaller than this cannot support cluster analysis honestly.
MIN_RECORDS_FOR_CLUSTERING = 5
# Records within this window count as temporally proximate.
TEMPORAL_WINDOW_HOURS = 48

# Signal weights for pairwise link scoring. Hard identifiers outweigh
# similarity by design: sharing a wallet is evidence, reading alike is not.
SIGNAL_WEIGHTS = {
    "shared_wallet": 40,
    "shared_phone": 35,
    "shared_handle": 30,
    "shared_device": 30,
    "shared_upi": 25,
    "semantic": 20,
    "shared_location": 12,
    "shared_drug": 8,
    "temporal_proximity": 5,
}

# Signals that constitute independent evidence of a connection. A link built
# only from the others is reported as a lead.
HARD_SIGNALS = {"shared_wallet", "shared_phone", "shared_handle",
                "shared_device", "shared_upi"}


def _require_numpy():
    try:
        import numpy as np
        return np
    except ImportError:                                       # pragma: no cover
        logger.error("numpy is required for semantic correlation.")
        return None


def cosine_matrix(vectors: Sequence[Sequence[float]]):
    """Pairwise cosine similarity for L2-normalised rows."""
    np = _require_numpy()
    if np is None or not len(vectors):
        return None
    matrix = np.asarray(vectors, dtype=float)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    matrix = matrix / norms
    return matrix @ matrix.T


# ─────────────────────────────────────────────────────────────────────
# Entity helpers
# ─────────────────────────────────────────────────────────────────────

def _wallet_set(entities: Dict[str, Any]) -> set:
    wallets = entities.get("crypto_wallets") or {}
    out = set()
    if isinstance(wallets, dict):
        for addresses in wallets.values():
            if isinstance(addresses, (list, tuple)):
                out.update(a for a in addresses if a)
    elif isinstance(wallets, (list, tuple)):
        out.update(a for a in wallets if a)
    return out


def _entity_sets(analysis: Dict[str, Any]) -> Dict[str, set]:
    entities = (analysis or {}).get("entities") or {}
    geo_markers = (analysis or {}).get("geo_markers") or []
    locations = {m.get("location") for m in geo_markers if m.get("location")}
    locations.update(entities.get("locations") or [])
    return {
        "wallets": _wallet_set(entities),
        "phones": set(entities.get("phones") or []),
        "handles": {h.lower() for h in (entities.get("handles") or [])},
        "upi": set(entities.get("upi_ids") or []),
        "drugs": set(entities.get("drugs") or []),
        "locations": {str(l) for l in locations if l},
    }


class SemanticCorrelator:
    """Vector-space pattern detection over stored intelligence."""

    # ── Loading ──────────────────────────────────────────────────────

    async def _load(self, days: Optional[int], limit: int) -> Tuple[List[Any], Dict[int, Dict], Dict[int, List[float]]]:
        """
        Load records, their analysis blocks, and their pooled vectors.

        Returns only records that have both, since a record with no embedding
        cannot participate in vector comparison and silently dropping it from
        one half of the analysis would skew every count.
        """
        from sqlalchemy import select
        from database.postgres import AsyncSessionLocal, ScrapedData, MediaArtifact
        from database.vector_store import vector_store
        from ai.enrichment import get_analysis

        async with AsyncSessionLocal() as db:
            stmt = select(ScrapedData).order_by(ScrapedData.created_at.desc()).limit(limit)
            if days:
                stmt = stmt.where(
                    ScrapedData.created_at >= datetime.utcnow() - timedelta(days=days))
            records = list((await db.execute(stmt)).scalars().all())

            media = list((await db.execute(
                select(MediaArtifact).where(MediaArtifact.device_signature.is_not(None))
            )).scalars().all())

        analyses = {r.id: get_analysis(r) for r in records}

        parents, vectors, metas = vector_store.all_record_vectors()
        by_record: Dict[int, List[float]] = {}
        for parent, vector, meta in zip(parents, vectors, metas):
            record_id = meta.get("record_id")
            try:
                record_id = int(record_id)
            except (TypeError, ValueError):
                # Fall back to the id convention SOURCE_TYPE_<id>.
                tail = str(parent).rsplit("_", 1)[-1]
                record_id = int(tail) if tail.isdigit() else None
            if record_id is not None:
                by_record[record_id] = vector

        # Device signatures per record, for the hardware-linkage signal.
        devices: Dict[int, set] = defaultdict(set)
        for m in media:
            if m.scraped_data_id and m.device_signature:
                devices[m.scraped_data_id].add(m.device_signature)
        self._devices = devices

        return records, analyses, by_record

    # ── Mirrors ──────────────────────────────────────────────────────

    def find_mirrors(self, ids: List[int], similarity, records_by_id) -> List[Dict[str, Any]]:
        """Near-identical content appearing under different URLs."""
        mirrors = []
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                score = float(similarity[i][j])
                if score < MIRROR_SIMILARITY:
                    continue
                left, right = records_by_id[ids[i]], records_by_id[ids[j]]
                same_url = left.source_url == right.source_url
                mirrors.append({
                    "record_ids": [ids[i], ids[j]],
                    "kind": "REVISION" if same_url else "MIRROR",
                    "similarity": round(score, 4),
                    "urls": [left.source_url, right.source_url],
                    "identical_bytes": left.sha256_hash == right.sha256_hash,
                    "interpretation": (
                        # One URL collected twice with the page edited in
                        # between. Worth surfacing so an analyst knows the
                        # corpus holds two versions - but it says nothing
                        # about a network, and must never read as one.
                        "the same page collected twice with minor changes; "
                        "not evidence of a relationship between sources"
                        if same_url else
                        "byte-identical content republished at a second URL"
                        if left.sha256_hash == right.sha256_hash else
                        "near-identical wording under a different URL; "
                        "consistent with a rotated or mirrored listing"
                    ),
                })
        return sorted(mirrors, key=lambda m: -m["similarity"])

    # ── Clustering ───────────────────────────────────────────────────

    def cluster(self, ids: List[int], vectors, analyses, records_by_id) -> Dict[str, Any]:
        """
        Group records describing the same activity.

        Agglomerative rather than k-means: the number of operations in a
        corpus is not known in advance, and forcing a chosen k invents
        structure where there is none.
        """
        if len(ids) < MIN_RECORDS_FOR_CLUSTERING:
            return {
                "status": "INSUFFICIENT_DATA",
                "clusters": [],
                "message": (f"{len(ids)} embedded records; clustering needs at "
                            f"least {MIN_RECORDS_FOR_CLUSTERING} to say anything "
                            f"meaningful."),
            }

        try:
            from sklearn.cluster import AgglomerativeClustering
        except ImportError:                                   # pragma: no cover
            return {"status": "UNAVAILABLE", "clusters": [],
                    "message": "scikit-learn is not installed."}

        model = AgglomerativeClustering(
            n_clusters=None,
            distance_threshold=CLUSTER_DISTANCE,
            metric="cosine",
            linkage="average",
        )
        labels = model.fit_predict(vectors)

        grouped: Dict[int, List[int]] = defaultdict(list)
        for record_id, label in zip(ids, labels):
            grouped[int(label)].append(record_id)

        clusters = []
        for label, members in sorted(grouped.items(), key=lambda kv: -len(kv[1])):
            if len(members) < 2:
                continue              # a cluster of one is just a record
            drugs, locations, levels, sources = Counter(), Counter(), Counter(), Counter()
            urls = set()
            for record_id in members:
                sets = _entity_sets(analyses.get(record_id, {}))
                drugs.update(sets["drugs"])
                locations.update(sets["locations"])
                record = records_by_id[record_id]
                levels.update([record.threat_level or "UNREVIEWED"])
                sources.update([record.source_type])
                urls.add(record.source_url)

            clusters.append({
                "cluster_id": int(label),
                "size": len(members),
                "record_ids": members,
                "distinct_urls": len(urls),
                # Several collections of one page cluster perfectly and mean
                # nothing. Saying so on the cluster keeps an analyst from
                # reading a re-crawl as a three-source pattern.
                "single_document": len(urls) == 1,
                "distinct_sources": len(sources),
                "source_types": dict(sources),
                "dominant_drugs": [d for d, _ in drugs.most_common(3)],
                "dominant_locations": [l for l, _ in locations.most_common(3)],
                "threat_mix": dict(levels),
                "highest_threat": max(
                    levels, key=lambda lv: ["UNREVIEWED", "LOW", "MEDIUM", "HIGH", "SEVERE"].index(lv)
                    if lv in ["UNREVIEWED", "LOW", "MEDIUM", "HIGH", "SEVERE"] else 0),
                # A group drawn entirely from one source is as likely to
                # reflect that source's house style as a real relationship.
                "corroborated_across_sources": len(sources) > 1,
            })

        return {
            "status": "SUCCESS",
            "clusters": clusters,
            "clustered_records": sum(c["size"] for c in clusters),
            "singletons": len(ids) - sum(c["size"] for c in clusters),
            "distance_threshold": CLUSTER_DISTANCE,
        }

    # ── Pairwise links ───────────────────────────────────────────────

    def score_links(self, ids: List[int], similarity, analyses, records_by_id,
                    max_links: int = 50) -> List[Dict[str, Any]]:
        """
        Score every record pair, keeping those with real supporting evidence.

        Each link carries the signals that produced it. A score without a
        breakdown is not something an investigator can act on or defend.
        """
        sets = {record_id: _entity_sets(analyses.get(record_id, {})) for record_id in ids}
        links: List[Dict[str, Any]] = []

        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a, b = ids[i], ids[j]

                # Two collections of one URL are two copies of one document.
                # Every signal fires - same phone, same drugs, similarity 1.0 -
                # and the pair scores like a strong network link while being
                # nothing of the kind. Reported as a revision instead.
                if records_by_id[a].source_url == records_by_id[b].source_url:
                    continue

                sim = float(similarity[i][j])
                signals: Dict[str, Any] = {}

                shared_wallets = sets[a]["wallets"] & sets[b]["wallets"]
                shared_phones = sets[a]["phones"] & sets[b]["phones"]
                shared_handles = sets[a]["handles"] & sets[b]["handles"]
                shared_upi = sets[a]["upi"] & sets[b]["upi"]
                shared_devices = self._devices.get(a, set()) & self._devices.get(b, set())
                shared_locations = sets[a]["locations"] & sets[b]["locations"]
                shared_drugs = sets[a]["drugs"] & sets[b]["drugs"]

                if shared_wallets:
                    signals["shared_wallet"] = sorted(shared_wallets)
                if shared_phones:
                    signals["shared_phone"] = sorted(shared_phones)
                if shared_handles:
                    signals["shared_handle"] = sorted(shared_handles)
                if shared_upi:
                    signals["shared_upi"] = sorted(shared_upi)
                if shared_devices:
                    signals["shared_device"] = sorted(shared_devices)
                if shared_locations:
                    signals["shared_location"] = sorted(shared_locations)
                if shared_drugs:
                    signals["shared_drug"] = sorted(shared_drugs)
                if sim >= LINK_MIN_SIMILARITY:
                    signals["semantic"] = round(sim, 4)

                left, right = records_by_id[a], records_by_id[b]
                if left.created_at and right.created_at:
                    gap = abs((left.created_at - right.created_at).total_seconds()) / 3600.0
                    if gap <= TEMPORAL_WINDOW_HOURS:
                        signals["temporal_proximity"] = round(gap, 1)

                if not signals:
                    continue

                # Semantic contributes proportionally to how far above the
                # floor it sits, so a 0.56 match does not score like a 0.95.
                score = 0.0
                for name in signals:
                    weight = SIGNAL_WEIGHTS.get(name, 0)
                    if name == "semantic":
                        span = max(1e-6, 1.0 - LINK_MIN_SIMILARITY)
                        score += weight * min(1.0, (sim - LINK_MIN_SIMILARITY) / span)
                    else:
                        score += weight
                score = int(min(round(score), 100))

                hard = sorted(set(signals) & HARD_SIGNALS)
                if hard:
                    verdict = "LINK"
                    basis = ("independent identifier evidence: "
                             + ", ".join(h.replace("shared_", "") for h in hard))
                elif score >= LEAD_MIN_SCORE or sim >= STRONG_SEMANTIC_LEAD:
                    # Circumstantial signals accumulate. Requiring the wording
                    # to clear 0.55 before any of the rest counted put a cliff
                    # in the wrong place: two paraphrases of one deal, sharing
                    # a substance, a village and a timeframe, were discarded
                    # at similarity 0.51 while contributing 25 points of other
                    # evidence. What matters is the weight of the combination,
                    # not which single signal carried it.
                    verdict = "LEAD"
                    basis = ("circumstantial only - %s; no shared identifier, "
                             "so this is a lead to check rather than an "
                             "established connection"
                             % ", ".join(sorted(k for k in signals
                                                if k != "temporal_proximity")))
                else:
                    continue

                links.append({
                    "record_ids": [a, b],
                    "strength": score,
                    "verdict": verdict,
                    "basis": basis,
                    "signals": signals,
                    "hard_signals": hard,
                    "semantic_similarity": round(sim, 4),
                })

        links.sort(key=lambda l: (l["verdict"] != "LINK", -l["strength"]))
        return links[:max_links]

    # ── Entry point ──────────────────────────────────────────────────

    async def build(self, days: Optional[int] = None, limit: int = 500) -> Dict[str, Any]:
        """Run the full semantic pass and return a structured picture."""
        self._devices = {}
        records, analyses, vectors_by_id = await self._load(days, limit)
        records_by_id = {r.id: r for r in records}

        ids = [r.id for r in records if r.id in vectors_by_id]
        missing = [r.id for r in records if r.id not in vectors_by_id]

        base = {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "window_days": days,
            "records_examined": len(records),
            "records_embedded": len(ids),
            "records_missing_embedding": missing,
            "method": "local MiniLM sentence embeddings; no external service",
        }

        if len(ids) < 2:
            return {**base, "status": "INSUFFICIENT_DATA",
                    "message": ("Fewer than two embedded records. Collect more "
                                "intelligence, or run the vector reindex if "
                                "records exist but were never embedded."),
                    "mirrors": [], "clusters": {"status": "INSUFFICIENT_DATA", "clusters": []},
                    "links": []}

        vectors = [vectors_by_id[i] for i in ids]
        similarity = cosine_matrix(vectors)
        if similarity is None:
            return {**base, "status": "UNAVAILABLE",
                    "message": "numpy unavailable; cannot compute similarity.",
                    "mirrors": [], "clusters": {"status": "UNAVAILABLE", "clusters": []},
                    "links": []}

        mirrors = self.find_mirrors(ids, similarity, records_by_id)
        clusters = self.cluster(ids, vectors, analyses, records_by_id)
        links = self.score_links(ids, similarity, analyses, records_by_id)

        return {
            **base,
            "status": "SUCCESS",
            "mirrors": mirrors,
            "clusters": clusters,
            "links": links,
            "summary": {
                "mirror_pairs": len(mirrors),
                "clusters_found": len(clusters.get("clusters", [])),
                "confirmed_links": sum(1 for l in links if l["verdict"] == "LINK"),
                "leads": sum(1 for l in links if l["verdict"] == "LEAD"),
            },
        }


semantic_correlator = SemanticCorrelator()
