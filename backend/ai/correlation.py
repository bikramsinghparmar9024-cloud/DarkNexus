"""
Cross-Record Correlation & Pattern Detection.

Individual intercepts say little. A hundred of them, viewed together, show
structure: the same wallet paying two different couriers, photographs from one
phone appearing under three aliases, a cluster of GPS fixes tightening around
one stretch of border, deliveries that only ever happen after midnight.

This module answers questions no single record can:

  * hotspots         - where is activity concentrating?
  * identifier reuse - which accounts, wallets or phones link separate records?
  * device linkage   - which photographs came from the same physical camera?
  * temporal pattern - when does this network operate?
  * co-occurrence    - which substances travel with which locations?
  * emerging trends  - what changed compared with the previous period?

A note on confidence. Correlation is suggestive, not proof: two records
sharing a phone number is a lead, not a conviction. Every finding therefore
carries an evidence count and an independent-source count, and nothing is
promoted to a strong finding on a single sighting. The thresholds are explicit
constants below so they can be defended and tuned.
"""

from typing import Any, Dict, List, Optional, Tuple
from collections import Counter, defaultdict
from datetime import datetime, timedelta
import logging

logger = logging.getLogger("correlation")

# ── Evidence thresholds ──────────────────────────────────────────────
# A location needs this many sightings before it is called a hotspot.
HOTSPOT_MIN_SIGHTINGS = 3
# Sightings from at least this many distinct sources before confidence rises.
HOTSPOT_MIN_SOURCES = 2
# An identifier must appear in at least this many records to be a link.
IDENTIFIER_MIN_RECORDS = 2
# Night-time window used for the operating-hours pattern.
NIGHT_HOURS = set(range(22, 24)) | set(range(0, 5))

THREAT_WEIGHTS = {"SEVERE": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "UNREVIEWED": 1}


def _confidence(sightings: int, sources: int) -> str:
    """Grade a finding by how much independent evidence supports it."""
    if sightings >= HOTSPOT_MIN_SIGHTINGS * 3 and sources >= HOTSPOT_MIN_SOURCES + 1:
        return "HIGH"
    if sightings >= HOTSPOT_MIN_SIGHTINGS and sources >= HOTSPOT_MIN_SOURCES:
        return "MODERATE"
    if sightings >= HOTSPOT_MIN_SIGHTINGS:
        return "LOW"
    return "INSUFFICIENT"


class CorrelationEngine:
    """Aggregates across stored records to surface network-level patterns."""

    # ── Data loading ─────────────────────────────────────────────────

    async def _load(self, days: Optional[int], limit: int) -> Tuple[List[Any], List[Any]]:
        from sqlalchemy import select
        from database.postgres import AsyncSessionLocal, ScrapedData, MediaArtifact
        from ai.enrichment import get_analysis

        async with AsyncSessionLocal() as db:
            stmt = select(ScrapedData).order_by(ScrapedData.created_at.desc()).limit(limit)
            if days:
                cutoff = datetime.utcnow() - timedelta(days=days)
                stmt = stmt.where(ScrapedData.created_at >= cutoff)
            records = (await db.execute(stmt)).scalars().all()

            media = (await db.execute(
                select(MediaArtifact).where(MediaArtifact.gps_lat.is_not(None))
            )).scalars().all()

        # Attach the canonical analysis block so callers need not re-derive it.
        for r in records:
            r._analysis = get_analysis(r)
        return records, media

    # ── 1. Hotspots ──────────────────────────────────────────────────

    def _hotspots(self, records: List[Any], media: List[Any]) -> Dict[str, Any]:
        """
        Where is activity concentrating?

        Two independent streams feed this: place names written in the text, and
        GPS coordinates lifted from photographs. GPS evidence is weighted more
        heavily - a coordinate embedded in a photo is far harder to fake or
        misread than a town name mentioned in passing.
        """
        sightings = defaultdict(lambda: {
            "text_mentions": 0, "gps_fixes": 0, "records": set(),
            "sources": set(), "threat_weight": 0, "max_threat": "LOW",
            "distance_to_border_km": None, "lat": None, "lon": None,
        })

        for r in records:
            analysis = getattr(r, "_analysis", {}) or {}
            entities = analysis.get("entities") or {}
            threat = (analysis.get("threat") or {}).get("threat_level", r.threat_level or "LOW")
            weight = THREAT_WEIGHTS.get(threat, 1)

            for marker in analysis.get("geo_markers") or []:
                name = marker.get("location")
                if not name:
                    continue
                s = sightings[name]
                s["text_mentions"] += 1
                s["records"].add(r.id)
                s["sources"].add(r.source_type)
                s["threat_weight"] += weight
                s["distance_to_border_km"] = marker.get("distance_to_border_km")
                s["lat"], s["lon"] = marker.get("lat"), marker.get("lon")
                if THREAT_WEIGHTS.get(threat, 1) > THREAT_WEIGHTS.get(s["max_threat"], 1):
                    s["max_threat"] = threat

            # Fall back to plain location names when geo markers are absent.
            if not analysis.get("geo_markers"):
                for name in entities.get("locations") or []:
                    s = sightings[name]
                    s["text_mentions"] += 1
                    s["records"].add(r.id)
                    s["sources"].add(r.source_type)
                    s["threat_weight"] += weight

        # GPS fixes from photographs, weighted double.
        for m in media:
            geo = m.geo_json or {}
            name = geo.get("nearest_known_location")
            if not name:
                continue
            s = sightings[name]
            s["gps_fixes"] += 1
            s["threat_weight"] += 4
            s["sources"].add("MEDIA_GPS")
            if m.scraped_data_id:
                s["records"].add(m.scraped_data_id)
            s["distance_to_border_km"] = geo.get("distance_to_border_km")
            s["lat"], s["lon"] = m.gps_lat, m.gps_lon

        hotspots = []
        for name, s in sightings.items():
            total = s["text_mentions"] + s["gps_fixes"]
            confidence = _confidence(total, len(s["sources"]))
            hotspots.append({
                "location": name,
                "lat": s["lat"], "lon": s["lon"],
                "total_sightings": total,
                "text_mentions": s["text_mentions"],
                "gps_fixes": s["gps_fixes"],
                "distinct_records": len(s["records"]),
                "independent_sources": sorted(s["sources"]),
                "intensity_score": s["threat_weight"],
                "max_threat_level": s["max_threat"],
                "distance_to_border_km": s["distance_to_border_km"],
                "in_border_corridor": (s["distance_to_border_km"] is not None
                                       and s["distance_to_border_km"] <= 15),
                "confidence": confidence,
                "is_hotspot": confidence != "INSUFFICIENT",
            })

        hotspots.sort(key=lambda h: (h["intensity_score"], h["total_sightings"]), reverse=True)
        confirmed = [h for h in hotspots if h["is_hotspot"]]

        return {
            "hotspots": hotspots,
            "confirmed_count": len(confirmed),
            "border_corridor_hotspots": [h["location"] for h in confirmed
                                         if h["in_border_corridor"]],
            "thresholds": {
                "min_sightings": HOTSPOT_MIN_SIGHTINGS,
                "min_independent_sources": HOTSPOT_MIN_SOURCES,
            },
        }

    # ── 2. Identifier reuse ──────────────────────────────────────────

    def _identifier_links(self, records: List[Any]) -> Dict[str, Any]:
        """
        Which concrete identifiers tie separate records together?

        A wallet or phone number appearing under two different handles, or on
        two different platforms, is the strongest cheap signal that one actor
        is behind both.
        """
        buckets = {
            "crypto_wallets": defaultdict(lambda: {"records": set(), "sources": set(), "authors": set()}),
            "phones": defaultdict(lambda: {"records": set(), "sources": set(), "authors": set()}),
            "handles": defaultdict(lambda: {"records": set(), "sources": set(), "authors": set()}),
            "upi_ids": defaultdict(lambda: {"records": set(), "sources": set(), "authors": set()}),
        }

        for r in records:
            entities = (getattr(r, "_analysis", {}) or {}).get("entities") or {}
            author = r.author_or_handle or "unknown"

            values = {
                "phones": entities.get("phones") or [],
                "handles": entities.get("handles") or [],
                "upi_ids": entities.get("upi_ids") or [],
                "crypto_wallets": [
                    addr
                    for addrs in (entities.get("crypto_wallets") or {}).values()
                    if isinstance(addrs, (list, tuple))
                    for addr in addrs
                ],
            }

            for kind, items in values.items():
                for item in items:
                    b = buckets[kind][item]
                    b["records"].add(r.id)
                    b["sources"].add(r.source_type)
                    b["authors"].add(author)

        links = []
        for kind, entries in buckets.items():
            for value, b in entries.items():
                if len(b["records"]) < IDENTIFIER_MIN_RECORDS:
                    continue
                cross_platform = len(b["sources"]) > 1
                multi_alias = len(b["authors"]) > 1
                links.append({
                    "identifier_type": kind,
                    "value": value,
                    "record_count": len(b["records"]),
                    "record_ids": sorted(b["records"]),
                    "source_types": sorted(b["sources"]),
                    "linked_authors": sorted(b["authors"]),
                    "cross_platform": cross_platform,
                    "multiple_aliases": multi_alias,
                    "significance": (
                        "STRONG" if cross_platform and multi_alias
                        else "MODERATE" if cross_platform or multi_alias
                        else "WEAK"
                    ),
                })

        links.sort(key=lambda l: (l["record_count"], len(l["source_types"])), reverse=True)
        return {
            "links": links,
            "strong_links": [l for l in links if l["significance"] == "STRONG"],
            "threshold_records": IDENTIFIER_MIN_RECORDS,
        }

    # ── 3. Device linkage ────────────────────────────────────────────

    def _device_links(self, media: List[Any], all_media: List[Any]) -> List[Dict[str, Any]]:
        """Photographs sharing a camera signature likely share a photographer."""
        devices = defaultdict(lambda: {"artifacts": [], "records": set()})
        for m in all_media:
            if not m.device_signature:
                continue
            d = devices[m.device_signature]
            d["artifacts"].append(m.id)
            if m.scraped_data_id:
                d["records"].add(m.scraped_data_id)

        return [
            {
                "device": name,
                "artifact_count": len(d["artifacts"]),
                "linked_record_ids": sorted(d["records"]),
                "record_count": len(d["records"]),
                "significance": "STRONG" if len(d["records"]) > 1 else "SINGLE_RECORD",
            }
            for name, d in sorted(devices.items(),
                                  key=lambda kv: len(kv[1]["records"]), reverse=True)
        ]

    # ── 4. Temporal pattern ──────────────────────────────────────────

    def _temporal(self, records: List[Any]) -> Dict[str, Any]:
        """When is this network active? Night concentration suggests drops."""
        by_hour, by_weekday = Counter(), Counter()
        night_high_threat = 0

        for r in records:
            ts = r.published_at or r.created_at
            if not ts:
                continue
            by_hour[ts.hour] += 1
            by_weekday[ts.strftime("%A")] += 1
            threat = (getattr(r, "_analysis", {}) or {}).get("threat", {}).get(
                "threat_level", r.threat_level)
            if ts.hour in NIGHT_HOURS and threat in ("HIGH", "SEVERE"):
                night_high_threat += 1

        total = sum(by_hour.values())
        night_total = sum(c for h, c in by_hour.items() if h in NIGHT_HOURS)
        night_share = round(night_total / total * 100, 1) if total else 0.0

        return {
            "records_with_timestamps": total,
            "by_hour": {str(h): by_hour.get(h, 0) for h in range(24)},
            "by_weekday": dict(by_weekday),
            "peak_hour": by_hour.most_common(1)[0][0] if by_hour else None,
            "night_activity_share_pct": night_share,
            "night_high_threat_records": night_high_threat,
            "assessment": (
                "Activity concentrates at night, consistent with dead-drop or "
                "border-crossing logistics." if night_share >= 50 and total >= 5
                else "No strong night-time concentration detected."
                if total >= 5 else "Insufficient timestamped records to assess."
            ),
        }

    # ── 5. Co-occurrence ─────────────────────────────────────────────

    def _cooccurrence(self, records: List[Any]) -> Dict[str, Any]:
        """Which substances travel with which places, and which tactics?"""
        drug_location = Counter()
        drug_tactic = Counter()
        drug_counts, location_counts = Counter(), Counter()

        for r in records:
            analysis = getattr(r, "_analysis", {}) or {}
            entities = analysis.get("entities") or {}
            drugs = entities.get("drugs") or []
            locations = entities.get("locations") or []
            tactics = (analysis.get("threat") or {}).get("modus_operandi") or []

            drug_counts.update(drugs)
            location_counts.update(locations)
            for d in drugs:
                for loc in locations:
                    drug_location[(d, loc)] += 1
                for t in tactics:
                    drug_tactic[(d, t)] += 1

        return {
            "drug_location_pairs": [
                {"drug": d, "location": l, "co_occurrences": c}
                for (d, l), c in drug_location.most_common(20)
            ],
            "drug_tactic_pairs": [
                {"drug": d, "tactic": t, "co_occurrences": c}
                for (d, t), c in drug_tactic.most_common(20)
            ],
            "substance_frequency": dict(drug_counts.most_common()),
            "location_frequency": dict(location_counts.most_common()),
        }

    # ── 6. Emerging trends ───────────────────────────────────────────

    def _trends(self, records: List[Any], window_days: int = 7) -> Dict[str, Any]:
        """Compare the most recent window against the one before it."""
        now = datetime.utcnow()
        recent_cut = now - timedelta(days=window_days)
        prior_cut = now - timedelta(days=window_days * 2)

        recent_locs, prior_locs = Counter(), Counter()
        recent_drugs, prior_drugs = Counter(), Counter()
        recent_n = prior_n = 0

        for r in records:
            ts = r.created_at
            if not ts:
                continue
            entities = (getattr(r, "_analysis", {}) or {}).get("entities") or {}
            if ts >= recent_cut:
                recent_n += 1
                recent_locs.update(entities.get("locations") or [])
                recent_drugs.update(entities.get("drugs") or [])
            elif ts >= prior_cut:
                prior_n += 1
                prior_locs.update(entities.get("locations") or [])
                prior_drugs.update(entities.get("drugs") or [])

        new_locations = sorted(set(recent_locs) - set(prior_locs))
        new_substances = sorted(set(recent_drugs) - set(prior_drugs))

        change_pct = None
        if prior_n:
            change_pct = round((recent_n - prior_n) / prior_n * 100, 1)

        return {
            "window_days": window_days,
            "records_recent": recent_n,
            "records_prior": prior_n,
            "volume_change_pct": change_pct,
            "newly_appearing_locations": new_locations,
            "newly_appearing_substances": new_substances,
            "assessment": (
                "Insufficient history for trend analysis."
                if prior_n == 0 else
                "Collection volume rising." if (change_pct or 0) > 25 else
                "Collection volume falling." if (change_pct or 0) < -25 else
                "Collection volume broadly stable."
            ),
        }

    # ── Public entry point ───────────────────────────────────────────

    async def build_intelligence_picture(self, days: Optional[int] = None,
                                         limit: int = 2000) -> Dict[str, Any]:
        """Run every correlation pass and return one combined assessment."""
        records, media = await self._load(days, limit)

        if not records:
            return {
                "status": "NO_DATA",
                "message": "No intelligence records available to correlate.",
                "record_count": 0,
            }

        hotspots = self._hotspots(records, media)
        identifiers = self._identifier_links(records)
        temporal = self._temporal(records)
        cooccurrence = self._cooccurrence(records)
        trends = self._trends(records)
        devices = self._device_links(media, media)

        return {
            "status": "SUCCESS",
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "scope": {
                "record_count": len(records),
                "media_with_gps": len(media),
                "window_days": days,
            },
            "hotspots": hotspots,
            "identifier_links": identifiers,
            "device_links": devices,
            "temporal_pattern": temporal,
            "co_occurrence": cooccurrence,
            "trends": trends,
            "key_judgements": self._judgements(hotspots, identifiers, temporal, trends, len(records)),
        }

    def _judgements(self, hotspots, identifiers, temporal, trends, record_count) -> List[Dict[str, str]]:
        """
        Plain-language conclusions, each stated with its supporting evidence.

        Deliberately conservative: where evidence is thin, that is said openly
        rather than dressed up as a finding.
        """
        out: List[Dict[str, str]] = []

        confirmed = [h for h in hotspots["hotspots"] if h["is_hotspot"]]
        if confirmed:
            top = confirmed[0]
            out.append({
                "judgement": "Activity concentrates around %s." % top["location"],
                "evidence": "%d sighting(s) across %d independent source type(s); "
                            "%d from photograph GPS."
                            % (top["total_sightings"], len(top["independent_sources"]),
                               top["gps_fixes"]),
                "confidence": top["confidence"],
            })
        else:
            out.append({
                "judgement": "No location meets the hotspot threshold yet.",
                "evidence": "Requires %d sightings from %d independent sources."
                            % (HOTSPOT_MIN_SIGHTINGS, HOTSPOT_MIN_SOURCES),
                "confidence": "INSUFFICIENT",
            })

        border = hotspots["border_corridor_hotspots"]
        if border:
            out.append({
                "judgement": "Border corridor activity detected at %s." % ", ".join(border),
                "evidence": "Hotspot(s) resolved within 15 km of the international border.",
                "confidence": "MODERATE",
            })

        strong = identifiers["strong_links"]
        if strong:
            link = strong[0]
            out.append({
                "judgement": "One actor likely operates across multiple platforms.",
                "evidence": "%s '%s' appears in %d records spanning %s under aliases %s."
                            % (link["identifier_type"], link["value"], link["record_count"],
                               ", ".join(link["source_types"]), ", ".join(link["linked_authors"])),
                "confidence": "MODERATE",
            })

        if temporal["night_activity_share_pct"] >= 50 and temporal["records_with_timestamps"] >= 5:
            out.append({
                "judgement": "Operations are concentrated in night-time hours.",
                "evidence": "%.0f%% of timestamped records fall between 22:00 and 05:00."
                            % temporal["night_activity_share_pct"],
                "confidence": "MODERATE",
            })

        if trends["newly_appearing_locations"]:
            out.append({
                "judgement": "New locations entering the picture: %s."
                             % ", ".join(trends["newly_appearing_locations"][:5]),
                "evidence": "Present in the last %d days but absent from the prior period."
                            % trends["window_days"],
                "confidence": "LOW",
            })

        if record_count < 20:
            out.append({
                "judgement": "Overall assessment is provisional.",
                "evidence": "Only %d records analysed; patterns may not be representative."
                            % record_count,
                "confidence": "LOW",
            })

        return out


correlation_engine = CorrelationEngine()
