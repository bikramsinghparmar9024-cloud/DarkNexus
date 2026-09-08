"""
Hugging Face / Open-Source Threat Classification & Intent Scorer.
Classifies intercepted messages and marketplace listings into threat levels:
- SEVERE (Active large-scale distribution, border smuggling, precursor labs)
- HIGH (Direct retail sales, escrow, dead-drop coordination)
- MEDIUM (Discussion of pricing, chemical synthesis, user inquiries)
- LOW (General mention, news repost, unrelated)

Also detects Modus Operandi (Dead-drop, Postal courier, Border concealment, Hawala/Crypto).
"""

from typing import Dict, Any, List, Tuple
import logging

logger = logging.getLogger("threat_classifier")

# Intent keywords with associated threat weights
SEVERITY_WEIGHTS = {
    "border": 30,
    "smuggling": 30,
    "precursor": 35,
    "chitta": 25,
    "heroin": 25,
    "bulk": 20,
    "kg": 20,
    "kilogram": 20,
    "dead-drop": 15,
    "escrow": 15,
    "tramadol": 15,
    "delivery": 10,
    "btc": 10,
    "xmr": 10,
    "stock": 10
}

MODUS_OPERANDI_PATTERNS = {
    "Dead-Drop Concealment": ["dead-drop", "drop location", "hidden spot", "gps coordinates", "behind brick"],
    "Postal / Parcel Courier": ["courier", "postal", "parcel", "speed post", "tracking id"],
    "Border Transit": ["border", "majitha", "attari", "fence", "riverine", "firozpur border", "drone"],
    "Cryptocurrency Laundering": ["btc", "bitcoin", "xmr", "monero", "crypto", "blockchain escrow"],
    "UPI / Cash Drop": ["upi", "qr code", "barcode", "cash on delivery", "cod"]
}


class ThreatClassifier:
    """Classifies threat severity, trafficking intent, and operational tactics."""

    def __init__(self):
        self.hf_pipeline = None
        self._hf_attempted = False

    def _init_hf_model(self):
        """Lazy loads Hugging Face pipeline if requested."""
        if self._hf_attempted:
            return
        self._hf_attempted = True
        try:
            from transformers import pipeline
            self.hf_pipeline = pipeline("zero-shot-classification", model="valhalla/distilbart-mnli-12-3", device=-1)
            logger.info("Loaded Hugging Face zero-shot classification pipeline.")
        except Exception as e:
            logger.info(f"Transformers zero-shot pipeline skipped ({e}). Using rule-based threat classifier.")
            self.hf_pipeline = None

    def classify(self, text: str) -> Dict[str, Any]:
        """Compute threat level, trafficking intent score, and detected modus operandi."""
        if not text:
            return {
                "threat_level": "LOW",
                "risk_score": 0,
                "intent": "INSUFFICIENT_DATA",
                "modus_operandi": []
            }

        text_lower = text.lower()

        # 1. Compute Base Risk Score (0 - 100)
        score = 0
        for keyword, weight in SEVERITY_WEIGHTS.items():
            if keyword in text_lower:
                score += weight

        score = min(score, 100)

        # 2. Assign Threat Level
        if score >= 65:
            threat_level = "SEVERE"
        elif score >= 40:
            threat_level = "HIGH"
        elif score >= 20:
            threat_level = "MEDIUM"
        else:
            threat_level = "LOW"

        # 3. Detect Modus Operandi tactics
        detected_tactics = []
        for tactic, patterns in MODUS_OPERANDI_PATTERNS.items():
            if any(p in text_lower for p in patterns):
                detected_tactics.append(tactic)

        # 4. Primary Trafficking Intent
        intent = "UNKNOWN"
        if "precursor" in text_lower or "acetic" in text_lower:
            intent = "PRECURSOR_CHEMICAL_ACQUISITION"
        elif any(k in text_lower for k in ["bulk", "wholesale", "5kg", "10kg"]):
            intent = "WHOLESALE_TRAFFICKING"
        elif any(k in text_lower for k in ["strip", "100mg", "gram", "retail", "price"]):
            intent = "RETAIL_DISTRIBUTION"
        elif any(k in text_lower for k in ["looking for", "need chitta", "buy"]):
            intent = "BUYER_DEMAND"
        else:
            intent = "COMMUNICATIONS_CHATTER"

        return {
            "threat_level": threat_level,
            "risk_score": score,
            "intent": intent,
            "modus_operandi": detected_tactics,
            "requires_immediate_action": threat_level in ["HIGH", "SEVERE"]
        }


threat_classifier = ThreatClassifier()
