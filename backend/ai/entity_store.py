"""
Entity Knowledge Base, built from collected intelligence.

The entity resolver's scoring logic was sound but ran against a hardcoded cast
of invented suspects, so it answered the same fiction regardless of what had
actually been collected. This module produces the same structures from the
database instead.

An entity here is an observed actor - an author handle seen posting. Its
identifiers are everything extracted from the records it appears in: aliases,
payment addresses, phone numbers, PGP fingerprints, and the camera signatures
of any photographs it posted.

Relationships are then derived by looking for identifiers two actors share.
Nothing is asserted that the evidence does not contain: where a signal cannot
be observed - PGP where no key was ever posted - it is reported as unmatched
rather than filled in.
"""

from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict
from datetime import datetime, timedelta
import logging
import re

from core.identity import slugify_entity_key

logger = logging.getLogger("entity_store")

# Two actors active within this window are treated as temporally correlated.
TIMING_CORRELATION_HOURS = 72

# Cap on records scanned when rebuilding the knowledge base.
DEFAULT_RECORD_LIMIT = 2000


def _slug(value: str) -> str:
    """
    Entity id for an author handle - the same key the graph uses.

    This used to build its own key with an "actor_" prefix while the graph
    built "suspect_" keys without lowercasing, so the same person existed
    under two irreconcilable ids and "Why This Link?" answered 404 for
    suspects that were plainly in both stores. Both now come from one
    function; see core/identity.py.
    """
    return slugify_entity_key(value or "unknown", "suspect")


def _flatten_wallets(entities: Dict[str, Any]) -> List[str]:
    wallets = entities.get("crypto_wallets") or {}
    if isinstance(wallets, dict):
        out = []
        for chain, addrs in wallets.items():
            for a in addrs or []:
                out.append(f"{chain.upper()}:{a}")
        return out
    return list(wallets or [])


async def build_knowledge_base(limit: int = DEFAULT_RECORD_LIMIT
                               ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Assemble entities and their derived relationships from stored records.

    Returns (knowledge_base, relationships) in the shapes the resolver expects.
    """
    from sqlalchemy import select
    from database.postgres import AsyncSessionLocal, ScrapedData, MediaArtifact
    from ai.enrichment import get_analysis

    async with AsyncSessionLocal() as db:
        records = (await db.execute(
            select(ScrapedData).order_by(ScrapedData.created_at.desc()).limit(limit)
        )).scalars().all()
        media = (await db.execute(select(MediaArtifact))).scalars().all()

    media_by_record = defaultdict(list)
    for m in media:
        if m.scraped_data_id:
            media_by_record[m.scraped_data_id].append(m)

    accumulator: Dict[str, Dict[str, Any]] = {}

    for record in records:
        author = (record.author_or_handle or "").strip()
        if not author:
            continue

        entity_id = _slug(author)
        entity = accumulator.setdefault(entity_id, {
            "id": entity_id,
            "name": author,
            "type": "suspect",
            "platforms": set(),
            "aliases": set(),
            "payment_handles": set(),
            "communication_ids": set(),
            "phone_numbers": set(),
            "pgp_fingerprints": set(),
            "devices": set(),
            "sources": [],
            "timestamps": [],
        })

        entity["aliases"].add(author)
        entity["platforms"].add(record.source_type)

        analysis = get_analysis(record)
        extracted = analysis.get("entities") or {}

        entity["payment_handles"].update(_flatten_wallets(extracted))
        entity["payment_handles"].update(
            f"UPI:{u}" for u in (extracted.get("upi_ids") or [])
        )
        entity["communication_ids"].update(extracted.get("handles") or [])
        entity["communication_ids"].update(extracted.get("phones") or [])
        entity["phone_numbers"].update(extracted.get("phones") or [])
        entity["pgp_fingerprints"].update(extracted.get("pgp_fingerprints") or [])

        for artifact in media_by_record.get(record.id, []):
            if artifact.device_signature:
                entity["devices"].add(artifact.device_signature)

        timestamp = record.published_at or record.created_at
        if timestamp:
            entity["timestamps"].append(timestamp)

        snippet = (record.cleaned_text or record.raw_content or "")[:220].strip()
        entity["sources"].append({
            "id": f"rec_{record.id}",
            "record_id": record.id,
            "type": record.source_type,
            "url": record.source_url,
            "snippet": snippet,
            "timestamp": timestamp.isoformat() + "Z" if timestamp else None,
            "threat_level": record.threat_level,
        })

    knowledge_base = {}
    for entity_id, e in accumulator.items():
        knowledge_base[entity_id] = {
            "id": entity_id,
            "name": e["name"],
            "type": e["type"],
            "platform": " & ".join(sorted(e["platforms"])) or "Unknown",
            "identifiers": {
                "aliases": sorted(e["aliases"]),
                # Reported as None when no key was ever observed, rather than
                # invented - this is the highest-weighted signal in the model.
                "pgp_fingerprint": sorted(e["pgp_fingerprints"])[0] if e["pgp_fingerprints"] else None,
                "pgp_fingerprints": sorted(e["pgp_fingerprints"]),
                "payment_handles": sorted(e["payment_handles"]),
                "communication_ids": sorted(e["communication_ids"]),
                "phone_numbers": sorted(e["phone_numbers"]),
                "devices": sorted(e["devices"]),
            },
            "sources": e["sources"],
            "_timestamps": e["timestamps"],
        }

    relationships = _derive_relationships(knowledge_base)
    logger.info("Knowledge base rebuilt: %d entities, %d relationships from %d records.",
                len(knowledge_base), len(relationships), len(records))
    return knowledge_base, relationships


def _timing_correlated(a: Dict[str, Any], b: Dict[str, Any]) -> Optional[str]:
    """True when the two actors were active within the correlation window."""
    for ta in a.get("_timestamps", []):
        for tb in b.get("_timestamps", []):
            delta = abs((ta - tb).total_seconds()) / 3600.0
            if delta <= TIMING_CORRELATION_HOURS:
                return (f"activity within {delta:.0f}h "
                        f"(threshold {TIMING_CORRELATION_HOURS}h)")
    return None


def _derive_relationships(kb: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Build a relationship for every pair of actors sharing an identifier.

    Pairs with nothing in common are not emitted: an absence of evidence is
    not a relationship, and listing every pair would bury the real links.
    """
    relationships: List[Dict[str, Any]] = []
    ids = sorted(kb.keys())

    for i, source_id in enumerate(ids):
        for target_id in ids[i + 1:]:
            source, target = kb[source_id], kb[target_id]
            s_ids, t_ids = source["identifiers"], target["identifiers"]

            shared_pgp = set(s_ids["pgp_fingerprints"]) & set(t_ids["pgp_fingerprints"])
            shared_alias = ({a.lower() for a in s_ids["aliases"]}
                            & {a.lower() for a in t_ids["aliases"]})
            shared_payment = set(s_ids["payment_handles"]) & set(t_ids["payment_handles"])
            shared_comm = ({c.lower() for c in s_ids["communication_ids"]}
                           & {c.lower() for c in t_ids["communication_ids"]})
            shared_device = set(s_ids["devices"]) & set(t_ids["devices"])

            if not any((shared_pgp, shared_alias, shared_payment,
                        shared_comm, shared_device)):
                continue

            surface_corroboration = (
                any(s["type"] == "SURFACE_WEB" for s in source["sources"])
                and any(s["type"] == "SURFACE_WEB" for s in target["sources"])
            )
            timing = _timing_correlated(source, target)

            signals = {
                "pgp_fingerprint": {
                    "matched": bool(shared_pgp),
                    "value": sorted(shared_pgp)[0] if shared_pgp else None,
                },
                "alias_overlap": {
                    "matched": bool(shared_alias),
                    "value": sorted(shared_alias) or None,
                },
                "payment_handle": {
                    "matched": bool(shared_payment),
                    "value": sorted(shared_payment) or None,
                },
                "communication_id": {
                    "matched": bool(shared_comm),
                    "value": sorted(shared_comm) or None,
                },
                "shared_device": {
                    "matched": bool(shared_device),
                    "value": sorted(shared_device) or None,
                },
                "surface_web_corroboration": {
                    "matched": surface_corroboration,
                    "value": "both actors appear in surface-web material"
                             if surface_corroboration else None,
                },
                "timing_correlation": {
                    "matched": bool(timing),
                    "value": timing,
                },
            }

            evidence_sources = ([s["id"] for s in source["sources"]]
                                + [s["id"] for s in target["sources"]])

            relationships.append({
                "source_entity": source_id,
                "target_entity": target_id,
                "signals": signals,
                "evidence_sources": sorted(set(evidence_sources)),
                "contradictions": _find_contradictions(source, target, shared_payment),
                "hops": 1,
            })

    return relationships


def _find_contradictions(source: Dict[str, Any], target: Dict[str, Any],
                         shared_payment: set) -> List[Dict[str, Any]]:
    """
    Evidence that argues against the two actors being one person.

    Surfacing this matters: an analyst shown only supporting evidence has been
    handed a conclusion, not an assessment.
    """
    contradictions: List[Dict[str, Any]] = []

    s_phones = set(source["identifiers"]["phone_numbers"])
    t_phones = set(target["identifiers"]["phone_numbers"])
    if shared_payment and s_phones and t_phones and not (s_phones & t_phones):
        contradictions.append({
            "type": "IDENTIFIER_CONFLICT",
            "severity": "LOW",
            "detail": ("shares a payment address but uses entirely different phone "
                       "numbers (%s vs %s); consistent with a shared wallet or "
                       "escrow service rather than one individual"
                       % (", ".join(sorted(s_phones)[:2]), ", ".join(sorted(t_phones)[:2]))),
        })

    s_pgp = set(source["identifiers"]["pgp_fingerprints"])
    t_pgp = set(target["identifiers"]["pgp_fingerprints"])
    if s_pgp and t_pgp and not (s_pgp & t_pgp):
        contradictions.append({
            "type": "PGP_MISMATCH",
            "severity": "HIGH",
            "detail": ("both actors publish PGP keys and the fingerprints differ, "
                       "which argues strongly against a single identity"),
        })

    return contradictions
