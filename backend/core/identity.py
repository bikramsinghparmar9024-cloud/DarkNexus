"""
Canonical entity identity - the single place node keys are made.

Entity keys were being built inline in at least three modules, each with its
own rules, and the results did not agree. For one handle:

    ai/enrichment.py   ->  suspect_Jagga_Drops     (no lowercasing)
    ai/entity_store.py ->  actor_jagga_drops       (different prefix too)

Those can never match, which is why the "Why This Link?" panel returned 404
for suspects that plainly existed: the graph and the entity resolver were
describing the same person under two names and neither could find the other.

Wallet keys were worse. They used the first twelve characters of the address,
so two different wallets sharing a prefix collapsed into one node - the graph
would claim two vendors shared a payment account when they did not. A node key
that can merge two real, distinct entities is a correctness bug, not a
formatting preference.

Rules
-----
* One function makes every key. Nothing constructs one by hand.
* Wallets keep their full address, so distinct wallets stay distinct.
* Drug names pass through an alias table first, so "chitta", "Chitta" and
  "Heroin / Chitta" become one node rather than three.
* Everything is lowercased and punctuation-normalised, so case or spacing
  differences never split one entity into several nodes.
"""

from typing import Dict, Optional
from pathlib import Path
import hashlib
import json
import logging
import re
import threading

logger = logging.getLogger("identity")

# Entity types this module knows how to key. Anything else is still accepted,
# but is logged, because an unexpected type usually means a caller invented a
# category and its nodes will not join up with anyone else's.
KNOWN_TYPES = {"suspect", "vendor", "drug", "wallet", "intercept",
               "phone", "upi", "pgp", "device", "location"}

# Types whose value is an identifier that must never be shortened or
# case-folded away. Two wallets differing only in case are two wallets.
_CASE_SENSITIVE_TYPES = {"wallet", "pgp"}

# Above this length a key is replaced by a hash, so the database column
# (255 chars) can never be overflowed by a long identifier.
MAX_KEY_LENGTH = 200

_ALIAS_PATH = Path(__file__).resolve().parent.parent / "data" / "drug_aliases.json"
_alias_lock = threading.Lock()
_alias_cache: Optional[Dict[str, str]] = None


def _load_drug_aliases() -> Dict[str, str]:
    """
    Load the alias-to-canonical-name table.

    Kept in a JSON file rather than in Python so new street vocabulary can be
    added without a code change or a redeploy - which matters, because slang
    is exactly the thing that changes between one operation and the next.
    """
    global _alias_cache
    with _alias_lock:
        if _alias_cache is not None:
            return _alias_cache
        try:
            with open(_ALIAS_PATH, encoding="utf-8") as handle:
                raw = json.load(handle)
            table: Dict[str, str] = {}
            for canonical, aliases in raw.get("substances", {}).items():
                table[_normalize_text(canonical)] = canonical
                for alias in aliases:
                    table[_normalize_text(alias)] = canonical
            _alias_cache = table
            logger.info("Loaded %d drug aliases mapping to %d substances",
                        len(table), len(raw.get("substances", {})))
        except Exception as e:
            logger.error("Could not load drug aliases from %s: %s", _ALIAS_PATH, e)
            _alias_cache = {}
        return _alias_cache


def reload_drug_aliases() -> Dict[str, str]:
    """Drop the cached table so an edited file takes effect without a restart."""
    global _alias_cache
    with _alias_lock:
        _alias_cache = None
    return _load_drug_aliases()


def canonical_drug_name(raw_value: str) -> str:
    """
    Map any spelling of a substance to its canonical name.

    "chitta", "Chitta", "Heroin / Chitta" and "smack" are one substance. Left
    unnormalised they became four separate nodes, and the graph showed a
    network fragmented across spellings of the same drug.
    """
    normalized = _normalize_text(raw_value)
    return _load_drug_aliases().get(normalized, raw_value.strip())


def _normalize_text(value: str) -> str:
    """Lowercase, strip @, collapse anything non-alphanumeric to one underscore."""
    text = (value or "").replace("@", " ").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def slugify_entity_key(raw_value: str, entity_type: str) -> str:
    """
    Build the canonical node key for an entity.

    This is the only function permitted to construct an entity key. Every
    caller - graph writes, the entity resolver, correlation - must use it, so
    that the same real-world thing always produces the same key no matter
    which code path saw it first.
    """
    entity_type = (entity_type or "entity").strip().lower()
    if entity_type not in KNOWN_TYPES:
        logger.debug("Unrecognised entity type %r; keys of this type will only "
                     "match other callers using the same spelling", entity_type)

    value = (raw_value or "").strip()
    if not value:
        return f"{entity_type}_unknown"

    if entity_type in _CASE_SENSITIVE_TYPES:
        # The full identifier, never a prefix. Truncating wallet addresses to
        # twelve characters merged distinct wallets into a single node.
        body = re.sub(r"[^A-Za-z0-9]", "", value)
    else:
        if entity_type == "drug":
            value = canonical_drug_name(value)
        body = _normalize_text(value)

    if not body:
        return f"{entity_type}_unknown"

    if len(body) > MAX_KEY_LENGTH:
        # A digest rather than a prefix: a prefix can collide, a digest of the
        # whole value effectively cannot.
        body = hashlib.sha256(body.encode("utf-8")).hexdigest()

    return f"{entity_type}_{body}"


def entity_type_of(node_key: str) -> str:
    """Read the entity type back off a key."""
    return (node_key or "").split("_", 1)[0] if "_" in (node_key or "") else ""
