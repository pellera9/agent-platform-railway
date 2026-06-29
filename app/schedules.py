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

    The usage rollup is delivered to Slack, so the cron only arms when Slack is
    set up: `SLACK_BOT_TOKEN` + `SLACK_CHANNEL` (the destination). Setting the
    channel is the opt-in — enabling the Slack *interface* alone won't spawn it.
    The workflow stays runnable on demand at `POST /workflows/usage-rollup/runs`.
    """
    if not (getenv("SLACK_BOT_TOKEN") and getenv("SLACK_CHANNEL")):
        log_info("schedules: usage-rollup off (set SLACK_BOT_TOKEN + SLACK_CHANNEL to arm the cron)")
        return
    try:
        manager = ScheduleManager(get_postgres_db())
        manager.create(
            name="usage-rollup",
            cron=getenv("USAGE_ROLLUP_CRON", "0 13 * * *"),  # 13:00 UTC daily
            endpoint="/workflows/usage-rollup/runs",
            payload={"message": "Scheduled usage rollup."},
            description="Daily: post a 24h agent-activity rollup to Slack.",
            if_exists="update",
        )
        log_info("schedules: registered 'usage-rollup'")
    except Exception as exc:
        log_warning(f"schedules: could not register schedules: {exc}")
