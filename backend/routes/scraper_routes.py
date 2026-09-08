"""
Scraper & Crawler Control Endpoints.
Allows investigators to manually trigger scrapes, launch crawlers, and monitor jobs.
"""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime

from database.postgres import get_db, ScrapeJob, Target
from scrapers.surface_web.scraper import SurfaceWebScraper
from scrapers.dark_web.scraper import DarkWebScraper
from scrapers.encrypted.telegram_scraper import TelegramScraper
from evidence.audit_log import record_audit_event
from auth.rbac import require_investigator

router = APIRouter(
    prefix="/api/scrape", tags=["Scraper Control"],
    # Every endpoint on this router requires authentication.
    dependencies=[Depends(require_investigator)],
)

surface_scraper = SurfaceWebScraper()
dark_scraper = DarkWebScraper()
telegram_scraper = TelegramScraper()


class TriggerScrapeRequest(BaseModel):
    pipeline: str  # SURFACE_WEB, DARK_WEB, TELEGRAM
    target: str    # URL, .onion, or @channel
    mode: Optional[str] = "scrape"  # "scrape" or "crawl"
    max_depth: Optional[int] = 2


# Result statuses that mean nothing was collected, even though the scraper
# returned normally instead of raising.
_FAILURE_STATUSES = {"FAILED", "BLOCKED", "ERROR", "UNREACHABLE", "EMPTY"}


def _interpret_result(result, mode: str):
    """
    Decide what actually happened, from what the scraper returned.

    A job used to be marked COMPLETED whenever no exception escaped, with
    `items_scraped` hardcoded to 1. The scrapers report failure by returning
    {"status": "FAILED", ...} rather than by raising, so a .onion fetch
    attempted with no Tor daemon running was recorded as a completed job that
    collected one item - while the database received nothing. An operator
    reading the jobs table would have believed the service was scraped.

    Returns (status, items_scraped, error_message).
    """
    if isinstance(result, dict):
        status = str(result.get("status", "")).upper()
        if status in _FAILURE_STATUSES or result.get("error"):
            message = result.get("error") or result.get("note") or status
            return "FAILED", 0, str(message)[:1000]
        # A duplicate is a successful visit that produced no new evidence.
        if status == "DUPLICATE":
            return "COMPLETED", 0, None
        # A channel scrape stores one record per message, so the count comes
        # from the scraper rather than being assumed to be one.
        if isinstance(result.get("stored"), int):
            return "COMPLETED", result["stored"], None
        return "COMPLETED", 1, None

    if isinstance(result, (list, tuple)):
        # Crawl mode. Count records that were actually stored, not the number
        # of URLs the crawler happened to touch.
        stored = sum(
            1 for item in result
            if isinstance(item, dict)
            and str(item.get("status", "")).upper() not in _FAILURE_STATUSES
            and not item.get("error")
        )
        failed = len(result) - stored
        error = f"{failed} of {len(result)} targets failed" if failed else None
        return ("COMPLETED" if stored else "FAILED"), stored, error

    return "COMPLETED", 0, None


async def _run_scrape_task(pipeline: str, target: str, mode: str, job_id: int):
    """Background execution worker for scraping and crawling."""
    from database.postgres import AsyncSessionLocal

    try:
        if pipeline == "SURFACE_WEB":
            if mode == "crawl":
                result = await surface_scraper.crawl(target)
            else:
                result = await surface_scraper.scrape(target)
        elif pipeline == "DARK_WEB":
            if mode == "crawl":
                result = await dark_scraper.crawl(target)
            else:
                result = await dark_scraper.scrape(target)
        elif pipeline == "TELEGRAM":
            if mode == "crawl":
                result = await telegram_scraper.crawl(target)
            else:
                result = await telegram_scraper.scrape(target)
        else:
            result = {"error": f"Unknown pipeline {pipeline}"}

        status, items, error = _interpret_result(result, mode)

        async with AsyncSessionLocal() as session:
            stmt = select(ScrapeJob).where(ScrapeJob.id == job_id)
            job = (await session.execute(stmt)).scalars().first()
            if job:
                job.status = status
                job.items_scraped = items
                job.error_message = error
                job.completed_at = datetime.utcnow()
                await session.commit()

    except Exception as e:
        async with AsyncSessionLocal() as session:
            stmt = select(ScrapeJob).where(ScrapeJob.id == job_id)
            job = (await session.execute(stmt)).scalars().first()
            if job:
                job.status = "FAILED"
                job.error_message = str(e)
                job.completed_at = datetime.utcnow()
                await session.commit()


@router.post("/trigger")
async def trigger_scrape(
    req: TriggerScrapeRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Trigger a scraping or crawling operation across any of the 3 ingestion pipelines."""
    # Create tracking job
    job = ScrapeJob(
        pipeline=req.pipeline.upper(),
        target_identifier=req.target,
        status="RUNNING"
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Dispatch to background task
    background_tasks.add_task(
        _run_scrape_task,
        pipeline=req.pipeline.upper(),
        target=req.target,
        mode=req.mode,
        job_id=job.id
    )

    await record_audit_event(
        action=f"TRIGGER_{req.pipeline.upper()}_{req.mode.upper()}",
        resource=req.target,
        details=f"Job ID {job.id} enqueued"
    )

    return {
        "message": f"Successfully launched {req.mode} task on {req.pipeline}",
        "job_id": job.id,
        "target": req.target,
        "status": "RUNNING"
    }


@router.get("/jobs")
async def get_recent_jobs(db: AsyncSession = Depends(get_db)):
    """Fetch the latest scraper execution jobs."""
    stmt = select(ScrapeJob).order_by(ScrapeJob.started_at.desc()).limit(20)
    jobs = (await db.execute(stmt)).scalars().all()
    return jobs


class AhmiaDiscoveryRequest(BaseModel):
    query: str
    limit: int = 25
    # Named queue_targets rather than register: `register` shadows an
    # attribute Pydantic's BaseModel inherits, which pydantic warns about.
    queue_targets: bool = True
    use_tor: Optional[bool] = None


@router.post("/discover/ahmia")
async def discover_via_ahmia(req: AhmiaDiscoveryRequest):
    """
    Find hidden services through the Ahmia search engine.

    The dark web crawler can only follow links out of onion sites it already
    holds, so it needs somewhere to start. This turns a search term into
    candidate .onion addresses and queues them as targets.

    Ahmia's index entries are not stored as intelligence - they describe a
    service rather than being its content. A discovered address becomes
    intelligence only when the Tor crawler fetches the service itself, which
    requires Tor to be running.
    """
    from scrapers.dark_web.ahmia_discovery import AhmiaDiscovery

    result = await AhmiaDiscovery(use_tor=req.use_tor).discover(
        query=req.query, limit=req.limit, register=req.queue_targets)

    await record_audit_event(
        action="DARK_WEB_DISCOVERY",
        resource="ahmia",
        details=(f"Query {req.query!r} via {result.get('endpoint')}: "
                 f"{result.get('result_count', 0)} services, "
                 f"{result.get('registration', {}).get('registered_count', 0)} "
                 f"newly queued"),
    )
    return result


class OnionSearchRequest(BaseModel):
    query: str
    engines: Optional[list] = None
    limit: int = 50
    queue_targets: bool = True
    # Off by default. Auto-activating means unattended collection from
    # addresses no person has looked at; see scrapers/dark_web/onion_search.py.
    auto_activate_filtered: bool = False


@router.post("/discover/onion-search")
async def discover_via_onion_search(req: OnionSearchRequest):
    """
    Search several dark web indexes at once for hidden services.

    Ahmia alone was a single point of failure - when its backend started
    returning gateway errors, discovery stopped while the rest of the Tor
    pipeline worked. Sixteen engines are queried and their results pooled,
    with each address recording which engines returned it: agreement between
    independent indexes is the only corroboration available at this stage.

    Discovered addresses are held as PENDING_REVIEW and are NOT collected.
    Only Ahmia filters abuse material from its index; the rest filter nothing,
    and this system stores whatever it fetches. An investigator approves an
    address in Sources before anything is retrieved from it.
    """
    from scrapers.dark_web.onion_search import onion_search

    result = await onion_search.discover(
        query=req.query, engines=req.engines, limit=req.limit,
        queue_targets=req.queue_targets,
        auto_activate_filtered=req.auto_activate_filtered)

    registration = result.get("registration", {})
    await record_audit_event(
        action="DARK_WEB_MULTI_ENGINE_DISCOVERY",
        resource="onion_search",
        details=(f"Query {req.query!r}: {result.get('engines_responded', 0)}/"
                 f"{result.get('engines_queried', 0)} engines responded, "
                 f"{result.get('result_count', 0)} services found, "
                 f"{registration.get('pending_review_count', 0)} held for review"),
    )
    return result


@router.get("/discover/engines")
async def list_search_engines():
    """The onion search engines available, and whether each filters abuse material."""
    from scrapers.dark_web.onion_search import ENGINES

    return {
        "engines": [{"name": e["name"], "filters_abuse": e["filters_abuse"]}
                    for e in ENGINES],
        "count": len(ENGINES),
        "note": ("Only engines marked filters_abuse remove child sexual abuse "
                 "material from their index. Results from the others are held "
                 "for human review before any collection."),
    }
