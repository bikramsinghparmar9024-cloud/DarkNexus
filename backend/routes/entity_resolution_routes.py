"""
Entity Resolution API Routes.
Provides explainable cross-platform identity correlation endpoints:
- explain-link: Why two entities are connected, with confidence + evidence
- candidates: Find all candidate matches for an entity
- entities: List all entities in the knowledge base
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from ai.entity_resolver import entity_resolver
from ai.corroboration_engine import corroboration_engine
from auth.rbac import require_investigator

router = APIRouter(
    prefix="/api/entity-resolution", tags=["Entity Resolution & Explain Link"],
    # Every endpoint on this router requires authentication.
    dependencies=[Depends(require_investigator)],
)


class ExplainLinkRequest(BaseModel):
    source_entity_id: str = Field(..., example="suspect_tariq_lahori")
    target_entity_id: str = Field(..., example="vendor_afghan_silk")


@router.post("/explain-link")
async def explain_link(req: ExplainLinkRequest):
    """
    Given two entity IDs, produce a full 'Why This Link?' explanation:
    - Confidence score with signal-by-signal breakdown
    - Supporting evidence references (source IDs, snippets, timestamps)
    - Source reliability ratings
    - Contradicting evidence
    - Corroboration assessment
    - Intelligence state recommendation
    """
    await entity_resolver.refresh()
    result = entity_resolver.explain_link(req.source_entity_id, req.target_entity_id)

    if result.get("status") == "NOT_FOUND":
        # Most edges in the graph are observed co-occurrences - an intercept
        # mentioning a substance, an actor using a wallet - not identity
        # claims, so the entity resolver has no relationship for them and this
        # used to return 404. An investigator clicking an edge that plainly
        # exists and being told it does not is worse than showing less: it
        # undermines every other number on the screen.
        #
        # Fall back to what the graph itself records. No confidence score is
        # produced here, because a co-occurrence has no identity signals to
        # score and inventing one would be the more serious failure.
        from database.graph_db import graph_manager

        observed = await graph_manager.describe_edge(
            req.source_entity_id, req.target_entity_id)

        if observed.get("status") == "NO_EDGE":
            raise HTTPException(
                status_code=404,
                detail=("No relationship and no observed connection between "
                        f"{req.source_entity_id} and {req.target_entity_id}."))

        return {
            "status": "OBSERVED_ONLY",
            "explanation_type": "OBSERVATION_HISTORY",
            "source_entity_id": req.source_entity_id,
            "target_entity_id": req.target_entity_id,
            "confidence_score": None,
            "confidence_level": None,
            "note": ("These entities are connected by observation, not by "
                     "identity resolution. Shown below is every record that "
                     "produced the link."),
            **observed,
        }

    # Run corroboration assessment on the evidence
    evidence_cards = result.get("evidence_cards", [])
    if evidence_cards:
        corroboration = corroboration_engine.assess_relationship(
            evidence_sources=evidence_cards,
            signals_matched=result.get("matched_signal_count", 0),
            total_signals=result.get("total_signal_count", 0),
            contradictions=result.get("contradictions", [])
        )
        result["corroboration"] = corroboration

        # Update intelligence state based on corroboration
        if corroboration_engine.should_auto_promote(corroboration):
            result["intelligence_state"] = "CORROBORATED"

    return result


@router.get("/candidates/{entity_id}")
async def get_candidates(entity_id: str):
    """
    Find all candidate identity matches for a given entity.
    Returns ranked list with confidence scores and signal counts.
    """
    await entity_resolver.refresh()
    candidates = entity_resolver.get_candidates(entity_id)
    entity_info = entity_resolver.knowledge_base.get(entity_id)

    if not entity_info:
        raise HTTPException(status_code=404, detail=f"Entity '{entity_id}' not found in knowledge base")

    return {
        "status": "SUCCESS",
        "entity": {
            "id": entity_id,
            "name": entity_info.get("name", entity_id),
            "type": entity_info.get("type", "unknown"),
        },
        "candidate_count": len(candidates),
        "candidates": candidates,
    }


@router.get("/entities")
async def list_entities():
    """List all entities in the knowledge base for exploration."""
    await entity_resolver.refresh()
    entities = entity_resolver.get_all_entities()
    return {
        "status": "SUCCESS",
        "count": len(entities),
        "entities": entities,
    }


@router.get("/relationships")
async def list_relationships():
    """List all known relationships with confidence scores."""
    results = []
    for rel in entity_resolver.relationships:
        confidence_pct, confidence_level = entity_resolver.calculate_confidence(rel["signals"])
        matched_count = sum(1 for s in rel["signals"].values() if s.get("matched"))

        source = entity_resolver.knowledge_base.get(rel["source_entity"], {})
        target = entity_resolver.knowledge_base.get(rel["target_entity"], {})

        results.append({
            "source_entity": {
                "id": rel["source_entity"],
                "name": source.get("name", rel["source_entity"]),
                "type": source.get("type", "unknown"),
            },
            "target_entity": {
                "id": rel["target_entity"],
                "name": target.get("name", rel["target_entity"]),
                "type": target.get("type", "unknown"),
            },
            "confidence": confidence_pct,
            "confidence_level": confidence_level,
            "matched_signals": matched_count,
            "evidence_count": len(rel.get("evidence_sources", [])),
            "contradictions_count": len(rel.get("contradictions", [])),
            "hops": rel.get("hops", 1),
        })

    results.sort(key=lambda x: x["confidence"], reverse=True)
    return {"status": "SUCCESS", "count": len(results), "relationships": results}


@router.post("/rebuild")
async def rebuild_knowledge_base():
    """
    Rebuild the entity knowledge base from collected intelligence.

    Entities and their links are derived from stored records - there is no
    pre-seeded roster, so an empty database yields no entities.
    """
    return await entity_resolver.refresh()
