"""Production kill switch: the worker polls the control plane to abort mid-run.

`scan-authorization.md` requires that the control plane can stop a running scan
and that "a scan that cannot be stopped must not start". The executor polls a
:class:`KillSwitch` before work, between requests, and before returning; this is
the production implementation of that protocol. It GETs the per-execution
kill-switch endpoint, authenticating on the opaque ``kill_switch_token`` the
control plane froze into the execution specification (not the worker credential,
so aborting never depends on that credential's lifecycle).

**Fail-safe = abort.** ``is_active`` returns ``True`` (stop the scan) on the
control plane's explicit ``{"active": true}`` *and* on anything that prevents a
clear "keep going" — a non-200 status (a revoked/expired poll token yields 401),
a malformed body, or a transport error. A worker that cannot positively confirm
it is still permitted to run stops, which also satisfies "a scan that cannot be
stopped must not start": the executor's pre-flight poll fails closed.

Import purity: the pure ``KillSwitch`` protocol and (lazily, inside the call)
``httpx`` — a worker-only dependency never pulled into the API import graph. No
FastAPI, SQLAlchemy, repositories, services, routers, dispatcher, or ``app.main``.
"""

import logging
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from app.modules.validation_executions.executor import KillSwitch

__all__ = [
    "DEFAULT_KILL_SWITCH_POLL_TIMEOUT_SECONDS",
    "ControlPlaneKillSwitch",
    "KillSwitchFactory",
    "build_control_plane_kill_switch_factory",
]

_logger = logging.getLogger("securescope.worker.kill_switch")

# A kill-switch poll is a tiny local GET; a tight default keeps a stalled poll
# from wedging the executor between phases.
DEFAULT_KILL_SWITCH_POLL_TIMEOUT_SECONDS = 5.0

_KILL_SWITCH_TOKEN_HEADER = "X-Kill-Switch-Token"  # noqa: S105 - header name, not a secret


class ControlPlaneKillSwitch:
    """Poll the control plane's kill-switch endpoint for one execution.

    Satisfies :class:`KillSwitch`. Built per execution (the ``execution_id`` and
    ``kill_switch_token`` come from the frozen envelope, not from process-wide
    config). ``transport`` is an optional ``httpx.AsyncBaseTransport`` for tests
    (an ``httpx.MockTransport``); ``None`` selects httpx's real transport. Typed
    ``Any`` because httpx is imported lazily and must not be referenced at module
    import time.
    """

    def __init__(
        self,
        base_url: str,
        execution_id: str,
        kill_switch_token: str,
        *,
        timeout_seconds: float = DEFAULT_KILL_SWITCH_POLL_TIMEOUT_SECONDS,
        transport: Any = None,
    ) -> None:
        self._url = (
            f"{base_url.rstrip('/')}/api/v1/validation-executions/"
            f"{quote(execution_id, safe='')}/kill-switch"
        )
        self._execution_id = execution_id
        self._token = kill_switch_token
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    async def is_active(self) -> bool:
        """Return whether the scan must abort now (fail-safe: abort on any doubt)."""
        import httpx

        timeout = httpx.Timeout(self._timeout_seconds)
        try:
            async with httpx.AsyncClient(
                follow_redirects=False,
                timeout=timeout,
                verify=True,
                trust_env=False,
                transport=self._transport,
            ) as client:
                response = await client.get(
                    self._url, headers={_KILL_SWITCH_TOKEN_HEADER: self._token}
                )
        except Exception:
            # Never echo a raw transport exception (may carry the URL). Cannot
            # confirm the scan is still permitted → abort.
            _logger.warning(
                "kill-switch poll failed for execution %s; aborting (fail-safe)",
                self._execution_id,
            )
            return True

        if response.status_code != 200:
            _logger.warning(
                "kill-switch poll for execution %s returned status %s; aborting "
                "(fail-safe)",
                self._execution_id,
                response.status_code,
            )
            return True

        try:
            active = response.json().get("active")
        except (ValueError, AttributeError):
            _logger.warning(
                "kill-switch poll for execution %s returned an unreadable body; "
                "aborting (fail-safe)",
                self._execution_id,
            )
            return True

        if not isinstance(active, bool):
            _logger.warning(
                "kill-switch poll for execution %s omitted a boolean 'active'; "
                "aborting (fail-safe)",
                self._execution_id,
            )
            return True
        return active


# Builds a per-execution kill switch from the identifiers the worker reads out of
# the validated envelope: (execution_id, kill_switch_token) -> KillSwitch.
KillSwitchFactory = Callable[[str, str], KillSwitch]


def build_control_plane_kill_switch_factory(
    base_url: str,
    *,
    timeout_seconds: float = DEFAULT_KILL_SWITCH_POLL_TIMEOUT_SECONDS,
    transport: Any = None,
) -> KillSwitchFactory:
    """Build the per-execution kill-switch factory for a worker process.

    Closes over the control-plane ``base_url`` (and, in tests, an httpx
    transport) so the worker consumer can mint a :class:`ControlPlaneKillSwitch`
    scoped to each envelope's ``execution_id`` / ``kill_switch_token``.
    """

    def factory(execution_id: str, kill_switch_token: str) -> KillSwitch:
        return ControlPlaneKillSwitch(
            base_url,
            execution_id,
            kill_switch_token,
            timeout_seconds=timeout_seconds,
            transport=transport,
        )

    return factory
