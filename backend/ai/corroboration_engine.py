"""
Corroboration Engine — Assesses source reliability and independent support.
Auto-promotes LEAD → CORROBORATED when ≥2 independent sources agree.
Evaluates temporal correlation, contradictions, and produces structured reports.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import logging

logger = logging.getLogger("corroboration_engine")

# Source reliability matrix
SOURCE_RELIABILITY_MATRIX = {
    "DARK_WEB":     {"reliability": "MEDIUM",      "weight": 0.6, "adversarial_risk": "HIGH",   "note": "Content may be deceptive; vendor can be impersonated"},
    "TELEGRAM":     {"reliability": "MEDIUM",      "weight": 0.6, "adversarial_risk": "MEDIUM", "note": "Pseudonymous; channel admin controls narrative"},
    "SURFACE_WEB":  {"reliability": "LOW-MEDIUM",  "weight": 0.4, "adversarial_risk": "LOW",    "note": "Open source; may contain misinformation or planted data"},
    "FORENSIC":     {"reliability": "HIGH",        "weight": 0.9, "adversarial_risk": "LOW",    "note": "Lawfully acquired digital forensic artifact"},
    "CASE_DATA":    {"reliability": "HIGH",        "weight": 0.85,"adversarial_risk": "LOW",    "note": "Authorized investigation case record"},
    "BLOCKCHAIN":   {"reliability": "HIGH",        "weight": 0.8, "adversarial_risk": "LOW",    "note": "Immutable on-chain record; attribution separate from transaction"},
    "WIRETAP":      {"reliability": "VERY_HIGH",   "weight": 0.95,"adversarial_risk": "LOW",    "note": "Court-authorized lawful interception"},
}


class CorroborationEngine:
    """Evaluates evidence strength, independent source agreement, and contradiction detection."""

    def assess_relationship(
        self,
        evidence_sources: List[Dict[str, Any]],
        signals_matched: int,
        total_signals: int,
        contradictions: List[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Produce a corroboration assessment for a given relationship.

        Returns:
        - corroboration_level: UNCORROBORATED | PARTIALLY_CORROBORATED | CORROBORATED | STRONGLY_CORROBORATED
        - recommended_state: LEAD | CORROBORATED
        - evidence_strength: numerical score
        - independent_source_analysis: breakdown by source type
        """
        contradictions = contradictions or []

        # Count independent source types
        source_types = {}
        for src in evidence_sources:
            stype = src.get("source_type", src.get("type", "UNKNOWN"))
            if stype not in source_types:
                source_types[stype] = []
            source_types[stype].append(src)

        independent_count = len(source_types)

        # Calculate evidence strength (weighted by source reliability)
        total_weight = 0.0
        for stype, srcs in source_types.items():
            reliability = SOURCE_RELIABILITY_MATRIX.get(stype, SOURCE_RELIABILITY_MATRIX["SURFACE_WEB"])
            total_weight += reliability["weight"] * len(srcs)

        evidence_strength = min(round(total_weight / max(len(evidence_sources), 1) * 100, 1), 100)

        # Apply contradiction penalty
        contradiction_penalty = sum(
            10 if c.get("severity", "LOW") == "LOW" else 25
            for c in contradictions
        )
        evidence_strength = max(0, evidence_strength - contradiction_penalty)

        # Determine corroboration level
        if independent_count >= 3 and signals_matched >= 4:
            corroboration_level = "STRONGLY_CORROBORATED"
        elif independent_count >= 2 and signals_matched >= 3:
            corroboration_level = "CORROBORATED"
        elif independent_count >= 2 or signals_matched >= 2:
            corroboration_level = "PARTIALLY_CORROBORATED"
        else:
            corroboration_level = "UNCORROBORATED"

        # Recommend intelligence state
        if corroboration_level in ["CORROBORATED", "STRONGLY_CORROBORATED"]:
            recommended_state = "CORROBORATED"
        else:
            recommended_state = "LEAD"

        # Temporal analysis
        timestamps = []
        for src in evidence_sources:
            ts = src.get("timestamp")
            if ts:
                try:
                    timestamps.append(datetime.fromisoformat(ts.replace("Z", "+00:00")))
                except Exception:
                    pass

        temporal_span = None
        temporal_note = "Insufficient temporal data"
        if len(timestamps) >= 2:
            timestamps.sort()
            span = (timestamps[-1] - timestamps[0]).days
            temporal_span = f"{span} days"
            if span <= 7:
                temporal_note = "Tight temporal clustering (≤7 days) — strong temporal correlation"
            elif span <= 30:
                temporal_note = "Moderate temporal spread (≤30 days) — reasonable correlation"
            else:
                temporal_note = f"Wide temporal spread ({span} days) — weaker temporal signal"

        # Build source analysis
        source_analysis = []
        for stype, srcs in source_types.items():
            reliability = SOURCE_RELIABILITY_MATRIX.get(stype, SOURCE_RELIABILITY_MATRIX["SURFACE_WEB"])
            source_analysis.append({
                "source_type": stype,
                "count": len(srcs),
                "reliability": reliability["reliability"],
                "adversarial_risk": reliability["adversarial_risk"],
                "note": reliability["note"],
            })

        return {
            "corroboration_level": corroboration_level,
            "recommended_state": recommended_state,
            "evidence_strength": evidence_strength,
            "independent_source_count": independent_count,
            "total_evidence_count": len(evidence_sources),
            "signals_matched": signals_matched,
            "total_signals": total_signals,
            "source_analysis": source_analysis,
            "contradictions": contradictions,
            "contradiction_count": len(contradictions),
            "temporal_analysis": {
                "span": temporal_span,
                "note": temporal_note,
                "data_points": len(timestamps),
            },
            "assessment_timestamp": datetime.utcnow().isoformat() + "Z",
        }

    def should_auto_promote(self, assessment: Dict[str, Any]) -> bool:
        """Determine if a LEAD should be auto-promoted to CORROBORATED."""
        return assessment.get("recommended_state") == "CORROBORATED"


corroboration_engine = CorroborationEngine()
