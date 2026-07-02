"""Pure value objects for the worker dispatch contract.

These are the types the control plane freezes at queue time and a future queue
consumer reads on the worker side. The module is deliberately dependency-free: it
imports no FastAPI, settings/config, database/session/repository/service/router,
worker process, or HTTP transport — only the standard library. Keeping the
contract here lets both the API (via the dispatcher seam) and an isolated worker
package depend on it without pulling in either side's runtime.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class WorkerDispatchPayload:
    """The frozen, worker-bound payload handed to the dispatch seam.

    It carries exactly what an isolated worker needs to reconstruct a
    ``worker_runner.WorkerInput`` and nothing more: the execution id, the
    template id, and the three immutable snapshots frozen at queue time. The
    field set is intentionally identical to ``WorkerInput`` so a future queue
    consumer can build one from this payload field-for-field — this module does
    not import the worker runtime to do so.

    Deliberately excluded: tenant/organization identity, request headers, user
    credentials, result fields, and step evidence. Those are control-plane or
    worker-output concerns, never dispatch inputs.

    ``execution_specification`` still carries the opaque ``kill_switch_token``:
    per ``.claude/rules/scan-authorization.md`` the worker polls that key to
    abort mid-run, so it is a required dispatch control — a capability the worker
    must receive, not a removable secret. No long-lived credential is present.
    """

    execution_id: str
    template_id: str
    execution_specification: Mapping[str, Any]
    scope_snapshot: Mapping[str, Any]
    safety_snapshot: Mapping[str, Any]
