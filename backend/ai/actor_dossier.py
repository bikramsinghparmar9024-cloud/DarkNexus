"""
Actor Dossiers - intelligence organised by person rather than by page.

Everything else in this system is record-centric: the unit of analysis is a
scraped page or an intercepted message. That is not how an investigation
works. Nobody asks "what does record 47 say"; they ask who this person is,
what they move, where they operate, and who they deal with.

This module inverts the index. It walks the stored records, collects every
identifier that appears in them - handles, phones, wallets, UPI IDs, PGP
fingerprints, camera signatures - and builds a profile for each: when it was
first and last seen, which substances and districts it is associated with,
which platforms it operates on, and what the person appears to be *doing*.

An author and the wallets, numbers and cameras that appear in their own
messages are merged into one actor, because one person running five handles is
the normal case rather than the exception.

Two honesty constraints run through this.

First, co-occurrence is not identity. Handles named inside a message are
counterparties, not the sender - merging on "appeared together" collapsed a
six-person network into a single actor, since everyone in a conversation ends
up in one component. Ownership merges identity; mentions build the network.
Merges are graded by how many separate records support them, and a join
resting on one record is reported as WEAK rather than asserted.

Second, a role is an inference, not a fact. It is derived from what the text
does - offering, requesting, or reporting - and every dossier carries the
counts it was derived from so the reasoning can be checked or rejected.
"""

from typing import Any, Dict, List, Optional, Tuple
from collections import Counter, defaultdict
from datetime import datetime, timedelta
import logging

logger = logging.getLogger("actor_dossier")

# Identifier kinds, ordered by how strongly each identifies one person.
# A PGP fingerprint is published deliberately so buyers can verify identity;
# a district is shared by a million people.
IDENTIFIER_STRENGTH = {
    "pgp": 100,
    "wallet": 90,
    "device": 85,
    "phone": 80,
    "upi": 70,
    "handle": 60,
}

# Records needed before two identifiers are treated as confidently the same
# actor. One shared record is a coincidence waiting to happen.
STRONG_JOIN_RECORDS = 2

# Role thresholds: share of a subject's classified messages.
ROLE_DOMINANCE = 0.6


def _wallets(entities: Dict[str, Any]) -> List[str]:
    raw = entities.get("crypto_wallets") or {}
    out: List[str] = []
    if isinstance(raw, dict):
        for addresses in raw.values():
            if isinstance(addresses, (list, tuple)):
                out.extend(a for a in addresses if a)
    elif isinstance(raw, (list, tuple)):
        out.extend(a for a in raw if a)
    return out


def _norm_handle(handle: str) -> str:
    return "@" + str(handle).lstrip("@").strip().lower()


def owned_identifiers(analysis: Dict[str, Any],
                      devices: Optional[List[str]] = None) -> List[Tuple[str, str]]:
    """
    Identifiers that belong to whoever produced this record.

    A wallet, phone, UPI ID, PGP key or camera in a message is the sender's
    own - that is what makes them useful for identity. Handles are excluded
    here because a handle in the body of a message is usually somebody else.
    """
    entities = (analysis or {}).get("entities") or {}
    found: List[Tuple[str, str]] = []

    for wallet in _wallets(entities):
        found.append(("wallet", wallet))
    for phone in entities.get("phones") or []:
        found.append(("phone", str(phone)))
    for upi in entities.get("upi_ids") or []:
        found.append(("upi", str(upi).lower()))
    for fingerprint in entities.get("pgp_fingerprints") or []:
        found.append(("pgp", str(fingerprint).upper()))
    for signature in devices or []:
        found.append(("device", str(signature)))

    return list(dict.fromkeys(found))


def mentioned_handles(analysis: Dict[str, Any],
                      author: Optional[str]) -> List[Tuple[str, str]]:
    """
    Handles named in the text - counterparties, not the sender.

    Treating these as the sender's own identifiers was a serious error: it
    merged everyone who had ever been addressed into a single person, and an
    eight-message network of six people collapsed into one actor. Whom you
    message is a relationship; it is not who you are.
    """
    entities = (analysis or {}).get("entities") or {}
    author_key = _norm_handle(author) if author else None
    handles = []
    for handle in entities.get("handles") or []:
        normalized = _norm_handle(handle)
        if normalized != author_key:
            handles.append(("handle", normalized))
    return list(dict.fromkeys(handles))


class DossierBuilder:
    """Builds per-actor profiles from stored records."""

    async def _load(self, days: Optional[int], limit: int):
        from sqlalchemy import select
        from database.postgres import AsyncSessionLocal, ScrapedData, MediaArtifact
        from ai.enrichment import get_analysis

        async with AsyncSessionLocal() as db:
            stmt = select(ScrapedData).order_by(ScrapedData.created_at.desc()).limit(limit)
            if days:
                stmt = stmt.where(
                    ScrapedData.created_at >= datetime.utcnow() - timedelta(days=days))
            records = list((await db.execute(stmt)).scalars().all())
            media = list((await db.execute(
                select(MediaArtifact).where(MediaArtifact.device_signature.is_not(None))
            )).scalars().all())

        devices: Dict[int, List[str]] = defaultdict(list)
        for m in media:
            if m.scraped_data_id:
                devices[m.scraped_data_id].append(m.device_signature)

        return records, {r.id: get_analysis(r) for r in records}, devices

    # ── Profiles ─────────────────────────────────────────────────────

    def _blank(self, kind: str, value: str) -> Dict[str, Any]:
        return {
            "kind": kind, "value": value,
            "strength": IDENTIFIER_STRENGTH.get(kind, 50),
            "record_ids": [], "first_seen": None, "last_seen": None,
            "substances": Counter(), "locations": Counter(),
            "platforms": Counter(), "speech_acts": Counter(),
            "threat_levels": Counter(), "risk_scores": [],
            "border_sightings": 0,
        }

    def _profile_identifiers(self, records, analyses, devices):
        """
        Build a profile per identifier, and record two different relations.

        `ownership` links an author to the wallets and numbers in their own
        messages - that is identity. `interactions` links an author to the
        handles they address - that is a relationship, and it is what the
        network graph is built from. Keeping them apart is the whole point.
        """
        profiles: Dict[Tuple[str, str], Dict[str, Any]] = {}
        ownership: List[Tuple[Tuple[str, str], Tuple[str, str], int]] = []
        interactions: List[Tuple[Tuple[str, str], Tuple[str, str], int]] = []

        for record in records:
            analysis = analyses.get(record.id) or {}
            entities = analysis.get("entities") or {}
            threat = analysis.get("threat") or {}
            act = (analysis.get("speech_act") or {}).get("act")
            geo_markers = analysis.get("geo_markers") or []
            locations = [m.get("location") for m in geo_markers if m.get("location")]
            locations += list(entities.get("locations") or [])

            author_key = (("handle", _norm_handle(record.author_or_handle))
                          if record.author_or_handle else None)
            owned = owned_identifiers(analysis, devices.get(record.id))
            mentioned = mentioned_handles(analysis, record.author_or_handle)

            if author_key:
                for key in owned:
                    ownership.append((author_key, key, record.id))
                for key in mentioned:
                    interactions.append((author_key, key, record.id))
            elif len(owned) > 1:
                # No author - a listing page, say. The identifiers on one
                # listing plausibly belong to one vendor, but nothing proves
                # it, so they are joined provisionally and graded WEAK.
                for key in owned[1:]:
                    ownership.append((owned[0], key, record.id))

            for key in ([author_key] if author_key else []) + owned + mentioned:
                profile = profiles.setdefault(key, self._blank(*key))
                profile["record_ids"].append(record.id)
                stamp = record.created_at or record.published_at
                if stamp:
                    if profile["first_seen"] is None or stamp < profile["first_seen"]:
                        profile["first_seen"] = stamp
                    if profile["last_seen"] is None or stamp > profile["last_seen"]:
                        profile["last_seen"] = stamp
                profile["substances"].update(entities.get("drugs") or [])
                profile["locations"].update(l for l in locations if l)
                profile["platforms"].update([record.source_type])
                if act:
                    profile["speech_acts"].update([act])
                profile["threat_levels"].update([record.threat_level or "UNREVIEWED"])
                if threat.get("risk_score") is not None:
                    profile["risk_scores"].append(threat["risk_score"])
                if analysis.get("border_alert"):
                    profile["border_sightings"] += 1

        return profiles, ownership, interactions

    # ── Grouping identifiers into actors ─────────────────────────────

    def _group(self, profiles, ownership) -> List[List[Tuple[str, str]]]:
        """
        Merge identifiers belonging to the same person.

        Only ownership joins - an author and the wallets, numbers and cameras
        in their own messages. The merge is transitive, which is what uncovers
        an alias chain: a wallet seen under two handles makes those handles one
        actor. Every group records the weakest evidence holding it together,
        so a chain resting on single sightings can be seen for what it is.

        Interactions are deliberately not merged. Grouping by "appeared in the
        same message" collapsed a six-person network into one actor, because
        everybody in a conversation ends up in one component.
        """
        try:
            import networkx as nx
        except ImportError:                                   # pragma: no cover
            logger.error("networkx is required to group identifiers.")
            return [[key] for key in profiles]

        graph = nx.Graph()
        graph.add_nodes_from(profiles)
        for left, right, record_id in ownership:
            if graph.has_edge(left, right):
                graph[left][right]["records"].append(record_id)
            else:
                graph.add_edge(left, right, records=[record_id])

        self._join_graph = graph
        return [sorted(component) for component in nx.connected_components(graph)]

    def _join_confidence(self, members: List[Tuple[str, str]]) -> Dict[str, Any]:
        """How well evidenced is the claim that these are one actor?"""
        if len(members) < 2:
            return {"grade": "SINGLE", "supporting_records": 0,
                    "note": "one identifier; nothing has been merged"}

        graph = getattr(self, "_join_graph", None)
        if graph is None:
            return {"grade": "UNKNOWN", "supporting_records": 0, "note": ""}

        supports = []
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                if graph.has_edge(members[i], members[j]):
                    supports.append(len(set(graph[members[i]][members[j]]["records"])))

        if not supports:
            return {"grade": "WEAK", "supporting_records": 0,
                    "note": "joined only indirectly through other identifiers"}

        weakest = min(supports)
        if weakest >= STRONG_JOIN_RECORDS:
            grade, note = "STRONG", ("every pairing is supported by at least "
                                     f"{weakest} separate records")
        else:
            grade, note = "WEAK", ("at least one pairing rests on a single "
                                   "record; two identifiers in one message may "
                                   "be two different people")
        return {"grade": grade, "supporting_records": weakest, "note": note}

    def _role(self, acts: Counter) -> Dict[str, Any]:
        """Infer what this actor is doing, and say what the inference rests on."""
        total = sum(acts.values())
        if not total:
            return {"role": "UNKNOWN", "confidence": 0.0,
                    "basis": "no classified messages"}

        role_for = {"OFFER": "SUPPLIER", "DEMAND": "BUYER",
                    "REPORT": "SUBJECT_OF_REPORTING", "CHATTER": "UNCLEAR"}
        act, count = acts.most_common(1)[0]
        share = count / total
        if share < ROLE_DOMINANCE:
            return {"role": "MIXED", "confidence": round(share, 2),
                    "basis": f"no dominant pattern across {total} messages: "
                             + ", ".join(f"{k} {v}" for k, v in acts.most_common())}
        return {
            "role": role_for.get(act, "UNKNOWN"),
            "confidence": round(share, 2),
            "basis": f"{count} of {total} messages read as {act}",
        }

    # ── Entry point ──────────────────────────────────────────────────

    async def build(self, days: Optional[int] = None, limit: int = 1000,
                    min_records: int = 1) -> Dict[str, Any]:
        records, analyses, devices = await self._load(days, limit)
        profiles, ownership, interactions = self._profile_identifiers(
            records, analyses, devices)

        if not profiles:
            return {
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "records_examined": len(records),
                "actors": [],
                "status": "NO_ACTORS",
                "message": ("No identifiers found in the collected records. "
                            "Sources that carry handles, phone numbers or "
                            "wallets are needed before actors can be profiled."),
            }

        actors = []
        groups = self._group(profiles, ownership)
        actor_of: Dict[Tuple[str, str], str] = {}
        for members in groups:
            merged_records: set = set()
            substances, locations, platforms = Counter(), Counter(), Counter()
            acts, levels = Counter(), Counter()
            scores: List[int] = []
            first_seen = last_seen = None
            border = 0

            for key in members:
                p = profiles[key]
                merged_records.update(p["record_ids"])
                substances.update(p["substances"])
                locations.update(p["locations"])
                platforms.update(p["platforms"])
                acts.update(p["speech_acts"])
                levels.update(p["threat_levels"])
                scores.extend(p["risk_scores"])
                border += p["border_sightings"]
                if p["first_seen"] and (first_seen is None or p["first_seen"] < first_seen):
                    first_seen = p["first_seen"]
                if p["last_seen"] and (last_seen is None or p["last_seen"] > last_seen):
                    last_seen = p["last_seen"]

            if len(merged_records) < min_records:
                continue

            # The actor is named for its strongest identifier, so a dossier is
            # headed by a PGP key or wallet rather than a throwaway handle.
            primary = max(members, key=lambda k: (IDENTIFIER_STRENGTH.get(k[0], 0),
                                                  len(profiles[k]["record_ids"])))
            order = ["UNREVIEWED", "LOW", "MEDIUM", "HIGH", "SEVERE"]
            actor_id = f"{primary[0]}:{primary[1]}"
            for key in members:
                actor_of[key] = actor_id

            # The id is the strongest identifier, because that is what stays
            # constant across aliases. The label prefers a handle, because
            # that is what an officer recognises on a screen.
            handles = [v for k, v in members if k == "handle"]
            label = handles[0] if handles else f"{primary[0]}:{primary[1][:16]}"

            actors.append({
                "actor_id": actor_id,
                "label": label,
                "primary_identifier": {"kind": primary[0], "value": primary[1]},
                "identifiers": [{"kind": k, "value": v,
                                 "records": len(profiles[(k, v)]["record_ids"])}
                                for k, v in members],
                "identifier_count": len(members),
                "identity_confidence": self._join_confidence(members),
                "record_ids": sorted(merged_records),
                "record_count": len(merged_records),
                "first_seen": first_seen.isoformat() + "Z" if first_seen else None,
                "last_seen": last_seen.isoformat() + "Z" if last_seen else None,
                "active_days": ((last_seen - first_seen).days
                                if first_seen and last_seen else 0),
                "substances": dict(substances.most_common()),
                "locations": dict(locations.most_common(5)),
                "platforms": dict(platforms),
                "cross_platform": len(platforms) > 1,
                "role": self._role(acts),
                "speech_acts": dict(acts),
                "highest_threat": max(levels, key=lambda lv: order.index(lv)
                                      if lv in order else 0) if levels else "UNREVIEWED",
                "peak_risk_score": max(scores) if scores else 0,
                "mean_risk_score": round(sum(scores) / len(scores)) if scores else 0,
                "border_sightings": border,
            })

        # Rank by what an investigator would triage on: threat first, then
        # how much of the corpus the actor appears in.
        order = ["UNREVIEWED", "LOW", "MEDIUM", "HIGH", "SEVERE"]
        actors.sort(key=lambda a: (order.index(a["highest_threat"])
                                   if a["highest_threat"] in order else 0,
                                   a["peak_risk_score"], a["record_count"]),
                    reverse=True)

        return {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "status": "SUCCESS",
            "records_examined": len(records),
            "identifiers_found": len(profiles),
            "actors": actors,
            # (actor_id, actor_id, record_id) - who addressed whom. The
            # network graph is built from these, never from the merges above.
            "interactions": [
                [actor_of.get(a), actor_of.get(b), record_id]
                for a, b, record_id in interactions
                if actor_of.get(a) and actor_of.get(b)
                and actor_of[a] != actor_of[b]
            ],
            "summary": {
                "actor_count": len(actors),
                "cross_platform_actors": sum(1 for a in actors if a["cross_platform"]),
                "multi_identifier_actors": sum(1 for a in actors
                                               if a["identifier_count"] > 1),
                "suppliers": sum(1 for a in actors if a["role"]["role"] == "SUPPLIER"),
                "buyers": sum(1 for a in actors if a["role"]["role"] == "BUYER"),
            },
        }


dossier_builder = DossierBuilder()
