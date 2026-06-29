"""
AgentOS Schedules
==================
"""

from os import getenv

from agno.scheduler import ScheduleManager
from agno.utils.log import log_info, log_warning

from db import get_postgres_db


def _enabled(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def register_schedules() -> None:
    """Register background schedules (idempotent — safe on every boot).

    The daily digest is **off by default**: a scheduled agent run costs tokens,
    so a starter template shouldn't fire one unprompted. Set
    ``ENABLE_DAILY_DIGEST=true`` to arm it, and tune the time with
    ``DAILY_DIGEST_CRON`` (UTC). The digest workflow is *always* registered and
    runnable on demand at ``POST /workflows/daily-digest/runs`` — this flag only
    controls the cron trigger.
    """
    if not _enabled(getenv("ENABLE_DAILY_DIGEST")):
        log_info("schedules: daily-digest off (set ENABLE_DAILY_DIGEST=true to arm the cron)")
        return
    try:
        manager = ScheduleManager(get_postgres_db())
        manager.create(
            name="daily-digest",
            cron=getenv("DAILY_DIGEST_CRON", "0 13 * * *"),  # 13:00 UTC daily
            endpoint="/workflows/daily-digest/runs",
            payload={"message": "Scheduled daily digest."},
            description="Daily: summarize the day's developments on a topic.",
            if_exists="update",
        )
        log_info("schedules: registered 'daily-digest'")
    except Exception as exc:
        log_warning(f"schedules: could not register schedules: {exc}")
