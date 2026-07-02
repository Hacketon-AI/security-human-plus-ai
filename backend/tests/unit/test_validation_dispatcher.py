"""Unit tests for the dispatch seam contract and its import purity.

The dispatcher hands a frozen :class:`WorkerDispatchPayload` to a worker
pipeline. These tests pin the fail-closed default, the frozen payload shape, and
— critically — that the control-plane dispatch path imports no worker runtime,
so the seam can never become an inline execution path inside the API
(``.claude/rules/security-boundaries.md`` → scanner execution isolation).
"""

import ast
from dataclasses import FrozenInstanceError, fields

import pytest
from app.modules.validation_executions import dispatch_contracts as contracts_module
from app.modules.validation_executions import dispatcher as dispatcher_module
from app.modules.validation_executions import router as router_module
from app.modules.validation_executions import service as service_module
from app.modules.validation_executions.dispatch_contracts import WorkerDispatchPayload
from app.modules.validation_executions.dispatcher import (
    UnconfiguredValidationDispatcher,
)
from app.modules.validation_executions.errors import ValidationDispatchNotConfigured

# dispatch_contracts is the FastAPI-free home of the dispatch value object; it
# must stay importable by an isolated worker without pulling in any app runtime.
_CONTRACTS_ALLOWED_IMPORTS = {"collections.abc", "dataclasses", "typing"}

# Worker-runtime and transport names that must never be imported by the
# control-plane dispatch path. Their presence would mean scanner execution could
# run in the API process.
_FORBIDDEN_IMPORT_TOKENS = (
    "worker_runner",
    "worker_process",
    "worker_client",
    "http_transport",
    "SafeHttpTransport",
    "HttpxTransportClient",
    # The serialization module imports the worker runtime; the API path must not
    # pull it in transitively.
    "dispatch_serialization",
)


def _imported_modules(module: object) -> list[str]:
    source = module.__file__  # type: ignore[attr-defined]
    assert source is not None
    with open(source, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.append(node.module)
    return names


def _payload() -> WorkerDispatchPayload:
    return WorkerDispatchPayload(
        execution_id="exec-1",
        template_id="HTTP_SECURITY_HEADER_VALIDATION",
        execution_specification={
            "target": "https://example.test",
            "kill_switch_token": "k",
        },
        scope_snapshot={"allowed_ports": [443]},
        safety_snapshot={"kill_switch_active": False},
    )


async def test_unconfigured_dispatcher_fails_closed() -> None:
    with pytest.raises(ValidationDispatchNotConfigured):
        await UnconfiguredValidationDispatcher().dispatch(_payload())


def test_payload_is_frozen() -> None:
    payload = _payload()
    with pytest.raises(FrozenInstanceError):
        payload.execution_id = "tampered"  # type: ignore[misc]


def test_payload_fields_are_exactly_the_worker_input_set() -> None:
    assert {f.name for f in fields(WorkerDispatchPayload)} == {
        "execution_id",
        "template_id",
        "execution_specification",
        "scope_snapshot",
        "safety_snapshot",
    }


def test_dispatch_contracts_module_is_pure() -> None:
    # The contract module is shared by both the API seam and a future worker
    # package, so it must import only the standard library — no FastAPI, config,
    # DB/session/repository/service/router, worker process, or HTTP transport.
    for module_name in _imported_modules(contracts_module):
        assert module_name in _CONTRACTS_ALLOWED_IMPORTS, (
            f"dispatch_contracts.py must import only the standard library; "
            f"found: {module_name}"
        )


def test_dispatcher_module_imports_no_worker_runtime() -> None:
    names = _imported_modules(dispatcher_module)
    for module_name in names:
        assert not any(token in module_name for token in _FORBIDDEN_IMPORT_TOKENS), (
            f"dispatcher.py must not import worker runtime: {module_name}"
        )


def test_service_and_router_import_no_worker_runtime() -> None:
    # The API path may reference the dispatcher contract, but never the worker
    # runtime or its transports.
    for module in (service_module, router_module):
        names = _imported_modules(module)
        for module_name in names:
            assert not any(
                token in module_name for token in _FORBIDDEN_IMPORT_TOKENS
            ), f"{module.__name__} must not import worker runtime: {module_name}"
