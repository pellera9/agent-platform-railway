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

    The deployment check ships off by default. Set `ENABLE_DEPLOY_CHECK=True`
    to run it on a cron. The workflow stays runnable on demand at
    `POST /workflows/deployment-check/runs`.
    """
    if getenv("ENABLE_DEPLOY_CHECK") != "True":
        log_info("schedules: deployment-check off (set ENABLE_DEPLOY_CHECK=True to arm the cron)")
        return
    try:
        manager = ScheduleManager(get_postgres_db())
        manager.create(
            name="deployment-check",
            cron=getenv("DEPLOY_CHECK_CRON", "0 13 * * *"),  # 13:00 UTC daily
            endpoint="/workflows/deployment-check/runs",
            payload={"message": "Scheduled deployment check."},
            description="Daily: verify deployment wiring and readiness.",
            if_exists="update",
        )
        log_info("schedules: registered 'deployment-check'")
    except Exception as exc:
        log_warning(f"schedules: could not register schedules: {exc}")
