"""
Entry point for the always-on service.

- Starts an APScheduler BackgroundScheduler with two cron jobs:
    1. daily_job     -> runs every day at DAILY_JOB_HOUR:DAILY_JOB_MINUTE
    2. weekly_job    -> runs Mondays only at WEEKLY_JOB_HOUR:WEEKLY_JOB_MINUTE
- Exposes a minimal FastAPI app with a health check and manual trigger
  endpoints (useful for testing without waiting for the schedule).

Run with:  uvicorn scheduler:app --host 0.0.0.0 --port 8000
"""
import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI

from config import settings
from daily_job import run_daily_job
from database import init_db
from weekly_job import run_weekly_job

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("scheduler")

scheduler = BackgroundScheduler(timezone="Asia/Kolkata")


def _safe_run(job_fn, job_name: str):
    """Wrap a job so an uncaught exception is logged instead of killing the scheduler thread."""
    try:
        job_fn()
    except Exception:
        logger.exception("Unhandled exception in job '%s'", job_name)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()

    scheduler.add_job(
        _safe_run,
        trigger=CronTrigger(hour=settings.DAILY_JOB_HOUR, minute=settings.DAILY_JOB_MINUTE),
        args=[run_daily_job, "daily_job"],
        id="daily_job",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        _safe_run,
        trigger=CronTrigger(day_of_week="mon", hour=settings.WEEKLY_JOB_HOUR, minute=settings.WEEKLY_JOB_MINUTE),
        args=[run_weekly_job, "weekly_job"],
        id="weekly_job",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.start()
    logger.info(
        "Scheduler started. Daily job at %02d:%02d IST every day. Weekly digest at %02d:%02d IST on Mondays.",
        settings.DAILY_JOB_HOUR, settings.DAILY_JOB_MINUTE,
        settings.WEEKLY_JOB_HOUR, settings.WEEKLY_JOB_MINUTE,
    )

    yield

    scheduler.shutdown(wait=False)
    logger.info("Scheduler stopped.")


app = FastAPI(title="Flight Price Tracker", lifespan=lifespan)


@app.get("/health")
def health():
    jobs = [
        {"id": j.id, "next_run": str(j.next_run_time)} for j in scheduler.get_jobs()
    ]
    return {"status": "ok", "jobs": jobs}


@app.post("/trigger/daily")
def trigger_daily():
    """Manually run the daily fetch+alert job right now (for testing)."""
    _safe_run(run_daily_job, "daily_job_manual")
    return {"status": "daily job executed"}


@app.post("/trigger/weekly")
def trigger_weekly():
    """Manually run the weekly digest job right now (for testing)."""
    _safe_run(run_weekly_job, "weekly_job_manual")
    return {"status": "weekly job executed"}
