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

    The deployment check runs daily by default. Set `ENABLE_DEPLOY_CHECK=False` to disable.
    """
    if getenv("ENABLE_DEPLOY_CHECK", "True") != "True":
        log_info("schedules: deployment-check disabled (ENABLE_DEPLOY_CHECK=False)")
        return
    try:
        manager = ScheduleManager(get_postgres_db())
        manager.create(
            name="deployment-check",
            cron="0 13 * * *",  # 13:00 UTC daily
            endpoint="/workflows/deployment-check/runs",
            payload={"message": "Scheduled deployment check."},
            description="Daily: verify deployment wiring and readiness.",
            if_exists="update",
        )
        log_info("schedules: registered 'deployment-check'")
    except Exception as exc:
        log_warning(f"schedules: could not register schedules: {exc}")
