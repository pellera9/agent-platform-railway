"""
Workflows
=========

Runnable Agno ``Workflow`` objects — the deterministic background jobs the
scheduler can fire (see `app/schedules.py`) and that are also runnable on demand
via the OS workflow router (``POST /workflows/<id>/runs``). Each module owns one
concern end to end: its step executor(s) and the ``Workflow`` that wraps them.

``WORKFLOWS`` is the registration list handed to ``AgentOS(workflows=...)`` in
`app/main.py`. *Which* of these fire on a schedule (and when) is a separate,
cross-cutting concern that lives in `app/schedules.py`, not here.
"""

from agno.workflow import RemoteWorkflow, Workflow, WorkflowFactory

from workflows.digest import daily_digest_workflow

# Explicit element type matches AgentOS's ``workflows=`` parameter so the list
# types cleanly at the call site (a bare list literal infers as the invariant
# ``list[Workflow]`` and would be rejected).
WORKFLOWS: list[Workflow | RemoteWorkflow | WorkflowFactory] = [
    daily_digest_workflow,
]

__all__ = ["WORKFLOWS", "daily_digest_workflow"]
