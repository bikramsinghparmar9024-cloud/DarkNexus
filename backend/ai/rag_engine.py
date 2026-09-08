"""
Retrieval-Augmented Intelligence Query Engine.

Investigators ask questions in plain language:

  "Show heroin distribution near the Amritsar border"
  "Which sellers accept dead-drop delivery or UPI?"
  "What crypto addresses are linked to Tramadol wholesale?"

ChromaDB retrieves semantically similar intercepts - matching on meaning, so a
query for "heroin" also surfaces records that only ever said "chitta". This
module then summarises what was actually retrieved.

Every statement in the answer is derived from the returned documents and is
traceable to a source record. Nothing is asserted that the evidence does not
support: if retrieval comes back thin, the answer says so rather than filling
the gap with plausible-sounding narrative.
"""

from typing import Any, Dict, List
from collections import Counter
import logging

from database.vector_store import vector_store
from ai.entity_extractor import entity_extractor

logger = logging.getLogger("rag_engine")

# Chroma returns squared-L2 distance; smaller is closer.
STRONG_MATCH_DISTANCE = 1.0
WEAK_MATCH_DISTANCE = 1.6


def _relevance(distance: float) -> str:
    if distance <= STRONG_MATCH_DISTANCE:
        return "STRONG"
    if distance <= WEAK_MATCH_DISTANCE:
        return "MODERATE"
    return "WEAK"


class RAGEngine:
    """Semantic retrieval over collected intelligence, with grounded synthesis."""

    def query(self, investigator_prompt: str, top_k: int = 5) -> Dict[str, Any]:
        prompt = (investigator_prompt or "").strip()
        if not prompt:
            return {
                "query": investigator_prompt,
                "answer": "Please provide an investigative query.",
                "sources": [],
                "key_entities": {},
                "evidence_count": 0,
            }

        query_entities = entity_extractor.extract(prompt)

        if not vector_store.collection:
            return {
                "query": prompt,
                "answer": ("Semantic search is unavailable: the ChromaDB vector store is not "
                           "initialised. Install chromadb and re-index collected records."),
                "sources": [],
                "key_entities": query_entities,
                "evidence_count": 0,
                "degraded": True,
            }

        matches = vector_store.query_similar(query_text=prompt, n_results=top_k)

        if not matches:
            return {
                "query": prompt,
                "answer": ("No indexed intelligence matched this query. Either nothing "
                           "collected so far relates to it, or the records predate vector "
                           "indexing. Try broadening the wording, or re-run the analysis "
                           "pipeline to index existing records."),
                "sources": [],
                "key_entities": query_entities,
                "evidence_count": 0,
            }

        # ── Aggregate what the retrieved evidence actually contains ──────
        drugs, locations, handles, wallets, tactics = Counter(), Counter(), set(), set(), Counter()
        source_types = Counter()
        threat_levels = Counter()
        sources: List[Dict[str, Any]] = []
        strong_matches = 0

        for match in matches:
            doc = match.get("document", "") or ""
            meta = match.get("metadata", {}) or {}
            distance = float(match.get("distance", 0.0) or 0.0)
            relevance = _relevance(distance)
            if relevance == "STRONG":
                strong_matches += 1

            found = entity_extractor.extract(doc)
            for d in found.get("drugs", []):
                drugs[d] += 1
            for loc in found.get("locations", []):
                locations[loc] += 1
            for h in found.get("handles", []):
                handles.add(h)
            for chain_addrs in (found.get("crypto_wallets") or {}).values():
                wallets.update(chain_addrs or [])
            for slang in found.get("regional_slang_detected", []):
                if slang.get("category") in ("MODUS_OPERANDI", "BORDER_CORRIDOR", "PAYMENT"):
                    tactics[slang.get("forensic_term", "")] += 1

            stype = meta.get("source_type", "UNKNOWN")
            source_types[stype] += 1
            if meta.get("threat_level"):
                threat_levels[meta["threat_level"]] += 1

            sha = str(meta.get("sha256", ""))
            sources.append({
                "record_id": meta.get("record_id"),
                "source_type": stype,
                "url": meta.get("url", "N/A"),
                "author": meta.get("author") or "N/A",
                "threat_level": meta.get("threat_level"),
                "sha256": (sha[:16] + "...") if sha else "N/A",
                "relevance": relevance,
                "distance": round(distance, 4),
                "snippet": doc[:240].strip(),
            })

        answer = self._synthesize(
            prompt, matches, strong_matches, drugs, locations,
            handles, wallets, tactics, source_types, threat_levels,
        )

        return {
            "query": prompt,
            "answer": answer,
            "sources": sources,
            "key_entities": query_entities,
            "evidence_count": len(matches),
            "strong_match_count": strong_matches,
            "aggregated_findings": {
                "drugs": dict(drugs),
                "locations": dict(locations),
                "handles": sorted(handles),
                "crypto_wallets": sorted(wallets),
                "tactics": dict(tactics),
                "source_breakdown": dict(source_types),
                "threat_breakdown": dict(threat_levels),
            },
        }

    def _synthesize(self, prompt, matches, strong_matches, drugs, locations,
                    handles, wallets, tactics, source_types, threat_levels) -> str:
        """Build a plain-language brief strictly from what was retrieved."""
        lines: List[str] = []

        breakdown = ", ".join("%d %s" % (c, s.replace("_", " ").lower())
                              for s, c in source_types.most_common())
        lines.append("Retrieved %d record(s) matching '%s' (%s). %d rated a strong semantic match."
                     % (len(matches), prompt, breakdown, strong_matches))

        if strong_matches == 0:
            lines.append("")
            lines.append("CAUTION: no result was a strong match. The findings below are "
                         "loosely related and should be treated as leads only.")

        if drugs:
            lines.append("")
            lines.append("Substances referenced: "
                         + ", ".join("%s (%d record%s)" % (d, c, "" if c == 1 else "s")
                                     for d, c in drugs.most_common()))
        if locations:
            lines.append("Locations referenced: "
                         + ", ".join("%s (%d)" % (l, c) for l, c in locations.most_common()))
        if tactics:
            lines.append("Methods indicated: " + ", ".join(t for t in tactics if t))

        if handles:
            lines.append("")
            lines.append("Accounts appearing in the evidence: " + ", ".join(sorted(handles)[:10]))
        if wallets:
            lines.append("Crypto addresses to trace: " + ", ".join(sorted(wallets)[:5]))

        if threat_levels:
            lines.append("")
            lines.append("Threat ratings across the matched records: "
                         + ", ".join("%s x%d" % (lvl, c) for lvl, c in threat_levels.most_common()))

        if not drugs and not locations and not handles and not wallets:
            lines.append("")
            lines.append("No narcotics, locations, accounts or wallet addresses were "
                         "extracted from the matched records. The match is textual only.")

        lines.append("")
        lines.append("All findings above are drawn from the %d cited source(s) below; "
                     "each retains its SHA-256 hash for chain of custody." % len(matches))
        return "\n".join(lines)


rag_engine = RAGEngine()
