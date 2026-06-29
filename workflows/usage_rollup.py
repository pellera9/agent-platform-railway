"""
Usage Rollup
============

A reference background workflow — the deterministic, schedulable counterpart to a
chat agent. It reads the last 24h of activity straight from Postgres (no LLM, no
token cost), then delivers a per-agent rollup — how many sessions and runs each
agent handled. This is what a scheduler is actually for: a deterministic pipeline,
not an agent on a timer.

Delivery is Slack when configured (``SLACK_BOT_TOKEN`` + ``SLACK_CHANNEL``),
otherwise the rollup is logged. The schedule that fires this only arms when Slack
is set up, so the summary actually reaches someone — see `app/schedules.py`.

Make it yours: change the window, group by ``user_id`` instead, or extend the
query to sum token usage from each session's ``runs`` for a daily cost report.
"""

from os import getenv

from agno.utils.log import log_info, log_warning
from agno.workflow.step import Step, StepInput, StepOutput
from agno.workflow.workflow import Workflow
from sqlalchemy import create_engine, text

from db import db_url, get_postgres_db

# agno stores agent/team/workflow sessions here by default (override with
# PostgresDb(session_table=...)). ``created_at`` is a unix timestamp (seconds).
SESSIONS_TABLE = "agno_sessions"
WINDOW_SECONDS = 24 * 60 * 60


def _post_to_slack(message: str) -> bool:
    """Best-effort: post ``message`` to ``SLACK_CHANNEL``. Returns whether it sent.

    No-op (returns False) unless ``SLACK_BOT_TOKEN`` and ``SLACK_CHANNEL`` are both
    set. Failures are logged and swallowed — delivery is a convenience on top of the
    rollup, never the thing that fails the run.
    """
    token, channel = getenv("SLACK_BOT_TOKEN"), getenv("SLACK_CHANNEL")
    if not (token and channel):
        return False
    try:
        from slack_sdk import WebClient

        WebClient(token=token).chat_postMessage(channel=channel, text=message)
        return True
    except Exception as exc:
        log_warning(f"usage-rollup: Slack delivery failed: {exc}")
        return False


def usage_rollup_step(step_input: StepInput) -> StepOutput:
    """Summarize the last 24h of activity from Postgres. Deterministic — no model.

    Counts sessions and runs per agent over the window, reads only (nothing is
    written or deleted), then delivers the summary to Slack (or logs it).
    """
    query = text(
        f"""
        SELECT
            COALESCE(agent_id, team_id, workflow_id, '(unknown)') AS actor,
            COUNT(*) AS sessions,
            COALESCE(SUM(jsonb_array_length(COALESCE(runs, '[]'::jsonb))), 0) AS runs
        FROM {SESSIONS_TABLE}
        WHERE created_at >= EXTRACT(EPOCH FROM NOW())::bigint - :window
        GROUP BY actor
        ORDER BY sessions DESC
        """
    )
    engine = create_engine(db_url)
    try:
        with engine.connect() as conn:
            rows = conn.execute(query, {"window": WINDOW_SECONDS}).fetchall()
    except Exception as exc:
        # e.g. the sessions table doesn't exist yet on a brand-new database.
        log_warning(f"usage-rollup: could not read {SESSIONS_TABLE}: {exc}")
        return StepOutput(content=f"Usage rollup unavailable: {exc}")
    finally:
        engine.dispose()

    if not rows:
        log_info("usage-rollup: no activity in the last 24h")
        return StepOutput(content="No agent activity in the last 24h.")

    lines = [f"• {r.actor}: {r.sessions} session(s), {r.runs} run(s)" for r in rows]
    totals = f"{sum(r.sessions for r in rows)} session(s), {sum(r.runs for r in rows)} run(s)"
    summary = f"*Usage — last 24h* ({totals})\n" + "\n".join(lines)

    if _post_to_slack(summary):
        log_info("usage-rollup: posted to Slack")
    else:
        log_info("usage-rollup:\n" + summary)
    return StepOutput(content=summary)


# Handed to AgentOS in app/main.py. Its ``id`` is the route the scheduler hits:
# POST /workflows/usage-rollup/runs (see app/schedules.py).
usage_rollup_workflow = Workflow(
    id="usage-rollup",
    name="Usage Rollup",
    description="Summarize the last 24h of agent activity (sessions + runs per agent) from Postgres.",
    db=get_postgres_db(),
    steps=[Step(name="usage-rollup", executor=usage_rollup_step)],
)
