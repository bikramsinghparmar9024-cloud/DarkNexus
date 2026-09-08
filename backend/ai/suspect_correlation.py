"""
Suspect Correlation from Collected Evidence.

Replaces a function that assigned risk scores by checking whether a handle
contained certain substrings:

    if "lahori" in handle: risk = 96
    elif "jagga" in handle: risk = 92
    else: risk = 75

That produced a confident-looking number for any input, including a handle
that had never been observed. Here the score is computed from records actually
collected, and an account with no footprint scores zero and says so.

The score combines four things, each individually explainable:

    threat      - the highest threat level of records the account appears in
    volume      - how many records mention it
    reach       - how many distinct platforms it appears on
    linkage     - identifiers it shares with other observed actors
"""

from typing import Any, Dict, List, Optional
from datetime import datetime
import logging

logger = logging.getLogger("suspect_correlation")

THREAT_POINTS = {"SEVERE": 40, "HIGH": 30, "MEDIUM": 15, "LOW": 5, "UNREVIEWED": 5}

# Diminishing returns: the tenth mention is weaker evidence than the second.
VOLUME_POINTS = [0, 8, 14, 18, 21, 23, 25]
MAX_VOLUME_POINTS = 25

# Appearing on several platforms is harder to explain innocently.
REACH_POINTS = {1: 0, 2: 12, 3: 20}

# Sharing a wallet or phone with another tracked actor.
LINKAGE_POINTS_PER_LINK = 8
MAX_LINKAGE_POINTS = 20


def _volume_points(count: int) -> int:
    if count < len(VOLUME_POINTS):
        return VOLUME_POINTS[count]
    return MAX_VOLUME_POINTS


async def correlate_suspect(username: str, limit: int = 2000) -> Dict[str, Any]:
    """
    Search collected intelligence for an account and score what is found.

    Returns the evidence alongside the score so an analyst can check the
    reasoning rather than trusting a number.
    """
    from sqlalchemy import select, or_
    from database.postgres import AsyncSessionLocal, ScrapedData
    from ai.enrichment import get_analysis

    handle = (username or "").strip()
    if not handle:
        return _empty_result(username)

    bare = handle.lstrip("@").lower()

    async with AsyncSessionLocal() as db:
        records = (await db.execute(
            select(ScrapedData)
            .where(or_(
                ScrapedData.author_or_handle.ilike(f"%{bare}%"),
                ScrapedData.cleaned_text.ilike(f"%{bare}%"),
            ))
            .order_by(ScrapedData.created_at.desc())
            .limit(limit)
        )).scalars().all()

        if not records:
            return _empty_result(username)

        # Identifiers this account uses, and any other actor sharing them.
        own_identifiers = set()
        matched_sources: List[Dict[str, Any]] = []
        source_types = set()
        highest_threat = "LOW"
        latest_activity: Optional[datetime] = None

        for record in records:
            analysis = get_analysis(record)
            entities = analysis.get("entities") or {}

            for addrs in (entities.get("crypto_wallets") or {}).values():
                own_identifiers.update(addrs or [])
            own_identifiers.update(entities.get("phones") or [])
            own_identifiers.update(entities.get("upi_ids") or [])
            own_identifiers.update(entities.get("pgp_fingerprints") or [])

            source_types.add(record.source_type)
            threat = record.threat_level or "LOW"
            if THREAT_POINTS.get(threat, 0) > THREAT_POINTS.get(highest_threat, 0):
                highest_threat = threat

            timestamp = record.published_at or record.created_at
            if timestamp and (latest_activity is None or timestamp > latest_activity):
                latest_activity = timestamp

            matched_sources.append({
                "record_id": record.id,
                "source_type": record.source_type,
                "url": record.source_url,
                "threat_level": threat,
                "snippet": (record.cleaned_text or record.raw_content or "")[:160].strip(),
                "observed_at": timestamp.isoformat() + "Z" if timestamp else None,
            })

        # Which other observed actors share one of those identifiers?
        linked_actors = set()
        if own_identifiers:
            others = (await db.execute(
                select(ScrapedData)
                .where(ScrapedData.author_or_handle.is_not(None))
                .order_by(ScrapedData.created_at.desc())
                .limit(limit)
            )).scalars().all()

            for other in others:
                other_handle = (other.author_or_handle or "").lstrip("@").lower()
                if not other_handle or other_handle == bare:
                    continue
                entities = (get_analysis(other).get("entities") or {})
                other_ids = set()
                for addrs in (entities.get("crypto_wallets") or {}).values():
                    other_ids.update(addrs or [])
                other_ids.update(entities.get("phones") or [])
                other_ids.update(entities.get("upi_ids") or [])
                other_ids.update(entities.get("pgp_fingerprints") or [])
                if own_identifiers & other_ids:
                    linked_actors.add(other.author_or_handle)

    # ── Score, with each component kept separate ─────────────────────
    threat_points = THREAT_POINTS.get(highest_threat, 0)
    volume_points = _volume_points(len(records))
    reach_points = REACH_POINTS.get(len(source_types), 20 if len(source_types) > 3 else 0)
    linkage_points = min(len(linked_actors) * LINKAGE_POINTS_PER_LINK, MAX_LINKAGE_POINTS)

    risk_score = min(threat_points + volume_points + reach_points + linkage_points, 100)

    summary = (
        "Found in %d record(s) across %s. Highest threat level observed: %s."
        % (len(records), ", ".join(sorted(source_types)), highest_threat)
    )
    if linked_actors:
        summary += (" Shares identifiers with %s."
                    % ", ".join(sorted(linked_actors)[:3]))

    return {
        "found": True,
        "username": username,
        "risk_score": risk_score,
        "score_breakdown": {
            "highest_threat": highest_threat,
            "threat_points": threat_points,
            "record_count": len(records),
            "volume_points": volume_points,
            "platform_count": len(source_types),
            "reach_points": reach_points,
            "linked_actor_count": len(linked_actors),
            "linkage_points": linkage_points,
        },
        "matched_sources": matched_sources[:20],
        "evidence_record_ids": [m["record_id"] for m in matched_sources],
        "linked_actors": sorted(linked_actors),
        "correlation_count": len(matched_sources),
        "platforms": sorted(source_types),
        "last_active": latest_activity.isoformat() + "Z" if latest_activity else None,
        "correlation_summary": summary,
    }


def _empty_result(username: str) -> Dict[str, Any]:
    """
    An account with no footprint in collected intelligence.

    Stated plainly rather than given a placeholder score - "no evidence" and
    "low risk" are different claims, and conflating them is how an untracked
    account comes to look assessed.
    """
    return {
        "found": False,
        "username": username,
        "risk_score": 0,
        "score_breakdown": {},
        "matched_sources": [],
        "evidence_record_ids": [],
        "linked_actors": [],
        "correlation_count": 0,
        "platforms": [],
        "last_active": None,
        "correlation_summary": (
            "No activity found in collected intelligence for '%s'. This is an "
            "absence of evidence, not evidence of low risk - the account may "
            "simply not appear in any source collected so far." % username
        ),
    }
