"""
Unified Intelligence Enrichment & Persistence Layer.

This module is the SINGLE source of truth for analysing and storing an intercept.
Every ingest path routes through here:

  * Automated collection  -> scrapers.base_scraper.save_evidence()
  * Manual injection      -> routes.simulator_routes.ingest_intercept()
  * Batch re-analysis     -> ai.langgraph_workflow.run_batch_analysis()

Because all three share this code, every record lands in the database with the
same field names, the same scoring rules, an entry in the ChromaDB vector index,
and a mirrored node in the correlation graph.

Canonical shape written to ScrapedData:

    scraped_data.threat_level      = "LOW" | "MEDIUM" | "HIGH" | "SEVERE"
    scraped_data.flagged_entities  = analysis["entities"]
    scraped_data.metadata_json     = {
        "analysis":   { ...see analyze_text()... },
        "provenance": { ...caller supplied... }
    }
"""

from typing import Any, Dict, List, Optional
from datetime import datetime
import logging

from ai.punjabi_slang import punjabi_normalizer
from ai.entity_extractor import entity_extractor
from ai.threat_classifier import threat_classifier
from ai.threat_scoring import score_threat
from ai.geo_resolver import extract_geo_markers_from_text
from ai.semantic_classifier import (
    semantic_classifier, reconcile, REPORT_CONFIDENCE,
)
from ai.speech_act import detect_speech_act
from config import settings
from auth.hashing import generate_sha256
from core.identity import slugify_entity_key, canonical_drug_name

logger = logging.getLogger("enrichment")

# Bump when the shape of analyze_text() output changes, so readers can adapt.
ANALYSIS_SCHEMA_VERSION = 2

# Banding lives with the scorer so every path uses one set of thresholds.
from ai.threat_scoring import THREAT_BANDS, level_from_score as _level_from_score  # noqa: E402


def _flatten_wallets(entities: Dict[str, Any]) -> List[str]:
    """crypto_wallets is a {btc: [], eth: []} dict; return one flat address list."""
    wallets = entities.get("crypto_wallets") or {}
    if isinstance(wallets, dict):
        flat: List[str] = []
        for chain_addresses in wallets.values():
            if isinstance(chain_addresses, (list, tuple)):
                flat.extend(chain_addresses)
        return flat
    if isinstance(wallets, (list, tuple)):
        return list(wallets)
    return []


def analyze_text(text: str) -> Dict[str, Any]:
    """
    Run the full analysis chain over a piece of intercepted text.

    Pure function - touches no database. Returns the canonical `analysis` block.
    """
    text = (text or "").strip()
    if not text:
        return {
            "schema_version": ANALYSIS_SCHEMA_VERSION,
            "analyzed_at": datetime.utcnow().isoformat() + "Z",
            "normalized_text": "",
            "detected_slang": [],
            "slang_count": 0,
            "entities": entity_extractor.extract(""),
            "threat": {
                "threat_level": "LOW",
                "risk_score": 0,
                "score_categories": {},
                "categories_triggered": [],
                "score_explanation": "No scoring signals found.",
                "intent": "INSUFFICIENT_DATA",
                "modus_operandi": [],
                "requires_immediate_action": False,
                "border_escalated": False,
                "narcotics_evidence": False,
                "suppressed_reason": None,
            },
            "geo": None,
            "geo_markers": [],
            "border_alert": False,
        }

    # 1. Regional Punjabi / Gurmukhi slang normalization
    slang = punjabi_normalizer.normalize(text)
    normalized_text = slang["normalized_text"]
    slang_boost = slang.get("threat_boost", 0)

    # Analyse raw + normalized together so forensic English terms are also matched.
    combined = f"{text} {normalized_text}"

    # 2. Entity extraction (drugs, locations, phones, handles, wallets, prices)
    entities = entity_extractor.extract(combined)

    # 3. Threat scoring across five independent categories.
    #    Slang is fed in rather than added on top: a street term for heroin
    #    describes the same substance as the English word, and adding both was
    #    a large part of why scores used to saturate.
    scoring = score_threat(combined, entities, slang.get("detected_slang", []))
    risk_score = scoring["risk_score"]
    threat_level = scoring["threat_level"]

    # The keyword classifier is retained only for intent and modus operandi,
    # which it derives from phrase patterns rather than from its own score.
    classification = threat_classifier.classify(combined)

    # 4. Geospatial resolution against the Indo-Pak border corridor
    geo_markers = extract_geo_markers_from_text(combined)
    border_alert = any(m.get("in_critical_border_corridor") for m in geo_markers)

    geo: Optional[Dict[str, Any]] = None
    if geo_markers:
        # Report the marker closest to the border as the primary location.
        geo = min(geo_markers, key=lambda m: m.get("distance_to_border_km", 9999))
        geo = dict(geo)
        geo["district"] = geo.get("location")
        geo["is_border_alert"] = geo.get("in_critical_border_corridor", False)
    elif "border" in combined.lower():
        border_alert = True
        geo = {
            "location": "Indo-Pak Border Belt",
            "district": "Border Belt",
            "distance_to_border_km": 5.0,
            "in_critical_border_corridor": True,
            "is_border_alert": True,
        }

    # 5. Narcotics gate.
    #
    #    Context keywords - "border", "delivery", "bulk", "escrow", "crypto" -
    #    describe logistics, not drugs. On their own they are not narcotics
    #    intelligence: a tractor-parts advert shipping to Fazilka matches every
    #    one of them. Without at least one actual narcotics indicator, the
    #    score is capped and neither the speech-act upgrade nor the border rule
    #    may fire. The record is still stored and still searchable; it is just
    #    not presented to an investigator as a drug threat.
    narcotic_slang = any(
        s.get("category") in ("NARCOTIC", "SYNTHETIC_OPIOID", "ADULTERANT",
                              "GENERAL_CONTRABAND")
        for s in slang.get("detected_slang", [])
    )
    has_narcotics_evidence = bool(entities.get("drugs")) or narcotic_slang

    suppressed_reason = None
    if not has_narcotics_evidence:
        suppressed_reason = (
            "no narcotics indicator found; matched only contextual terms "
            "(logistics, payment or geography), which are not drug evidence "
            "on their own"
        )
        risk_score = min(risk_score, 15)
        threat_level = _level_from_score(risk_score)

    # 6. Semantic cross-check: does this read as trafficking activity, or as
    #    reporting about it? Runs before the border rule so that a news story
    #    naming a border town is not escalated as though it were an offer.
    speech_act = detect_speech_act(combined)

    # The transformer is advisory only and off by default; see
    # ai/semantic_classifier.py for the measurements behind that decision.
    semantic = None
    if (settings.SEMANTIC_CLASSIFIER_ENABLED
            and len(combined.strip()) >= settings.SEMANTIC_MIN_CHARS):
        semantic = semantic_classifier.classify(combined)

    rule_threat = {
        "threat_level": threat_level,
        "risk_score": risk_score,
        "score_categories": scoring["categories"],
        "categories_triggered": scoring["categories_triggered"],
        "score_explanation": scoring["explanation"],
        "intent": classification.get("intent", "UNKNOWN"),
        "modus_operandi": classification.get("modus_operandi", []),
        "requires_immediate_action": threat_level in ("HIGH", "SEVERE"),
    }
    # The speech act may only move the level when narcotics evidence exists.
    threat = reconcile(rule_threat,
                       speech_act if has_narcotics_evidence else None,
                       semantic)
    threat["speech_act"] = speech_act          # always recorded, even if unused
    threat["narcotics_evidence"] = has_narcotics_evidence
    threat["suppressed_reason"] = suppressed_reason
    threat_level = threat["threat_level"]

    # 7. Border proximity escalates a credible threat one band upward - but
    #    only when the model has not judged the text to be commentary.
    border_escalated = False
    # Border proximity amplifies an actual transaction, not a passing remark.
    # CHATTER means no speech-act markers were found at all, which is too weak
    # to justify raising a record to the top band on geography alone.
    is_operational_speech = bool(
        speech_act and speech_act["act"] in ("OFFER", "DEMAND")
    )
    if (border_alert and has_narcotics_evidence and is_operational_speech
            and threat_level in ("MEDIUM", "HIGH")):
        threat_level = "SEVERE"
        border_escalated = True

    threat["threat_level"] = threat_level
    threat["border_escalated"] = border_escalated
    threat["requires_immediate_action"] = threat_level in ("HIGH", "SEVERE")

    return {
        "schema_version": ANALYSIS_SCHEMA_VERSION,
        "analyzed_at": datetime.utcnow().isoformat() + "Z",
        "normalized_text": normalized_text,
        "detected_slang": slang.get("detected_slang", []),
        "slang_count": slang.get("slang_count", 0),
        "entities": entities,
        "threat": threat,
        "speech_act": speech_act,
        "geo": geo,
        "geo_markers": geo_markers,
        "border_alert": border_alert,
    }


def get_analysis(record) -> Dict[str, Any]:
    """
    Read the analysis block off a ScrapedData row.

    Falls back to the pre-unification key layout so records written by the old
    split pipelines still render correctly.
    """
    meta = record.metadata_json or {}
    if isinstance(meta.get("analysis"), dict):
        return meta["analysis"]

    # Legacy: simulator wrote these keys at the top level of metadata_json.
    legacy_threat = meta.get("threat_classifier") or meta.get("ai_analysis") or {}
    return {
        "schema_version": 1,
        "analyzed_at": None,
        "normalized_text": meta.get("normalized_text", record.cleaned_text),
        "detected_slang": meta.get("detected_slang", []),
        "slang_count": len(meta.get("detected_slang", []) or []),
        "entities": record.flagged_entities or meta.get("extracted_entities") or {},
        "threat": {
            "threat_level": record.threat_level,
            "risk_score": legacy_threat.get("risk_score", 0),
            "intent": legacy_threat.get("intent", "UNKNOWN"),
            "modus_operandi": legacy_threat.get("modus_operandi", []),
            "requires_immediate_action": record.threat_level in ("HIGH", "SEVERE"),
        },
        "geo": meta.get("geo_resolver"),
        "geo_markers": [],
        "border_alert": meta.get("border_alert", False),
    }


# ─────────────────────────────────────────────────────────────────────
# Persistence — every ingest path writes through store_intelligence()
# ─────────────────────────────────────────────────────────────────────

INTERCEPT_LABEL_CHARS = 70


def intercept_label_for(record_id: int, title: Optional[str] = None,
                        source_url: Optional[str] = None) -> str:
    """
    A name an investigator can recognise on the graph.

    Nodes were labelled "Intercept #14", which tells a reader nothing: to find
    out what a node was they had to leave the graph and look the id up. The
    page title is used where one was captured, then the last meaningful part
    of the URL, and only then the bare id - so a node always says as much as
    the collection actually knows about it.
    """
    title = (title or "").strip()
    if title:
        short = title[:INTERCEPT_LABEL_CHARS].strip()
        return short + ("..." if len(title) > INTERCEPT_LABEL_CHARS else "")

    if source_url:
        from urllib.parse import urlparse
        parsed = urlparse(source_url)
        tail = [part for part in parsed.path.split("/") if part]
        if tail:
            readable = tail[-1].replace("_", " ").replace("-", " ")[:INTERCEPT_LABEL_CHARS]
            return f"{parsed.netloc}: {readable}" if readable else parsed.netloc
        if parsed.netloc:
            return parsed.netloc

    return f"Intercept #{record_id}"


async def sync_graph(record_id: int, source_type: str, author: Optional[str],
                     analysis: Dict[str, Any], title: Optional[str] = None,
                     source_url: Optional[str] = None) -> int:
    """Mirror an analysed record into the correlation graph. Returns edges added."""
    from database.graph_db import graph_manager

    entities = analysis.get("entities") or {}
    intercept_id = slugify_entity_key(str(record_id), "intercept")
    intercept_label = intercept_label_for(record_id, title, source_url)
    intercept_type = "channel" if source_type == "TELEGRAM" else "onion"
    edges = 0

    actor_id = None
    if author:
        actor_id = slugify_entity_key(author, "suspect")
        await graph_manager.add_entity_link(
            source_id=actor_id, source_label=f"Actor: {author}", source_type="suspect",
            target_id=intercept_id, target_label=intercept_label, target_type=intercept_type,
            relation="TRANSMITTED", evidence_record_id=record_id,
        )
        edges += 1

    for drug in entities.get("drugs", []) or []:
        await graph_manager.add_entity_link(
            source_id=intercept_id, source_label=intercept_label, source_type=intercept_type,
            target_id=slugify_entity_key(drug, "drug"),
            target_label=f"Substance: {canonical_drug_name(drug)}", target_type="drug",
            relation="MENTIONS_NARCOTIC", evidence_record_id=record_id,
        )
        edges += 1

    for wallet in _flatten_wallets(entities):
        await graph_manager.add_entity_link(
            source_id=actor_id or intercept_id,
            source_label=f"Actor: {author}" if actor_id else intercept_label,
            source_type="suspect" if actor_id else intercept_type,
            # Full address, never a prefix: twelve characters were not
            # enough to keep two different wallets apart.
            target_id=slugify_entity_key(wallet, "wallet"),
            target_label=f"Wallet: {wallet[:10]}...",
            target_type="wallet", relation="USES_CRYPTO",
            evidence_record_id=record_id,
        )
        edges += 1

    return edges


async def _record_wallets(session, entities: Dict[str, Any], source_url: str, risk_score: int):
    """Upsert discovered crypto addresses into the tracked-wallet table."""
    from sqlalchemy import select
    from database.postgres import CryptoWalletIntel

    wallets = entities.get("crypto_wallets") or {}
    if not isinstance(wallets, dict):
        return

    for chain, addresses in wallets.items():
        for address in addresses or []:
            existing = (await session.execute(
                select(CryptoWalletIntel).where(CryptoWalletIntel.wallet_address == address)
            )).scalars().first()
            if existing:
                existing.last_activity = datetime.utcnow()
                existing.risk_score = max(existing.risk_score or 0, risk_score)
            else:
                session.add(CryptoWalletIntel(
                    wallet_address=address,
                    crypto_type=chain.upper(),
                    associated_source_url=source_url,
                    risk_score=risk_score,
                    last_activity=datetime.utcnow(),
                ))


async def store_intelligence(
    source_type: str,
    source_url: str,
    raw_content: str,
    cleaned_text: Optional[str] = None,
    author: Optional[str] = None,
    target_id: Optional[int] = None,
    ocr_text: Optional[str] = None,
    provenance: Optional[Dict[str, Any]] = None,
    analysis: Optional[Dict[str, Any]] = None,
    media_items: Optional[List[Dict[str, Any]]] = None,
    session=None,
) -> Dict[str, Any]:
    """
    Analyse (if needed) and persist one intercept.

    Writes the ScrapedData row, indexes it into ChromaDB, records any crypto
    wallets, and mirrors the entities into the correlation graph.

    Pass `session` to join a request-scoped transaction; otherwise a session is
    opened here.
    """
    from database.postgres import AsyncSessionLocal, ScrapedData, MediaArtifact
    from database.vector_store import vector_store
    from media.pipeline import media_text_blob, summarize_media

    cleaned_text = cleaned_text or raw_content[:2000]
    media_items = media_items or []

    # Text recovered from attached media (OCR output, resolved GPS districts)
    # is analysed alongside the page text, so a phone number visible only
    # inside a screenshot is still extracted and scored.
    media_blob = media_text_blob(media_items) if media_items else ""

    if analysis is None:
        analysis = analyze_text(
            " ".join(filter(None, [cleaned_text, ocr_text, media_blob])).strip()
        )

    # Record what the media contributed, and let a border GPS fix raise the
    # alert even when the text itself never mentions a location.
    analysis["media"] = summarize_media(media_items)
    if analysis["media"]["in_border_corridor"] > 0 and not analysis.get("border_alert"):
        analysis["border_alert"] = True
        analysis["threat"]["border_escalated_by_media"] = True
        if analysis["threat"]["threat_level"] in ("MEDIUM", "HIGH"):
            analysis["threat"]["threat_level"] = "SEVERE"

    threat = analysis.get("threat", {})
    threat_level = threat.get("threat_level", "LOW")
    content_hash = generate_sha256(raw_content)

    metadata = {
        "analysis": analysis,
        "provenance": provenance or {},
    }

    async def _resight(db, existing) -> None:
        """
        Record that identical content was collected again.

        A scheduled crawler revisiting the same page every few minutes was
        inserting a fresh row each pass. Correlation counts sightings, so this
        did not merely waste space - it manufactured evidence, turning one
        Wikipedia page into a six-sighting "hotspot". Re-collection is now
        logged on the original record instead of becoming a new one.
        """
        meta = dict(existing.metadata_json or {})
        prov = dict(meta.get("provenance") or {})
        prov["times_collected"] = int(prov.get("times_collected", 1)) + 1
        prov["last_collected_at"] = datetime.utcnow().isoformat() + "Z"
        meta["provenance"] = prov
        existing.metadata_json = meta          # reassign so SQLAlchemy sees it
        await db.commit()

    async def _find_existing(db):
        """Same bytes from the same URL is a re-collection, not new evidence."""
        from sqlalchemy import select
        return (await db.execute(
            select(ScrapedData)
            .where(ScrapedData.sha256_hash == content_hash)
            .where(ScrapedData.source_url == source_url)
        )).scalars().first()

    async def _write(db) -> int:
        record = ScrapedData(
            target_id=target_id,
            source_type=source_type.upper(),
            source_url=source_url,
            raw_content=raw_content,
            cleaned_text=cleaned_text,
            ocr_extracted_text=ocr_text,
            sha256_hash=content_hash,
            author_or_handle=author,
            published_at=datetime.utcnow(),
            threat_level=threat_level,
            flagged_entities=analysis.get("entities"),
            metadata_json=metadata,
        )
        db.add(record)
        await _record_wallets(db, analysis.get("entities") or {}, source_url,
                              threat.get("risk_score", 0))
        await db.flush()          # assign record.id before linking media

        for item in media_items:
            geo = item.get("geo") or {}
            gps = item.get("gps") or {}
            db.add(MediaArtifact(
                scraped_data_id=record.id,
                source_url=item["url"],
                local_path=item.get("path"),
                media_type=item.get("media_type", "IMAGE"),
                mime_type=item.get("mime_type"),
                file_size=item.get("size", 0),
                sha256_hash=item["sha256"],
                width=item.get("width"),
                height=item.get("height"),
                duration_seconds=item.get("duration_seconds"),
                exif_json=item.get("exif") or {},
                capture_timestamp=item.get("capture_timestamp"),
                device_signature=item.get("device_signature"),
                gps_lat=gps.get("lat"),
                gps_lon=gps.get("lon"),
                geo_json=geo or None,
                in_border_corridor=bool(item.get("in_border_corridor")),
                ocr_text=item.get("ocr_text") or None,
            ))

        await db.commit()
        await db.refresh(record)
        return record.id

    async def _persist(db):
        """Returns (record_id, is_duplicate)."""
        existing = await _find_existing(db)
        if existing is not None:
            await _resight(db, existing)
            logger.info("Re-collected identical content for %s; folded into record %d",
                        source_url, existing.id)
            return existing.id, True
        return await _write(db), False

    if session is not None:
        record_id, is_duplicate = await _persist(session)
    else:
        async with AsyncSessionLocal() as db:
            record_id, is_duplicate = await _persist(db)

    if is_duplicate:
        # Already analysed, indexed and graphed on first collection. Repeating
        # that work would only re-embed text the vector store already holds.
        return {
            "id": record_id,
            "record_id": record_id,
            "status": "DUPLICATE",
            "url": source_url,
            "sha256_hash": content_hash,
            "threat_level": threat_level,
            "border_alert": analysis.get("border_alert", False),
            "graph_edges_added": 0,
            "media": analysis.get("media"),
            "analysis": analysis,
        }

    # Index into the vector store so semantic search can reach this record.
    searchable = " ".join(filter(None, [
        cleaned_text, ocr_text, analysis.get("normalized_text"),
    ])).strip()
    if searchable:
        vector_store.add_intelligence(
            doc_id=f"{source_type.upper()}_{record_id}",
            text_content=searchable,
            metadata={
                "record_id": record_id,
                "source_type": source_type.upper(),
                "url": source_url,
                "author": author or "",
                "sha256": content_hash,
                "threat_level": threat_level,
            },
        )

    graph_edges = await sync_graph(
        record_id, source_type.upper(), author, analysis,
        title=(provenance or {}).get('title'), source_url=source_url)

    return {
        "id": record_id,
        "record_id": record_id,
        "status": "SAVED",
        "url": source_url,
        "sha256_hash": content_hash,
        "threat_level": threat_level,
        "border_alert": analysis.get("border_alert", False),
        "graph_edges_added": graph_edges,
        "media": analysis.get("media"),
        "analysis": analysis,
    }


async def fetch_raw_content(record_id: Optional[int]) -> str:
    """
    Read back the stored page source for a record.

    Crawlers need the HTML they just collected in order to follow its links,
    but store_intelligence() deliberately does not return it - the same dict is
    serialised into API responses, and putting a megabyte of page source in
    every scrape reply would be wasteful and would leak raw content to callers
    that only asked whether the save succeeded.

    Both crawlers previously read `result["raw_content"]`, a key that has never
    existed in that dict. The dark web crawler therefore returned an empty list
    on every run and the surface crawler skipped every page, so link-following
    discovery silently did nothing on both pipelines.
    """
    if record_id is None:
        return ""

    from sqlalchemy import select
    from database.postgres import AsyncSessionLocal, ScrapedData

    async with AsyncSessionLocal() as db:
        record = (await db.execute(
            select(ScrapedData).where(ScrapedData.id == record_id)
        )).scalars().first()
        return (record.raw_content or "") if record else ""


async def reindex_vector_store(limit: int = 1000) -> Dict[str, Any]:
    """
    Backfill the ChromaDB index from the database.

    Records collected while chromadb was unavailable were stored but never
    embedded, leaving them invisible to semantic search. This re-indexes them
    from what is already in the database - no re-scraping needed.
    """
    from sqlalchemy import select
    from database.postgres import AsyncSessionLocal, ScrapedData
    from database.vector_store import vector_store

    if not vector_store.collection:
        return {
            "status": "UNAVAILABLE",
            "indexed": 0,
            "message": "ChromaDB is not initialised; install chromadb and restart.",
        }

    indexed = 0
    skipped = 0

    async with AsyncSessionLocal() as session:
        records = (await session.execute(
            select(ScrapedData).order_by(ScrapedData.id).limit(limit)
        )).scalars().all()

        for rec in records:
            analysis = get_analysis(rec)
            searchable = " ".join(filter(None, [
                rec.cleaned_text,
                rec.ocr_extracted_text,
                analysis.get("normalized_text"),
            ])).strip()

            if not searchable:
                skipped += 1
                continue

            ok = vector_store.add_intelligence(
                doc_id=f"{rec.source_type}_{rec.id}",
                text_content=searchable,
                metadata={
                    "record_id": rec.id,
                    "source_type": rec.source_type,
                    "url": rec.source_url or "",
                    "author": rec.author_or_handle or "",
                    "sha256": rec.sha256_hash or "",
                    "threat_level": rec.threat_level or "UNREVIEWED",
                },
            )
            indexed += 1 if ok else 0

    return {
        "status": "SUCCESS",
        "indexed": indexed,
        "skipped_empty": skipped,
        "total_examined": indexed + skipped,
    }
