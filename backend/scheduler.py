"""
Continuous Background Intelligence Scheduler.

Runs three autonomous jobs:

  1. SURVEILLANCE  - revisit every active target on its own interval and file
                     whatever it finds. This is the 24/7 collection loop.
  2. ANALYSIS      - re-score records through the shared enrichment pipeline,
                     picking up anything ingested without a threat level.
  3. MAINTENANCE   - refresh the proxy pool health metrics.

Failure handling matters here: a target that is down, blocked, or removed must
not stall the loop or fill the log forever. Each failure backs the target off
exponentially, and a target that fails repeatedly is paused for human review
rather than retried indefinitely.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger("scheduler")

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
except ImportError:
    AsyncIOScheduler = None

# How often the surveillance job wakes to look for due targets. Individual
# targets are still governed by their own scan_interval_minutes.
SURVEILLANCE_TICK_MINUTES = 2

# Targets scraped per tick, so one cycle cannot monopolise the event loop.
MAX_TARGETS_PER_TICK = 5

# Consecutive failures before a target is paused for review.
FAILURE_PAUSE_THRESHOLD = 5

# Backoff multiplier applied to the interval after each consecutive failure.
FAILURE_BACKOFF_CAP_MINUTES = 720  # 12 hours


class BackgroundIntelligenceScheduler:
    """Owns the autonomous collection and analysis jobs."""

    def __init__(self):
        self.scheduler = AsyncIOScheduler() if AsyncIOScheduler else None
        self.is_running = False
        self.last_surveillance_run: Optional[str] = None
        self.last_surveillance_result: Dict[str, Any] = {}
        self._busy = False

    # ── Lifecycle ────────────────────────────────────────────────────

    def start(self):
        if not self.scheduler:
            logger.warning("APScheduler is not installed. Continuous collection disabled.")
            return

        self.scheduler.add_job(
            self._scheduled_surveillance, "interval",
            minutes=SURVEILLANCE_TICK_MINUTES,
            id="surveillance_job", replace_existing=True,
            max_instances=1, coalesce=True,
        )
        self.scheduler.add_job(
            self._scheduled_ai_analysis, "interval",
            minutes=10, id="analysis_job", replace_existing=True,
            max_instances=1, coalesce=True,
        )
        self.scheduler.add_job(
            self._scheduled_proxy_refresh, "interval",
            minutes=15, id="proxy_refresh_job", replace_existing=True,
            max_instances=1, coalesce=True,
        )

        try:
            self.scheduler.start()
            self.is_running = True
            logger.info("Continuous surveillance scheduler started "
                        "(tick every %d min).", SURVEILLANCE_TICK_MINUTES)
        except Exception as e:
            logger.error("Failed to start scheduler: %s", e)

    def shutdown(self):
        if self.scheduler and self.is_running:
            self.scheduler.shutdown(wait=False)
            self.is_running = False
            logger.info("Scheduler stopped.")

    def job_summary(self) -> List[Dict[str, Any]]:
        """Describe the registered jobs for the surveillance status endpoint."""
        if not self.scheduler or not self.is_running:
            return []
        out = []
        for job in self.scheduler.get_jobs():
            out.append({
                "id": job.id,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            })
        return out

    # ── Job 1: continuous surveillance ───────────────────────────────

    async def _scheduled_surveillance(self):
        """Scrape every target whose scan interval has elapsed."""
        if self._busy:
            logger.debug("Surveillance tick skipped; previous cycle still running.")
            return
        self._busy = True
        try:
            await self._run_surveillance_cycle()
        except Exception as e:
            logger.error("Surveillance cycle failed: %s: %s", type(e).__name__, e)
        finally:
            self._busy = False

    async def _run_surveillance_cycle(self) -> Dict[str, Any]:
        from sqlalchemy import select, or_
        from database.postgres import AsyncSessionLocal, Target

        now = datetime.utcnow()
        scraped, failed = 0, 0

        async with AsyncSessionLocal() as session:
            due = (await session.execute(
                select(Target)
                .where(Target.status == "ACTIVE")
                .where(or_(Target.next_scan_at.is_(None), Target.next_scan_at <= now))
                .order_by(Target.priority.desc(), Target.next_scan_at.asc().nullsfirst())
                .limit(MAX_TARGETS_PER_TICK)
            )).scalars().all()

            if not due:
                self.last_surveillance_run = now.isoformat() + "Z"
                return {"due": 0, "scraped": 0, "failed": 0}

            logger.info("Surveillance: %d target(s) due for collection.", len(due))

            for target in due:
                ok = await self._collect_target(target)
                if ok:
                    scraped += 1
                else:
                    failed += 1
                self._reschedule(target, success=ok, now=datetime.utcnow())

            await session.commit()

        result = {"due": len(due), "scraped": scraped, "failed": failed}
        self.last_surveillance_run = now.isoformat() + "Z"
        self.last_surveillance_result = result
        logger.info("Surveillance cycle complete: %s", result)
        return result

    async def _collect_target(self, target) -> bool:
        """Run the appropriate scraper for one target. Returns success."""
        from scrapers.surface_web.scraper import SurfaceWebScraper
        from scrapers.dark_web.scraper import DarkWebScraper
        from scrapers.encrypted.telegram_scraper import TelegramScraper

        scrapers = {
            "SURFACE_WEB": SurfaceWebScraper,
            "DARK_WEB": DarkWebScraper,
            "TELEGRAM": TelegramScraper,
        }
        scraper_cls = scrapers.get(target.source_type)
        if not scraper_cls:
            target.last_error = f"No scraper for source type {target.source_type}"
            return False

        try:
            scraper = scraper_cls()
            scraper.active_target_id = target.id
            result = await scraper.scrape(target.identifier)
            status = (result or {}).get("status")

            # DUPLICATE means the source was reached and everything it holds
            # is already collected. That is a successful check, not an error -
            # it is the expected outcome for any source revisited before it
            # publishes anything new, which for most sources is most visits.
            #
            # Counting it as a failure made the deduplication added upstream
            # actively harmful: a healthy target accumulated "failures" every
            # time it was polled, and was auto-paused once it reached the
            # threshold. The better the source behaved, the sooner collection
            # from it stopped.
            if status in ("SAVED", "DUPLICATE"):
                collected = result.get("stored") if isinstance(
                    result.get("stored"), int) else (1 if status == "SAVED" else 0)
                target.total_records_collected = (
                    target.total_records_collected or 0) + collected
                target.consecutive_failures = 0
                target.last_error = None

                if collected:
                    logger.info("Collected %d from %s (threat %s)",
                                collected, target.identifier,
                                result.get("threat_level"))
                else:
                    logger.info("Checked %s; nothing new since the last visit",
                                target.identifier)
                return True

            # BLOCKED / FAILED come back as structured results, not exceptions.
            target.last_error = (result or {}).get("error") or f"status={status}"
            return False

        except Exception as e:
            target.last_error = f"{type(e).__name__}: {e}"
            logger.warning("Collection failed for %s: %s", target.identifier, e)
            return False

    def _reschedule(self, target, success: bool, now: datetime):
        """Set the next scan time, backing off after failures."""
        target.last_scraped_at = now
        interval = max(target.scan_interval_minutes or 60, 5)

        if success:
            target.consecutive_failures = 0
            target.next_scan_at = now + timedelta(minutes=interval)
            return

        failures = (target.consecutive_failures or 0) + 1
        target.consecutive_failures = failures

        if failures >= FAILURE_PAUSE_THRESHOLD:
            target.status = "PAUSED"
            target.next_scan_at = None
            logger.warning("Target '%s' paused after %d consecutive failures: %s",
                           target.identifier, failures, target.last_error)
            return

        # Exponential backoff, capped, so a dead target is retried sparingly.
        backoff = min(interval * (2 ** failures), FAILURE_BACKOFF_CAP_MINUTES)
        target.next_scan_at = now + timedelta(minutes=backoff)

    # ── Job 2: batch analysis ────────────────────────────────────────

    async def _scheduled_ai_analysis(self):
        try:
            from ai.batch_analysis import batch_analyzer
            result = await batch_analyzer.run_batch_analysis(limit=15)
            logger.info("Scheduled analysis: %s record(s) processed.",
                        result.get("processed_records"))
        except Exception as e:
            logger.error("Scheduled analysis failed: %s", e)

    # ── Job 3: proxy maintenance ─────────────────────────────────────

    async def _scheduled_proxy_refresh(self):
        try:
            from proxy.pool import proxy_pool
            await proxy_pool.initialize()
        except Exception as e:
            logger.error("Proxy refresh failed: %s", e)

    # ── Manual trigger ───────────────────────────────────────────────

    async def run_now(self) -> Dict[str, Any]:
        """Force one surveillance cycle immediately (used by the API)."""
        if self._busy:
            return {"status": "BUSY", "message": "A collection cycle is already running."}
        self._busy = True
        try:
            result = await self._run_surveillance_cycle()
            return {"status": "SUCCESS", **result}
        finally:
            self._busy = False


intel_scheduler = BackgroundIntelligenceScheduler()
