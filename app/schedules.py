"""
AgentOS Schedules
==================
"""

from os import getenv

from agno.scheduler import ScheduleManager
from agno.utils.log import log_info, log_warning

from db import get_postgres_db


def register_schedules() -> None:
    """Register schedules (idempotent and fail-soft).

    The daily digest is off by default.

    Set `ENABLE_DAILY_DIGEST=True` to activate.
    """
    if getenv("ENABLE_DAILY_DIGEST") != "True":
        log_info("schedules: daily-digest off (set ENABLE_DAILY_DIGEST=True to arm the cron)")
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
