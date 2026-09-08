"""
Regional Punjabi & Gurmukhi Narcotics Slang Normalization Engine.
Solves the regional language bottleneck for Punjab Police:
Translates and normalizes Romanized-Punjabi, Gurmukhi, and code-mixed slang
into standardized forensic English terminology.
"""

import re
from typing import Dict, Any, List, Tuple

# Comprehensive Slang Dictionary: [Pattern -> (Standard Term, Category, Threat Weight)]
REGIONAL_SLANG_MAP = {
    # ── Substances & Narcotics ──────────────────────────────────
    r"\bchitta\b": ("Heroin (Diacetylmorphine)", "NARCOTIC", 35),
    r"\bचिट्टा\b": ("Heroin (Diacetylmorphine)", "NARCOTIC", 35),
    r"\bਚਿੱਟਾ\b": ("Heroin (Diacetylmorphine)", "NARCOTIC", 35),
    r"\bafeem\b": ("Opium Raw", "NARCOTIC", 25),
    r"\bਅਫ਼ੀਮ\b": ("Opium Raw", "NARCOTIC", 25),
    r"\bbhukki\b": ("Poppy Husk / Straw", "NARCOTIC", 20),
    r"\bਭੁੱਕੀ\b": ("Poppy Husk / Straw", "NARCOTIC", 20),
    r"\bdoda\b": ("Crushed Poppy Heads", "NARCOTIC", 20),
    r"\bpost\b": ("Poppy Straw", "NARCOTIC", 20),
    r"\bkaal\b": ("Black Tar Heroin", "NARCOTIC", 30),
    r"\bmaal\b": ("Illicit Consignment", "GENERAL_CONTRABAND", 15),
    r"\bsaman\b": ("Drug Consignment", "GENERAL_CONTRABAND", 15),
    r"\bsaaman\b": ("Drug Consignment", "GENERAL_CONTRABAND", 15),
    r"\bgoli\b": ("Intoxication Pills / Tramadol", "SYNTHETIC_OPIOID", 20),
    r"\btol\b": ("Tramadol Capsules", "SYNTHETIC_OPIOID", 20),
    r"\bchitti goli\b": ("Alprazolam / Sedative Tablets", "SYNTHETIC_OPIOID", 15),
    r"\bkutta\b": ("Low Grade Heroin Adulterant", "ADULTERANT", 15),

    # ── Deals & Transactions ───────────────────────────────────
    r"\bveere\b": ("Brother / Peer contact", "COLLOQUIAL", 5),
    r"\bmiluga\b": ("Is it available? (Demand inquiry)", "TRANSACTION_INQUIRY", 10),
    r"\bmil jau\b": ("Will be available (Supply affirmation)", "TRANSACTION_SUPPLY", 15),
    r"\brate daso\b": ("Quote price / Quotation inquiry", "TRANSACTION_INQUIRY", 15),
    r"\brate ki aa\b": ("What is the current rate?", "TRANSACTION_INQUIRY", 15),
    r"\badvance pay\b": ("Advance payment demanded", "PAYMENT", 15),
    r"\bkhata bhejo\b": ("Send bank / UPI account details", "PAYMENT", 20),
    r"\bbarcode bhejo\b": ("Send QR code for UPI transaction", "PAYMENT", 20),
    r"\bdead drop\b": ("Concealed Dead-Drop delivery", "MODUS_OPERANDI", 25),
    r"\blukoya\b": ("Concealed / Hidden", "MODUS_OPERANDI", 15),
    r"\bchupa dita\b": ("Hidden at drop spot", "MODUS_OPERANDI", 20),
    r"\beithay pohnch\b": ("Reach this location", "COORDINATION", 10),
    r"\bpind ch\b": ("Inside village boundary", "LOCATION_CONTEXT", 10),
    r"\bborder vall\b": ("Towards International Border", "BORDER_CORRIDOR", 30),
    r"\bmajitha vall\b": ("Majitha Transit Line", "BORDER_CORRIDOR", 25),
    r"\btarn taran vall\b": ("Tarn Taran Transit Line", "BORDER_CORRIDOR", 25)
}


class PunjabiSlangNormalizer:
    """Normalizes Romanized Punjabi and Gurmukhi narcotics chatter into English forensic context."""

    def normalize(self, text: str) -> Dict[str, Any]:
        """Detect and translate regional slang phrases."""
        if not text:
            return {"normalized_text": "", "detected_slang": [], "threat_boost": 0}

        text_lower = text.lower()
        normalized_tokens = text
        detected_slang = []
        threat_boost = 0

        for pattern, (standard_term, category, weight) in REGIONAL_SLANG_MAP.items():
            matches = list(re.finditer(pattern, text_lower))
            if matches:
                detected_slang.append({
                    "original_term": matches[0].group(),
                    "forensic_term": standard_term,
                    "category": category,
                    "weight": weight
                })
                threat_boost += weight
                # Annotate normalized text inline for NLP understanding
                normalized_tokens = re.sub(
                    pattern,
                    f"{matches[0].group()} [{standard_term}]",
                    normalized_tokens,
                    flags=re.IGNORECASE
                )

        return {
            "original_text": text,
            "normalized_text": normalized_tokens,
            "detected_slang": detected_slang,
            "slang_count": len(detected_slang),
            "threat_boost": min(threat_boost, 50)
        }


punjabi_normalizer = PunjabiSlangNormalizer()


def normalize_punjabi_slang(text: str) -> Dict[str, Any]:
    """Convenience helper to normalize Punjabi/Gurmukhi slang."""
    return punjabi_normalizer.normalize(text)
