"""
Category-Based Threat Scoring.

The previous scorer summed a flat list of keyword weights, which produced two
failures at once. Scores saturated - three or four terms reached the 100 cap,
so every serious record looked identical and none could be ranked. And the
ordering was inverted, because a single high-weight context word outscored a
genuine offer:

    "someone was talking about chitta near the border"          -> 55
    "500g chitta, dead drop Majitha, BTC escrow"                -> 50

A passing mention outranked a wholesale offer.

This scorer asks five separate questions instead, each capped independently:

    substance     what is being traded            (30)
    scale         how much of it                  (25)
    logistics     how it moves                    (20)
    payment       how it is paid for              (15)
    coordination  is a transaction being arranged (10)

Two properties follow. Synonyms stop double-counting - "chitta" and "heroin"
in one message describe one substance, not two. And breadth beats repetition:
a message covering four categories outranks one that mentions the same drug
four times, which is what an investigator triaging a queue actually needs.

Within a category the strongest signal counts in full and further signals add
at a reduced rate, so more evidence always helps but never runs away.
"""

from typing import Any, Dict, List, Optional, Tuple
import re

# ── Category ceilings; they sum to 100 ───────────────────────────────
CATEGORY_CAPS = {
    "substance": 30,
    "scale": 25,
    "logistics": 20,
    "payment": 15,
    "coordination": 10,
}

# Additional signals within a category count at this rate. Corroboration
# should strengthen a finding without letting one category dominate.
SECONDARY_SIGNAL_RATE = 0.3

# ── Substance weights, keyed to entity_extractor's drug categories ───
# Precursors rank highest: they enable production rather than one sale.
SUBSTANCE_WEIGHTS = {
    "Precursor Chemicals": 30,
    "Heroin / Chitta": 28,
    "Methamphetamine / Ice": 26,
    "Opium / Bhukki": 22,
    "Tramadol / Synthetic Opioids": 18,
}

# Slang categories that denote a substance, for terms the extractor missed.
SLANG_SUBSTANCE_CATEGORIES = {
    "NARCOTIC": 26,
    "SYNTHETIC_OPIOID": 18,
    "ADULTERANT": 14,
    "GENERAL_CONTRABAND": 12,
}

LOGISTICS_TERMS = {
    "drone": 20, "cross-border": 20, "border crossing": 20,
    "dead drop": 16, "dead-drop": 16, "drop point": 16, "drop location": 16,
    "concealed": 12, "hidden compartment": 14, "tubewell": 12,
    "courier": 12, "postal": 12, "parcel": 12, "speed post": 12,
    "consignment": 10, "transit": 10, "shipment": 10, "riverine": 14,
}

PAYMENT_TERMS = {
    "escrow": 15, "hawala": 14, "monero": 13, "xmr": 13,
    "bitcoin": 12, "btc": 12, "usdt": 11, "eth": 11, "crypto": 11,
    "upi": 8, "qr code": 8, "barcode": 8, "paytm": 8,
    "cash on delivery": 6, "cod": 6, "advance payment": 9,
}

COORDINATION_TERMS = {
    "rate list": 10, "price list": 10, "rate daso": 10,
    "send location": 9, "gps": 9, "coordinates": 9,
    "tonight": 7, "tomorrow": 6, "pickup time": 8, "meet": 6,
    "confirm order": 10, "place order": 10, "dm me": 8, "contact me": 7,
}

SCALE_TERMS_WITHOUT_NUMBER = {
    "wholesale": 15, "bulk": 15, "commercial quantity": 20,
    "fresh stock": 10, "restock": 10, "container": 18,
}

# Quantities normalised to grams, then banded. Bands rather than a continuous
# curve because the underlying extraction is approximate.
_QUANTITY_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(kg|kilo|kilogram|kilograms|g|gm|gram|grams|"
    r"ton|tonne|strips?|packets?|pills?|tablets?)\b",
    re.IGNORECASE,
)
_UNIT_GRAMS = {
    "ton": 1_000_000, "tonne": 1_000_000,
    "kg": 1000, "kilo": 1000, "kilogram": 1000, "kilograms": 1000,
    "g": 1, "gm": 1, "gram": 1, "grams": 1,
}
# Counted items are not weights; treated as retail units.
_COUNT_UNITS = {"strip", "strips", "packet", "packets", "pill", "pills",
                "tablet", "tablets"}

QUANTITY_BANDS = [
    (1_000_000, 25, "tonne-scale"),
    (10_000, 25, "10kg or more"),
    (1_000, 22, "kilogram-scale"),
    (100, 16, "100g or more"),
    (10, 11, "10g or more"),
    (0, 6, "small retail quantity"),
]

THREAT_BANDS = [(70, "SEVERE"), (45, "HIGH"), (22, "MEDIUM"), (0, "LOW")]


def level_from_score(score: int) -> str:
    for threshold, level in THREAT_BANDS:
        if score >= threshold:
            return level
    return "LOW"


def _score_category(matches: List[Tuple[str, int]], cap: int) -> Tuple[int, List[str]]:
    """
    Strongest signal in full, the rest at a reduced rate, capped.

    This is what stops a message repeating one idea from outscoring a message
    that demonstrates several.
    """
    if not matches:
        return 0, []
    ordered = sorted(matches, key=lambda m: m[1], reverse=True)
    total = ordered[0][1] + SECONDARY_SIGNAL_RATE * sum(w for _, w in ordered[1:])
    return int(min(round(total), cap)), [name for name, _ in ordered]


def _find_terms(text: str, table: Dict[str, int]) -> List[Tuple[str, int]]:
    return [(term, weight) for term, weight in table.items() if term in text]


def _score_quantity(text: str) -> Tuple[int, List[str]]:
    """Largest quantity mentioned, banded. Counted units are retail-scale."""
    best_grams = 0.0
    best_label: Optional[str] = None
    retail_units = 0

    for amount, unit in _QUANTITY_RE.findall(text):
        unit_lower = unit.lower()
        try:
            value = float(amount)
        except ValueError:
            continue
        if unit_lower in _COUNT_UNITS:
            retail_units = max(retail_units, value)
            continue
        grams = value * _UNIT_GRAMS.get(unit_lower, 0)
        if grams > best_grams:
            best_grams, best_label = grams, f"{amount}{unit_lower}"

    if best_grams > 0:
        for threshold, points, description in QUANTITY_BANDS:
            if best_grams >= threshold:
                return points, [f"{best_label} ({description})"]

    if retail_units >= 1000:
        return 20, [f"{int(retail_units)} units (commercial count)"]
    if retail_units >= 100:
        return 14, [f"{int(retail_units)} units"]
    if retail_units > 0:
        return 7, [f"{int(retail_units)} units"]
    return 0, []


def score_threat(text: str,
                 entities: Optional[Dict[str, Any]] = None,
                 detected_slang: Optional[List[Dict[str, Any]]] = None
                 ) -> Dict[str, Any]:
    """
    Score an intercept across five categories.

    Returns the total, the band, and a per-category breakdown naming the
    signals that contributed - a score an analyst cannot inspect is not
    something they can defend.
    """
    text_lower = (text or "").lower()
    entities = entities or {}
    detected_slang = detected_slang or []

    # ── Substance ────────────────────────────────────────────────────
    substance_matches: List[Tuple[str, int]] = []
    for drug in entities.get("drugs", []) or []:
        weight = SUBSTANCE_WEIGHTS.get(drug)
        if weight:
            substance_matches.append((drug, weight))

    # Slang covers vocabulary the extractor's categories do not.
    if not substance_matches:
        for slang in detected_slang:
            weight = SLANG_SUBSTANCE_CATEGORIES.get(slang.get("category"))
            if weight:
                substance_matches.append(
                    (slang.get("forensic_term", slang.get("original_term", "slang")), weight))

    substance_score, substance_terms = _score_category(
        substance_matches, CATEGORY_CAPS["substance"])

    # ── Scale ────────────────────────────────────────────────────────
    quantity_score, quantity_terms = _score_quantity(text_lower)
    bulk_matches = _find_terms(text_lower, SCALE_TERMS_WITHOUT_NUMBER)
    bulk_score, bulk_terms = _score_category(bulk_matches, CATEGORY_CAPS["scale"])
    scale_score = min(max(quantity_score, bulk_score)
                      + int(SECONDARY_SIGNAL_RATE * min(quantity_score, bulk_score)),
                      CATEGORY_CAPS["scale"])
    scale_terms = quantity_terms + bulk_terms

    # ── Logistics, payment, coordination ─────────────────────────────
    logistics_score, logistics_terms = _score_category(
        _find_terms(text_lower, LOGISTICS_TERMS), CATEGORY_CAPS["logistics"])

    payment_matches = _find_terms(text_lower, PAYMENT_TERMS)
    wallets = entities.get("crypto_wallets") or {}
    if any(addrs for addrs in wallets.values() if isinstance(addrs, (list, tuple))):
        payment_matches.append(("crypto address present", 12))
    if entities.get("upi_ids"):
        payment_matches.append(("UPI identifier present", 8))
    payment_score, payment_terms = _score_category(
        payment_matches, CATEGORY_CAPS["payment"])

    coordination_matches = _find_terms(text_lower, COORDINATION_TERMS)
    if entities.get("phones") or entities.get("handles"):
        coordination_matches.append(("direct contact identifier present", 7))
    coordination_score, coordination_terms = _score_category(
        coordination_matches, CATEGORY_CAPS["coordination"])

    categories = {
        "substance": {"score": substance_score, "max": CATEGORY_CAPS["substance"],
                      "signals": substance_terms},
        "scale": {"score": scale_score, "max": CATEGORY_CAPS["scale"],
                  "signals": scale_terms},
        "logistics": {"score": logistics_score, "max": CATEGORY_CAPS["logistics"],
                      "signals": logistics_terms},
        "payment": {"score": payment_score, "max": CATEGORY_CAPS["payment"],
                    "signals": payment_terms},
        "coordination": {"score": coordination_score, "max": CATEGORY_CAPS["coordination"],
                         "signals": coordination_terms},
    }

    total = sum(c["score"] for c in categories.values())
    total = int(min(total, 100))

    return {
        "risk_score": total,
        "threat_level": level_from_score(total),
        "categories": categories,
        "categories_triggered": [name for name, c in categories.items() if c["score"] > 0],
        "explanation": _explain(categories, total),
    }


def _explain(categories: Dict[str, Any], total: int) -> str:
    parts = []
    for name, c in categories.items():
        if c["score"] > 0:
            signals = ", ".join(str(s) for s in c["signals"][:3])
            parts.append(f"{name} {c['score']}/{c['max']} ({signals})")
    if not parts:
        return "No scoring signals found."
    return f"Score {total}/100 from " + "; ".join(parts) + "."
