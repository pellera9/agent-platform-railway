"""
Daily Digest Workflow
=====================

A reference background **workflow** — the deterministic, schedulable counterpart
to a chat agent. This one runs the WebSearch agent against a configurable topic
and returns the summary as the workflow's output (persisted to Postgres, visible
at os.agno.com). It's the canonical "proactive run" the scheduler can fire on a
cron — see `app/schedules.py`.

Make it yours: swap the agent, the prompt, or the delivery (the brief is just
logged here — wire a Slack DM, an email, or a DB write to push it somewhere
durable). Keep the shape: one `Step` whose executor does the work, wrapped in a
`Workflow` registered with AgentOS (see `workflows/__init__.py`).
"""

from os import getenv

from agno.utils.log import log_info
from agno.workflow.step import Step, StepInput, StepOutput
from agno.workflow.workflow import Workflow

from db import get_postgres_db

# The subject the digest summarizes. Override with DIGEST_TOPIC.
DIGEST_TOPIC = getenv("DIGEST_TOPIC", "the most important developments in AI agents")

_PROMPT = (
    "Search the web and write a concise digest of {topic} from the last 24 hours. "
    "Lead with the 3-5 most important items as short bullets, each with a source URL. "
    "If nothing notable happened, say so plainly rather than padding."
)


async def daily_digest_step(step_input: StepInput) -> StepOutput:
    """Run the WebSearch agent on the configured topic and return the brief.

    Async because WebSearch's tools (Parallel MCP / SDK) are async — agno's sync
    ``agent.run()`` refuses async tools, so the step goes through ``arun``. The OS
    workflow router awaits step executors, so this composes cleanly. agno inspects
    the signature and only injects ``run_context`` when a step declares it; this
    one doesn't need caller identity, so it takes ``step_input`` alone.
    """
    # Imported lazily so this module stays cheap to import and free of any
    # import-order coupling with the agents package at startup.
    from agents.web_search import web_search

    result = await web_search.arun(input=_PROMPT.format(topic=DIGEST_TOPIC))
    brief = str(result.content).strip() if result.content else ""
    if not brief:
        return StepOutput(content="Daily digest produced no content.")

    # Delivery is intentionally just a log line — this is the seam to customize.
    log_info(f"Daily digest ready ({len(brief)} chars) — topic: {DIGEST_TOPIC}")
    return StepOutput(content=brief)


# The workflow object handed to AgentOS (see workflows/__init__.py). Its ``id``
# is the route segment the scheduler hits: POST /workflows/daily-digest/runs
# (see app/schedules.py).
daily_digest_workflow = Workflow(
    id="daily-digest",
    name="Daily Digest",
    description="Summarize the day's developments on a topic using the WebSearch agent.",
    db=get_postgres_db(),
    steps=[Step(name="daily-digest", executor=daily_digest_step)],
)
