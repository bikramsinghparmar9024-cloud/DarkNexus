"""
Batch Re-Analysis.

Re-scores stored records through the shared enrichment pipeline, picking up
anything ingested before analysis existed or collected while a component was
unavailable.

This file was called langgraph_workflow.py and described itself as an
"agentic workflow orchestrator". It never imported LangGraph; the
implementation is a loop over database rows. The name is corrected here
because a module that claims a framework it does not use makes the system
harder to reason about than one that says what it does.
"""

import asyncio
from typing import Dict, Any, List
import logging
from sqlalchemy import select, update

from database.postgres import AsyncSessionLocal, ScrapedData
from ai.enrichment import analyze_text, sync_graph

logger = logging.getLogger("batch_analysis")


class BatchAnalysisState:
    """State object passing through LangGraph nodes."""
    def __init__(self):
        self.pending_records: List[ScrapedData] = []
        self.analyzed_count: int = 0
        self.flagged_severe_count: int = 0
        self.extracted_entities_summary: Dict[str, Any] = {}


class BatchAnalyzer:
    """Agent pipeline orchestrator."""

    async def run_batch_analysis(self, limit: int = 20,
                                 force: bool = False) -> Dict[str, Any]:
        """
        Re-analyse stored records through the shared enrichment pipeline.

        Uses ai.enrichment.analyze_text() - the same function the scrapers and
        the live simulator call - so a re-analysed record ends up with exactly
        the same field layout as a freshly ingested one.

        `force` re-analyses every record rather than only unscored ones. It is
        what to run after an extraction or scoring rule changes: stored
        analysis blocks are snapshots, so a record keeps whatever the rules
        said on the day it was collected until it is scored again. Leaving a
        corrected rule unapplied to existing evidence is how two records come
        to disagree about the same text.
        """
        async with AsyncSessionLocal() as session:
            if force:
                stmt = select(ScrapedData).order_by(ScrapedData.id).limit(limit)
                records = (await session.execute(stmt)).scalars().all()
            else:
                # Prefer records that have never been scored.
                stmt = select(ScrapedData).where(
                    ScrapedData.threat_level == "UNREVIEWED").limit(limit)
                records = (await session.execute(stmt)).scalars().all()

                if not records:
                    stmt = select(ScrapedData).order_by(
                        ScrapedData.created_at.desc()).limit(limit)
                    records = (await session.execute(stmt)).scalars().all()

            analyzed_count = 0
            severe_alerts = []

            for rec in records:
                content = rec.cleaned_text or rec.raw_content
                if not content:
                    continue

                analysis = analyze_text(f"{content} {rec.ocr_extracted_text or ''}".strip())
                threat = analysis["threat"]

                # Write the canonical shape, preserving existing provenance.
                existing_meta = rec.metadata_json or {}
                rec.threat_level = threat["threat_level"]
                rec.flagged_entities = analysis["entities"]
                rec.metadata_json = {
                    **existing_meta,
                    "analysis": analysis,
                    "provenance": existing_meta.get("provenance", {}),
                }

                await sync_graph(
                    rec.id, rec.source_type, rec.author_or_handle, analysis,
                    title=(existing_meta.get('provenance') or {}).get('title'),
                    source_url=rec.source_url)

                analyzed_count += 1
                if threat["threat_level"] in ("HIGH", "SEVERE"):
                    severe_alerts.append({
                        "id": rec.id,
                        "source": rec.source_type,
                        "threat": threat["threat_level"],
                        "risk_score": threat["risk_score"],
                        "border_alert": analysis["border_alert"],
                        "summary": content[:100],
                    })

            await session.commit()

            return {
                "status": "SUCCESS",
                "processed_records": analyzed_count,
                "severe_alerts_count": len(severe_alerts),
                "alerts": severe_alerts,
            }


batch_analyzer = BatchAnalyzer()

# Former name, kept so existing imports keep working.
langgraph_pipeline = batch_analyzer
