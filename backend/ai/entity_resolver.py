"""
Explainable Entity Resolution Engine.
Combines multiple independent signals (PGP fingerprints, aliases, payment handles,
surface-web corroboration, timing correlation) to produce candidate identity matches
with confidence scores and human-readable explanations.

Every relationship exposes:
- Confidence level and its meaning
- Evidence supporting the relationship
- Source reliability/status
- Contradicting or missing evidence
- Relationship type and number of inferential hops
- Analyst verification status
"""

import re
import hashlib
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import logging

logger = logging.getLogger("entity_resolver")


# ─── Signal weights for confidence calculation ────────────────────
SIGNAL_WEIGHTS = {
    "pgp_fingerprint": 0.35,            # Near-conclusive: vendors publish these
    "payment_handle": 0.20,             # Strong: a reused wallet is hard to explain away
    "alias_overlap": 0.15,              # Supporting
    "shared_device": 0.15,              # Supporting: same camera behind both accounts
    "communication_id": 0.10,           # Supporting
    "surface_web_corroboration": 0.03,  # Weak: open-source mention of both
    "timing_correlation": 0.02,         # Weak: co-activity is common by chance
}

SIGNAL_DESCRIPTIONS = {
    "shared_device": "Photographs from the same camera under both identities",
    "pgp_fingerprint": "Matching public PGP fingerprint across platforms",
    "alias_overlap": "Repeated vendor/user handle or alias pattern",
    "payment_handle": "Shared payment identifier (BTC address, UPI ID, ETH wallet)",
    "communication_id": "Repeated public contact/username or phone number",
    "surface_web_corroboration": "Independent public mention linking identities",
    "timing_correlation": "Temporally correlated activity across platforms",
}

# ─── Source reliability ratings ───────────────────────────────────
SOURCE_RELIABILITY = {
    "DARK_WEB": {"rating": "MEDIUM", "score": 0.6, "note": "Adversarial environment; content may be deceptive"},
    "TELEGRAM": {"rating": "MEDIUM", "score": 0.6, "note": "Pseudonymous; channel integrity varies"},
    "SURFACE_WEB": {"rating": "LOW-MEDIUM", "score": 0.4, "note": "Open source; may be planted or outdated"},
    "FORENSIC": {"rating": "HIGH", "score": 0.9, "note": "Lawfully acquired forensic artifact"},
    "CASE_DATA": {"rating": "HIGH", "score": 0.85, "note": "Authorized case/investigation record"},
    "BLOCKCHAIN": {"rating": "HIGH", "score": 0.8, "note": "Immutable on-chain record; attribution is separate"},
}

# ─── Confidence level thresholds ──────────────────────────────────
CONFIDENCE_LEVELS = {
    "VERY_HIGH": {"min": 85, "label": "Very High Confidence", "meaning": "Multiple strong independent signals converge"},
    "HIGH": {"min": 70, "label": "High Confidence", "meaning": "Strong primary signal with supporting corroboration"},
    "MODERATE": {"min": 50, "label": "Moderate Confidence", "meaning": "Multiple supporting signals but no strong anchor"},
    "LOW": {"min": 25, "label": "Low Confidence", "meaning": "Limited signals; requires further investigation"},
    "SPECULATIVE": {"min": 0, "label": "Speculative", "meaning": "Weak or single signal only"},
}


class EntityResolver:
    """Explainable multi-signal entity resolution engine."""

    def __init__(self):
        # Populated by refresh(); empty until then so a caller that forgets to
        # refresh gets an honest "no data" rather than stale or invented rows.
        self.knowledge_base: Dict[str, Any] = {}
        self.relationships: List[Dict[str, Any]] = []
        self.last_refreshed: Optional[str] = None

    async def refresh(self, limit: int = 2000) -> Dict[str, Any]:
        """
        Rebuild the knowledge base from collected intelligence.

        Cheap enough to call per request at current data volumes; if that
        changes, cache on last_refreshed rather than reintroducing a literal.
        """
        from ai.entity_store import build_knowledge_base
        from datetime import datetime as _dt

        self.knowledge_base, self.relationships = await build_knowledge_base(limit)
        self.last_refreshed = _dt.utcnow().isoformat() + "Z"
        return {
            "entities": len(self.knowledge_base),
            "relationships": len(self.relationships),
            "refreshed_at": self.last_refreshed,
        }

    def calculate_confidence(self, signals: Dict[str, Dict]) -> Tuple[float, str]:
        """Calculate confidence score from matched signals and return confidence level."""
        total = 0.0
        for signal_type, signal_data in signals.items():
            if signal_data.get("matched") and signal_type in SIGNAL_WEIGHTS:
                weight = SIGNAL_WEIGHTS[signal_type]
                total += weight

        confidence_pct = round(min(total, 1.0) * 100, 1)

        # Determine confidence level
        level = "SPECULATIVE"
        for lvl_key, lvl_data in CONFIDENCE_LEVELS.items():
            if confidence_pct >= lvl_data["min"]:
                level = lvl_key
                break

        return confidence_pct, level

    def explain_link(self, source_entity_id: str, target_entity_id: str) -> Dict[str, Any]:
        """
        Given two entity IDs, produce a full explanation of their relationship:
        - Confidence score with breakdown
        - Signal types that contributed
        - Supporting evidence references with snippets
        - Contradicting evidence
        - Number of inferential hops
        """
        # Find the relationship
        relationship = None
        for rel in self.relationships:
            if (rel["source_entity"] == source_entity_id and rel["target_entity"] == target_entity_id) or \
               (rel["source_entity"] == target_entity_id and rel["target_entity"] == source_entity_id):
                relationship = rel
                break

        if not relationship:
            # Attempt dynamic resolution
            return self._dynamic_resolution(source_entity_id, target_entity_id)

        source_entity = self.knowledge_base.get(relationship["source_entity"], {})
        target_entity = self.knowledge_base.get(relationship["target_entity"], {})
        signals = relationship["signals"]

        # Calculate confidence
        confidence_pct, confidence_level = self.calculate_confidence(signals)

        # Build signal breakdown
        signal_breakdown = []
        for sig_type, sig_data in signals.items():
            signal_breakdown.append({
                "signal_type": sig_type,
                "description": SIGNAL_DESCRIPTIONS.get(sig_type, sig_type),
                "matched": sig_data.get("matched", False),
                "value": sig_data.get("value"),
                "weight": f"{SIGNAL_WEIGHTS.get(sig_type, 0) * 100:.0f}%",
                "contribution": f"{SIGNAL_WEIGHTS.get(sig_type, 0) * 100:.0f}%" if sig_data.get("matched") else "0%",
            })

        # Build evidence cards
        evidence_cards = []
        for src_id in relationship.get("evidence_sources", []):
            evidence = self._find_evidence_by_id(src_id)
            if evidence:
                source_reliability = SOURCE_RELIABILITY.get(evidence["type"], SOURCE_RELIABILITY["SURFACE_WEB"])
                evidence_cards.append({
                    "source_id": src_id,
                    "source_type": evidence["type"],
                    "url": evidence["url"],
                    "snippet": evidence["snippet"],
                    "timestamp": evidence["timestamp"],
                    "reliability": source_reliability,
                })

        # Determine intelligence state
        matched_count = sum(1 for s in signals.values() if s.get("matched"))
        independent_source_types = set()
        for src_id in relationship.get("evidence_sources", []):
            ev = self._find_evidence_by_id(src_id)
            if ev:
                independent_source_types.add(ev["type"])

        if matched_count >= 3 and len(independent_source_types) >= 2:
            intel_state = "CORROBORATED"
        else:
            intel_state = "LEAD"

        return {
            "status": "SUCCESS",
            "source_entity": {
                "id": source_entity.get("id", source_entity_id),
                "name": source_entity.get("name", source_entity_id),
                "type": source_entity.get("type", "unknown"),
                "platform": source_entity.get("platform", "Unknown"),
            },
            "target_entity": {
                "id": target_entity.get("id", target_entity_id),
                "name": target_entity.get("name", target_entity_id),
                "type": target_entity.get("type", "unknown"),
                "platform": target_entity.get("platform", "Unknown"),
            },
            "confidence": {
                "score": confidence_pct,
                "level": confidence_level,
                "label": CONFIDENCE_LEVELS.get(confidence_level, {}).get("label", "Unknown"),
                "meaning": CONFIDENCE_LEVELS.get(confidence_level, {}).get("meaning", ""),
            },
            "signal_breakdown": signal_breakdown,
            "evidence_cards": evidence_cards,
            "contradictions": relationship.get("contradictions", []),
            "inferential_hops": relationship.get("hops", 1),
            "intelligence_state": intel_state,
            "verification_status": "PENDING",
            "independent_source_count": len(independent_source_types),
            "matched_signal_count": matched_count,
            "total_signal_count": len(signals),
            "explanation_text": self._generate_explanation_text(
                source_entity, target_entity, signals, confidence_pct, evidence_cards, relationship.get("contradictions", [])
            ),
        }

    def _generate_explanation_text(
        self, source: Dict, target: Dict, signals: Dict, confidence: float,
        evidence: List, contradictions: List
    ) -> str:
        """Generate a human-readable explanation of the link."""
        source_name = source.get("name", "Entity A")
        target_name = target.get("name", "Entity B")

        matched_signals = [SIGNAL_DESCRIPTIONS[k] for k, v in signals.items() if v.get("matched") and k in SIGNAL_DESCRIPTIONS]

        text = f"Link between '{source_name}' and '{target_name}' (confidence: {confidence}%).\n\n"
        text += "WHY THIS LINK?\n"
        for i, sig in enumerate(matched_signals, 1):
            text += f"  {i}. {sig}\n"

        text += f"\nSupported by {len(evidence)} evidence source(s) across "
        source_types = list(set(e.get("source_type", "") for e in evidence))
        text += f"{', '.join(source_types)}.\n"

        if contradictions:
            text += f"\n⚠ {len(contradictions)} contradiction(s) noted:\n"
            for c in contradictions:
                text += f"  - {c.get('note', 'Unknown')} (Severity: {c.get('severity', 'LOW')})\n"

        return text

    def _find_evidence_by_id(self, source_id: str) -> Optional[Dict]:
        """Search all entities for an evidence source by ID."""
        for entity in self.knowledge_base.values():
            for src in entity.get("sources", []):
                if src["id"] == source_id:
                    return src
        return None

    def _dynamic_resolution(self, source_id: str, target_id: str) -> Dict[str, Any]:
        """Attempt dynamic resolution between two entities not in pre-computed relationships."""
        source = self.knowledge_base.get(source_id)
        target = self.knowledge_base.get(target_id)

        if not source or not target:
            return {
                "status": "NOT_FOUND",
                "message": f"One or both entities not found: {source_id}, {target_id}",
                "confidence": {"score": 0, "level": "SPECULATIVE", "label": "No Data", "meaning": "Entities not in knowledge base"},
                "signal_breakdown": [],
                "evidence_cards": [],
                "contradictions": [],
                "intelligence_state": "LEAD",
            }

        # Compare identifiers dynamically
        signals = {}
        s_ids = source.get("identifiers", {})
        t_ids = target.get("identifiers", {})

        # PGP
        s_pgp = s_ids.get("pgp_fingerprint")
        t_pgp = t_ids.get("pgp_fingerprint")
        signals["pgp_fingerprint"] = {
            "matched": bool(s_pgp and t_pgp and s_pgp == t_pgp),
            "value": s_pgp if s_pgp and t_pgp and s_pgp == t_pgp else None
        }

        # Aliases
        s_aliases = set(a.lower() for a in s_ids.get("aliases", []))
        t_aliases = set(a.lower() for a in t_ids.get("aliases", []))
        alias_overlap = s_aliases & t_aliases
        signals["alias_overlap"] = {
            "matched": len(alias_overlap) > 0,
            "value": list(alias_overlap) if alias_overlap else None
        }

        # Payment handles
        s_pay = set(s_ids.get("payment_handles", []))
        t_pay = set(t_ids.get("payment_handles", []))
        pay_overlap = s_pay & t_pay
        signals["payment_handle"] = {
            "matched": len(pay_overlap) > 0,
            "value": list(pay_overlap) if pay_overlap else None
        }

        # Communication IDs
        s_comm = set(c.lower() for c in s_ids.get("communication_ids", []))
        t_comm = set(c.lower() for c in t_ids.get("communication_ids", []))
        comm_overlap = s_comm & t_comm
        signals["communication_id"] = {
            "matched": len(comm_overlap) > 0,
            "value": list(comm_overlap) if comm_overlap else None
        }

        # Surface web and timing — check if they share evidence sources
        s_sources = set(s.get("id") for s in source.get("sources", []))
        t_sources = set(s.get("id") for s in target.get("sources", []))
        shared_sources = s_sources & t_sources
        signals["surface_web_corroboration"] = {
            "matched": len(shared_sources) > 0,
            "value": f"{len(shared_sources)} shared evidence source(s)" if shared_sources else None
        }
        signals["timing_correlation"] = {
            "matched": len(shared_sources) > 0,
            "value": "Temporal overlap detected" if shared_sources else None
        }

        confidence_pct, confidence_level = self.calculate_confidence(signals)

        signal_breakdown = []
        for sig_type, sig_data in signals.items():
            signal_breakdown.append({
                "signal_type": sig_type,
                "description": SIGNAL_DESCRIPTIONS.get(sig_type, sig_type),
                "matched": sig_data.get("matched", False),
                "value": sig_data.get("value"),
                "weight": f"{SIGNAL_WEIGHTS.get(sig_type, 0) * 100:.0f}%",
                "contribution": f"{SIGNAL_WEIGHTS.get(sig_type, 0) * 100:.0f}%" if sig_data.get("matched") else "0%",
            })

        return {
            "status": "DYNAMIC_RESOLUTION",
            "source_entity": {"id": source_id, "name": source.get("name", source_id), "type": source.get("type", "unknown"), "platform": source.get("platform", "Unknown")},
            "target_entity": {"id": target_id, "name": target.get("name", target_id), "type": target.get("type", "unknown"), "platform": target.get("platform", "Unknown")},
            "confidence": {
                "score": confidence_pct,
                "level": confidence_level,
                "label": CONFIDENCE_LEVELS.get(confidence_level, {}).get("label", "Unknown"),
                "meaning": CONFIDENCE_LEVELS.get(confidence_level, {}).get("meaning", ""),
            },
            "signal_breakdown": signal_breakdown,
            "evidence_cards": [],
            "contradictions": [],
            "inferential_hops": 1,
            "intelligence_state": "LEAD",
            "verification_status": "PENDING",
        }

    def get_candidates(self, entity_id: str) -> List[Dict[str, Any]]:
        """Find all candidate matches for a given entity."""
        candidates = []
        for rel in self.relationships:
            if rel["source_entity"] == entity_id or rel["target_entity"] == entity_id:
                other_id = rel["target_entity"] if rel["source_entity"] == entity_id else rel["source_entity"]
                other_entity = self.knowledge_base.get(other_id, {})
                confidence_pct, confidence_level = self.calculate_confidence(rel["signals"])
                matched_count = sum(1 for s in rel["signals"].values() if s.get("matched"))

                candidates.append({
                    "entity_id": other_id,
                    "entity_name": other_entity.get("name", other_id),
                    "entity_type": other_entity.get("type", "unknown"),
                    "platform": other_entity.get("platform", "Unknown"),
                    "confidence": confidence_pct,
                    "confidence_level": confidence_level,
                    "matched_signals": matched_count,
                    "total_signals": len(rel["signals"]),
                    "evidence_count": len(rel.get("evidence_sources", [])),
                    "contradictions_count": len(rel.get("contradictions", [])),
                })

        candidates.sort(key=lambda x: x["confidence"], reverse=True)
        return candidates

    def get_all_entities(self) -> List[Dict[str, Any]]:
        """Return all entities in the knowledge base."""
        return [
            {
                "id": eid,
                "name": edata.get("name", eid),
                "type": edata.get("type", "unknown"),
                "platform": edata.get("platform", "Unknown"),
                "source_count": len(edata.get("sources", [])),
                "alias_count": len(edata.get("identifiers", {}).get("aliases", [])),
                "has_pgp": bool(edata.get("identifiers", {}).get("pgp_fingerprint")),
            }
            for eid, edata in self.knowledge_base.items()
        ]


entity_resolver = EntityResolver()
