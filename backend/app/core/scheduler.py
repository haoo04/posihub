"""APScheduler-based background scheduler.

Configures two recurring jobs:

- ``sync_all_accounts``     every ``SYNC_INTERVAL_MINUTES`` minutes.
- ``write_daily_snapshots`` once per day at ``DAILY_SNAPSHOT_TIME`` local time.

The scheduler is started during FastAPI lifespan and stopped on shutdown.
"""

from __future__ import annotations

from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from ..services.snapshot_service import write_daily_snapshots
from ..services.sync_service import sync_all_accounts
from .config import get_settings
from .logging import get_logger

_logger = get_logger(__name__)
_scheduler: Optional[BackgroundScheduler] = None


def _job_sync() -> None:
    _logger.info("scheduler: running sync_all_accounts")
    try:
        results = sync_all_accounts()
        ok = sum(1 for r in results if r.success)
        _logger.info("scheduler: sync done %d/%d ok", ok, len(results))
    except Exception:
        _logger.exception("scheduler: sync_all_accounts crashed")


def _job_snapshot() -> None:
    _logger.info("scheduler: running write_daily_snapshots")
    try:
        outcome = write_daily_snapshots()
        _logger.info(
            "scheduler: snapshot %s accounts=%d positions=%d",
            outcome.snapshot_date,
            outcome.accounts_written,
            outcome.positions_written,
        )
    except Exception:
        _logger.exception("scheduler: write_daily_snapshots crashed")


def start_scheduler() -> BackgroundScheduler:
    """Start (or return existing) background scheduler."""

    global _scheduler
    if _scheduler is not None and _scheduler.running:
        return _scheduler

    settings = get_settings()
    scheduler = BackgroundScheduler(timezone=settings.app_timezone)

    scheduler.add_job(
        _job_sync,
        trigger=IntervalTrigger(minutes=settings.sync_interval_minutes),
        id="sync_all_accounts",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    hour, minute = settings.daily_snapshot_hour_minute
    scheduler.add_job(
        _job_snapshot,
        trigger=CronTrigger(hour=hour, minute=minute, timezone=settings.app_timezone),
        id="daily_snapshot",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    scheduler.start()
    _scheduler = scheduler
    _logger.info(
        "scheduler started: sync every %dm, snapshot at %02d:%02d %s",
        settings.sync_interval_minutes,
        hour,
        minute,
        settings.app_timezone,
    )
    return scheduler


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is None:
        return
    try:
        _scheduler.shutdown(wait=False)
    except Exception:  # pragma: no cover
        _logger.exception("error while shutting scheduler down")
    _scheduler = None
