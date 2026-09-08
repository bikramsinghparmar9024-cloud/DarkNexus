"""
spaCy Named Entity Recognition (NER) & Regional Slang Extractor.
Extracts entities specific to Punjab drug trafficking:
- Illicit Narcotics & Regional Slang: Chitta, Bhukki, Smack, Heroin, Opium/Afeem, Tramadol, Ice/Meth, Precursor
- Punjab Border Locations & Supply Hubs: Amritsar, Majitha, Tarn Taran, Jalandhar, Ludhiana, Bathinda, Firozpur, Fazilka, Mohali
- Contact Identifiers: Indian mobile numbers (+91, 10-digit), Telegram usernames (@...), Wickr/Signal handles
- Financial Identifiers: Bitcoin (BTC), Ethereum (ETH), Monero (XMR), UPI IDs (@upi, @paytm)
- Quantity & Pricing: Grams, kg, strips, packets, rupee amounts, BTC prices
"""

import re
from typing import Dict, Any, List, Set
import logging

logger = logging.getLogger("entity_extractor")

# ── Regional Drug Lexicon, in two tiers ──────────────────────────────
#
# The lexicon used to be one flat list, which meant "white", "powder", "post",
# "ice", "crystal" and "strip" each identified a narcotic on their own. The
# result was that
#
#     "I saw a white car parked near the post office"
#
# extracted as heroin and opium. That is not merely a noisy tag: the narcotics
# gate in ai/enrichment.py decides whether a record is drug intelligence by
# asking whether this list matched, so an ordinary sentence containing "post"
# disarmed the gate and unlocked border escalation.
#
# Terms are now separated by how much they mean on their own.

# Tier 1 - unambiguous. In running text these name a controlled substance and
# little else, so a single match is sufficient.
SPECIFIC_DRUG_PATTERNS = {
    "Heroin / Chitta": [
        r"\bchitta\b", r"\bheroin\b", r"\bsmack\b", r"\bचिट्टा\b",
    ],
    "Opium / Bhukki": [
        r"\bbhukki\b", r"\bopium\b", r"\bafeem\b", r"\bpoppy[- ]?straw\b",
        r"\bdoda\b", r"\bअफीम\b",
    ],
    "Tramadol / Synthetic Opioids": [
        r"\btramadol\b", r"\bultram\b", r"\bparvorin\b",
    ],
    "Methamphetamine / Ice": [
        r"\bmeth\b", r"\bmethamphetamine\b", r"\bmdma\b", r"\bshabu\b",
        r"\bmeow[- ]?meow\b",
    ],
    "Precursor Chemicals": [
        r"\bacetic anhydride\b", r"\bephedrine\b", r"\bpseudoephedrine\b",
        r"\bprecursor\b",
    ],
}

# Tier 2 - genuine street vocabulary that is also ordinary English. These are
# recorded only when the surrounding text shows a transaction: a quantity, a
# price, dealing language, or a tier-1 term. "500g of white" is narcotics;
# "white fence" is not.
GENERIC_DRUG_PATTERNS = {
    "Heroin / Chitta": [r"\bpowder\b", r"\bgrade[- ]?a\b", r"\bwhite\b"],
    "Opium / Bhukki": [r"\bpost\b"],
    "Tramadol / Synthetic Opioids": [r"\btol\b", r"\b100\s?mg\b", r"\b200\s?mg\b",
                                     r"\bstrips?\b"],
    "Methamphetamine / Ice": [r"\bice\b", r"\bcrystal\b"],
}

# Evidence that the text concerns a transaction rather than daily life.
DRUG_CONTEXT_PATTERNS = [
    # Quantities and money
    r"\b\d+(?:\.\d+)?\s?(?:kg|kilo|gram|grams|gm|g)\b",
    r"\b\d+\s?(?:strips?|packets?|pills?|tablets?)\b",
    r"(?:₹|rs\.?|inr)\s*[\d,]+", r"\b\d+(?:\.\d+)?\s*(?:btc|eth|usdt)\b",
    # Dealing language
    r"\bfor sale\b", r"\bavailable\b", r"\bin stock\b", r"\bwholesale\b",
    r"\bbulk\b", r"\bsupply\b", r"\bdelivery\b", r"\bdead[- ]?drop\b",
    r"\bdrop point\b", r"\bescrow\b", r"\bconsignment\b", r"\bcourier\b",
    r"\bstock\b", r"\bmaal\b", r"\bsell(?:ing|er)?\b", r"\bpurity\b",
    r"\bcut with\b", r"\bsmuggl", r"\btraffick", r"\bseiz(?:ed|ure)\b",
    r"\bnarcotic", r"\bcontraband\b", r"\bndps\b",
]

_CONTEXT_RE = re.compile("|".join(DRUG_CONTEXT_PATTERNS), re.IGNORECASE)

# Kept for callers that want the whole vocabulary, e.g. scoring explanations.
DRUG_PATTERNS = {
    category: SPECIFIC_DRUG_PATTERNS.get(category, [])
              + GENERIC_DRUG_PATTERNS.get(category, [])
    for category in set(SPECIFIC_DRUG_PATTERNS) | set(GENERIC_DRUG_PATTERNS)
}


def detect_drugs(text: str) -> Dict[str, Any]:
    """
    Identify substances, distinguishing certain matches from contextual ones.

    Returns the categories found, plus which tier established each one, so a
    reviewer can see whether a finding rests on the word "chitta" or on the
    word "white" next to a weight.
    """
    lowered = (text or "").lower()
    has_context = bool(_CONTEXT_RE.search(lowered))

    categories: List[str] = []
    basis: Dict[str, Dict[str, Any]] = {}

    for category, patterns in SPECIFIC_DRUG_PATTERNS.items():
        hits = [p for p in patterns if re.search(p, lowered, re.IGNORECASE)]
        if hits:
            categories.append(category)
            basis[category] = {"tier": "SPECIFIC", "matched": len(hits)}

    # A tier-1 hit anywhere is itself sufficient context for tier-2 terms:
    # once "chitta" is on the page, "white" is almost certainly the same thing.
    context_available = has_context or bool(categories)

    for category, patterns in GENERIC_DRUG_PATTERNS.items():
        if category in basis:
            continue
        hits = [p for p in patterns if re.search(p, lowered, re.IGNORECASE)]
        if not hits:
            continue
        if context_available:
            categories.append(category)
            basis[category] = {"tier": "CONTEXTUAL", "matched": len(hits)}
        else:
            basis.setdefault("_rejected", {})[category] = (
                "street term present but no transaction context")

    return {"categories": categories, "basis": basis}

# Key Punjab Border & Distribution Districts
PUNJAB_LOCATIONS = [
    "Amritsar", "Majitha", "Tarn Taran", "Attari", "Wagah",
    "Jalandhar", "Ludhiana", "Bathinda", "Firozpur", "Fazilka",
    "Pathankot", "Gurdaspur", "Mohali", "Patiala", "Moga",
    "Kapurthala", "Hoshiarpur", "Muktsar", "Barnala", "Rupnagar"
]

# Regex patterns for contacts & financials
#
# The boundaries on the phone pattern are load-bearing. `\b` at the end alone
# let the match slide into the middle of any longer digit run, so
# "ISBN 978-8185107769" was extracted as the phone number 8185107769 - and a
# fabricated identifier is worse than a missed one, because correlation treats
# a shared phone as hard evidence linking two records. Hyphens are excluded on
# both sides as well as digits, since ISBNs, order numbers and reference codes
# are routinely written in hyphenated groups.
PHONE_REGEX = re.compile(r"(?<![\d-])(?:\+91[\s-]?)?[6789]\d{9}(?![\d-])")
# A Telegram username starts with a letter and is preceded by whitespace or
# punctuation - never by another identifier character. Without the lookbehind
# the pattern matched the tail of any address-like string, so "yD@UFgDF" in a
# block of undecoded binary yielded the handle "@UFgDF".
TELEGRAM_HANDLE_REGEX = re.compile(
    r"(?<![A-Za-z0-9_@.])@([a-zA-Z][a-zA-Z0-9_]{4,31})\b")
BTC_REGEX = re.compile(r"\b(bc1[a-zA-HJ-NP-Z0-9]{25,39}|[13][a-km-zA-HJ-NP-Z1-9]{25,34})\b")
ETH_REGEX = re.compile(r"\b(0x[a-fA-F0-9]{40})\b")
# A UPI virtual payment address ends in a payment-provider handle, and the set
# of those is small and public. Matching "anything@anything" instead treated
# every email address - and every address-shaped fragment of binary - as a
# payment identifier, which then became a suspect's financial account in the
# actor dossiers.
UPI_PROVIDERS = (
    "upi|paytm|ybl|okhdfcbank|okicici|okaxis|oksbi|axl|ibl|apl|abfspay|"
    "airtel|freecharge|jupiteraxis|yapl|hdfcbank|icici|sbi|pnb|barodampay|"
    "kotak|indus|idfcbank|federal|rbl|dbs|cnrb|uboi|unionbank|jio|fam|slice|"
    "naviaxis|timecosmos|waaxis|yesbank|myicici"
)
UPI_REGEX = re.compile(
    r"(?<![A-Za-z0-9_@.])([a-zA-Z0-9][a-zA-Z0-9.\-_]{1,60}@(?:" + UPI_PROVIDERS + r"))\b",
    re.IGNORECASE,
)
# PGP fingerprints are the strongest identity signal on darknet markets:
# vendors publish them deliberately so buyers can verify who they are, which
# means the same fingerprint under two aliases is near-conclusive. A v4
# fingerprint is 40 hex characters, conventionally shown in ten 4-char groups.
PGP_FINGERPRINT_REGEX = re.compile(
    r"\b(?:[0-9A-Fa-f]{4}[ \t-]?){9}[0-9A-Fa-f]{4}\b"
)
PGP_BLOCK_REGEX = re.compile(r"-----BEGIN PGP (?:PUBLIC KEY|SIGNED MESSAGE)", re.I)

PRICE_REGEX = re.compile(r"(?:₹|rs\.?|inr)\s*[\d,]+|\b\d+(?:\.\d+)?\s*(?:btc|eth|usdt)\b|\b\d+\s*(?:grams?|gm|kg|kilo|strips?|pills?)\b", re.IGNORECASE)

# Try loading spaCy
try:
    import spacy
    try:
        nlp = spacy.load("en_core_web_sm")
    except Exception:
        nlp = spacy.blank("en")
except ImportError:
    nlp = None


class EntityExtractor:
    """Extracts domain-specific entities from text using rules, regex, and spaCy NER."""

    def extract_entities(self, text: str) -> Dict[str, Any]:
        """Alias for extract()."""
        return self.extract(text)

    def extract(self, text: str) -> Dict[str, Any]:
        """Extract structured intelligence entities from intercept text."""
        if not text:
            return {
                "drugs": [],
                "drug_basis": {},
                "locations": [],
                "phones": [],
                "handles": [],
                "crypto_wallets": {"btc": [], "eth": []},
                "crypto_wallets_unverified": [],
                "upi_ids": [],
                "pgp_fingerprints": [],
                "has_pgp_block": False,
                "quantities_and_prices": [],
                "spacy_entities": []
            }

        text_lower = text.lower()

        # 1. Drug Slang Match, tiered so ordinary English does not read as
        #    narcotics. `drug_basis` records why each category was accepted.
        drug_detection = detect_drugs(text)
        detected_drugs = drug_detection["categories"]

        # 2. Punjab Locations Match
        detected_locations = []
        for loc in PUNJAB_LOCATIONS:
            if re.search(r"\b" + re.escape(loc) + r"\b", text, re.IGNORECASE):
                detected_locations.append(loc)

        # 3. Contact Identifiers
        phones = list(set(PHONE_REGEX.findall(text)))
        handles = list(set(TELEGRAM_HANDLE_REGEX.findall(text)))

        # 4. Financial Identifiers
        #
        # Regex matches the shape; the checksum decides whether it is really an
        # address. Text reaching this system passes through OCR, re-typing and
        # truncation, all of which produce address-shaped strings that are not
        # addresses. Only verified ones are exposed for tracing and linking;
        # the rest are kept separately so the observation is not lost.
        from ai.crypto_validation import partition_addresses

        btc_wallets, btc_unverified = partition_addresses(
            list(set(BTC_REGEX.findall(text))), "BTC")
        eth_wallets, eth_unverified = partition_addresses(
            list(set(ETH_REGEX.findall(text))), "ETH")
        upi_ids = [u for u in UPI_REGEX.findall(text) if not u.endswith(".com") and not u.endswith(".org")]

        # 5. Quantity & Pricing
        prices = list(set(PRICE_REGEX.findall(text)))

        # 5b. PGP identity material
        pgp_fingerprints = []
        for raw in PGP_FINGERPRINT_REGEX.findall(text):
            normalized = re.sub(r"[ \t-]", "", raw).upper()
            if len(normalized) == 40:
                pgp_fingerprints.append(normalized)
        pgp_fingerprints = list(set(pgp_fingerprints))
        has_pgp_block = bool(PGP_BLOCK_REGEX.search(text))

        # Regional slang, resolved before the NER pass so its output can be
        # used to filter the model's misfires.
        from ai.punjabi_slang import punjabi_normalizer
        from ai.geo_resolver import extract_geo_markers_from_text
        slang_data = punjabi_normalizer.normalize(text)

        # 6. spaCy NER - ADVISORY ONLY.
        #
        # The model is English-trained and misfires badly on Romanized
        # Punjabi: it tags the place "Attari" as an ORG and the slang phrase
        # "barcode bhejo" as a PERSON. Feeding that into identity resolution
        # would manufacture suspects out of street vocabulary, so this output
        # is surfaced for an analyst and never used for scoring or linking.
        #
        # The filter below removes the obvious misfires: anything that is
        # already known to be a place, a drug term or regional slang.
        spacy_ents = []
        if nlp:
            try:
                doc = nlp(text[:2500])
                known_locations = {loc.lower() for loc in PUNJAB_LOCATIONS}
                slang_words = set()
                for term in (s.get("original_term", "") for s in slang_data["detected_slang"]):
                    slang_words.update(term.lower().split())

                for ent in doc.ents:
                    if ent.label_ not in ("PERSON", "ORG", "GPE", "MONEY"):
                        continue
                    candidate = ent.text.strip()
                    lowered = candidate.lower()

                    # Drop entities the domain vocabulary already explains.
                    if lowered in known_locations:
                        continue
                    if any(word in slang_words for word in lowered.split()):
                        continue
                    if ent.label_ == "PERSON" and len(candidate.split()) < 2:
                        continue  # single tokens are mostly noise here

                    spacy_ents.append({
                        "text": candidate,
                        "label": ent.label_,
                        "confidence": "ADVISORY",
                    })
            except Exception as e:
                logger.debug(f"spaCy pass failed: {e}")

        # 7. Border geospatial resolution
        geo_markers = extract_geo_markers_from_text(text)
        border_danger = any(m.get("in_critical_border_corridor", False) for m in geo_markers)

        return {
            "drugs": list(set(detected_drugs)),
            # Why each substance was accepted - SPECIFIC (the word names the
            # drug) or CONTEXTUAL (street term supported by transaction
            # language). A reviewer should be able to tell the two apart.
            "drug_basis": drug_detection["basis"],
            "locations": list(set(detected_locations)),
            "phones": phones,
            "handles": [f"@{h}" for h in handles],
            "crypto_wallets": {
                "btc": btc_wallets,
                "eth": eth_wallets
            },
            # Address-shaped strings that failed checksum validation. Present
            # so an analyst can see that a wallet was referenced, without the
            # bad transcription being traced or cited as fact.
            "crypto_wallets_unverified": btc_unverified + eth_unverified,
            "upi_ids": upi_ids,
            "pgp_fingerprints": pgp_fingerprints,
            "has_pgp_block": has_pgp_block,
            "quantities_and_prices": prices,
            "spacy_entities": spacy_ents,
            "regional_slang_detected": slang_data["detected_slang"],
            "geo_markers": geo_markers,
            "in_critical_border_zone": border_danger
        }


entity_extractor = EntityExtractor()
