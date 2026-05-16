"""FastAPI service — exposes /trigger and /status, runs scheduled scrapes."""
import asyncio
import logging
import os
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, HTTPException

from .db import get_session
from .models import ArchonScrapeRun
from .runner import run_scrape

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

_running = False
_current_task: asyncio.Task | None = None


async def _run_and_clear():
    global _running, _current_task
    try:
        await run_scrape()
    except Exception as exc:
        logger.error("Scrape failed: %s", exc)
    finally:
        _running = False
        _current_task = None


def _start_scrape() -> bool:
    global _running, _current_task
    if _running:
        return False
    _running = True
    _current_task = asyncio.create_task(_run_and_clear())
    return True


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = AsyncIOScheduler()
    schedule = os.getenv("SCRAPE_SCHEDULE")
    if schedule:
        scheduler.add_job(_start_scrape, CronTrigger.from_crontab(schedule))
        logger.info("Scrape scheduled: %s", schedule)
    else:
        logger.info("No SCRAPE_SCHEDULE set — manual trigger only")
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="Raidmetrics Scraper", lifespan=lifespan)


@app.post("/trigger")
async def trigger():
    started = _start_scrape()
    if not started:
        raise HTTPException(status_code=409, detail="scrape_already_running")
    return {"started": True}


@app.get("/status")
async def status():
    db = get_session()
    try:
        last_run = (
            db.query(ArchonScrapeRun)
            .order_by(ArchonScrapeRun.started_at.desc())
            .first()
        )
    finally:
        db.close()

    last_run_data = None
    if last_run:
        last_run_data = {
            "id": last_run.id,
            "started_at": last_run.started_at,
            "completed_at": last_run.completed_at,
            "success": last_run.success,
            "error_message": last_run.error_message,
        }

    return {
        "running": _running,
        "last_run": last_run_data,
    }
