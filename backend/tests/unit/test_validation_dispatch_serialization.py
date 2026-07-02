"""Unit tests for the worker dispatch serialization contract.

These pin the JSON-safe round trip, the exact field set, strict rejection of
malformed input, content-free errors, the WorkerInput adaptation, and that a
``WorkerInput`` rebuilt from a serialized+deserialized payload actually runs
through the worker runner (with a fake transport — no network). They also pin
import purity: the serialization module pulls in no DB/service/router/worker
process/HTTP transport.
"""

import ast
import json
from datetime import UTC, datetime
from typing import Any

import pytest
from app.modules.validation_executions import (
    dispatch_serialization as serialization_module,
)
from app.modules.validation_executions.dispatch_contracts import WorkerDispatchPayload
from app.modules.validation_executions.dispatch_serialization import (
    WorkerDispatchSerializationError,
    deserialize_worker_dispatch_payload,
    serialize_worker_dispatch_payload,
    to_worker_input,
)
from app.modules.validation_executions.executor_transport import HttpResponse
from app.modules.validation_executions.schemas import WorkerFinishedRequest
from app.modules.validation_executions.templates import HTTP_SECURITY_HEADER_VALIDATION
from app.modules.validation_executions.worker_runner import (
    WorkerInput,
    run_http_security_header_validation,
)

_TARGET = "https://app.example.com/login"

_STRONG_HEADERS = {
    "Strict-Transport-Security": "max-age=63072000",
    "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=()",
}


def _payload(**overrides: Any) -> WorkerDispatchPayload:
    """A runnable dispatch payload with JSON-safe snapshots.

    The window timestamps are ISO strings (as the spec builder produces them) so
    the JSON-safety assertions exercise a real datetime-shaped value.
    """
    base: dict[str, Any] = {
        "execution_id": "11111111-1111-1111-1111-111111111111",
        "template_id": HTTP_SECURITY_HEADER_VALIDATION,
        "execution_specification": {
            "template_id": HTTP_SECURITY_HEADER_VALIDATION,
            "target": _TARGET,
            "kill_switch_token": "opaque-poll-key",
            "testing_window": {
                "start": datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
                "end": datetime(2026, 1, 2, tzinfo=UTC).isoformat(),
            },
        },
        "scope_snapshot": {
            "allowed_paths": None,
            "excluded_paths": None,
            "allowed_ports": [443],
        },
        "safety_snapshot": {
            "timeout_seconds": 5.0,
            "redirect_limit": 3,
            "max_requests": 5,
            "max_response_bytes": 65536,
            "kill_switch_active": False,
        },
    }
    base.update(overrides)
    return WorkerDispatchPayload(**base)


# --- Fake transport so a rebuilt WorkerInput can run without network ---------


class _FakeTransport:
    def __init__(self, response: HttpResponse) -> None:
        self._response = response

    async def request(
        self,
        method: str,
        url: str,
        *,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> HttpResponse:
        return self._response


def _fake_factory(scope: object, safety: object) -> _FakeTransport:
    return _FakeTransport(HttpResponse(200, _STRONG_HEADERS, _TARGET, 8.0))


# --- Round trip + field set -------------------------------------------------


def test_round_trip_returns_equal_payload() -> None:
    payload = _payload()
    restored = deserialize_worker_dispatch_payload(
        serialize_worker_dispatch_payload(payload)
    )
    assert restored == payload


def test_serialized_field_set_is_exact() -> None:
    data = serialize_worker_dispatch_payload(_payload())
    assert set(data.keys()) == {
        "execution_id",
        "template_id",
        "execution_specification",
        "scope_snapshot",
        "safety_snapshot",
    }


def test_json_dump_load_round_trip() -> None:
    payload = _payload()
    data = serialize_worker_dispatch_payload(payload)
    reloaded = json.loads(json.dumps(data))
    assert deserialize_worker_dispatch_payload(reloaded) == payload


def _assert_json_primitive(value: object) -> None:
    """Recursively assert a value is a JSON primitive — no datetime/bytes/etc."""
    if isinstance(value, dict):
        for key, item in value.items():
            assert isinstance(key, str)
            _assert_json_primitive(item)
    elif isinstance(value, list):
        for item in value:
            _assert_json_primitive(item)
    else:
        # bool is a subclass of int; both are allowed. datetime/bytes/SecretStr
        # and any other object are not.
        assert isinstance(value, str | int | float | type(None)), (
            f"non-JSON value of type {type(value).__name__} in serialized payload"
        )


def test_serialized_output_has_no_non_json_objects() -> None:
    data = serialize_worker_dispatch_payload(_payload())
    _assert_json_primitive(data)


# --- Rejection --------------------------------------------------------------


def test_rejects_extra_fields() -> None:
    data = serialize_worker_dispatch_payload(_payload())
    data["unexpected"] = "x"
    with pytest.raises(WorkerDispatchSerializationError):
        deserialize_worker_dispatch_payload(data)


def test_rejects_missing_fields() -> None:
    data = serialize_worker_dispatch_payload(_payload())
    del data["scope_snapshot"]
    with pytest.raises(WorkerDispatchSerializationError):
        deserialize_worker_dispatch_payload(data)


def test_rejects_wrong_top_level_type() -> None:
    with pytest.raises(WorkerDispatchSerializationError):
        deserialize_worker_dispatch_payload(["not", "a", "mapping"])  # type: ignore[arg-type]


def test_rejects_non_mapping_snapshot() -> None:
    data = serialize_worker_dispatch_payload(_payload())
    data["safety_snapshot"] = "not-a-mapping"
    with pytest.raises(WorkerDispatchSerializationError):
        deserialize_worker_dispatch_payload(data)


def test_rejects_empty_execution_id() -> None:
    data = serialize_worker_dispatch_payload(_payload())
    data["execution_id"] = ""
    with pytest.raises(WorkerDispatchSerializationError):
        deserialize_worker_dispatch_payload(data)


def test_rejects_empty_template_id() -> None:
    data = serialize_worker_dispatch_payload(_payload())
    data["template_id"] = ""
    with pytest.raises(WorkerDispatchSerializationError):
        deserialize_worker_dispatch_payload(data)


def test_error_message_does_not_echo_payload_content() -> None:
    data = serialize_worker_dispatch_payload(_payload())
    data["execution_id"] = "SENSITIVE-VALUE-1234"
    data["leaky_secret_key"] = "SENSITIVE-VALUE-5678"
    with pytest.raises(WorkerDispatchSerializationError) as exc_info:
        deserialize_worker_dispatch_payload(data)
    message = str(exc_info.value)
    assert "SENSITIVE-VALUE-1234" not in message
    assert "SENSITIVE-VALUE-5678" not in message
    assert "leaky_secret_key" not in message


# --- Worker compatibility ---------------------------------------------------


def test_to_worker_input_preserves_values() -> None:
    payload = _payload()
    worker_input = to_worker_input(payload)
    assert isinstance(worker_input, WorkerInput)
    assert worker_input.execution_id == payload.execution_id
    assert worker_input.template_id == payload.template_id
    assert worker_input.execution_specification == payload.execution_specification
    assert worker_input.scope_snapshot == payload.scope_snapshot
    assert worker_input.safety_snapshot == payload.safety_snapshot


async def test_worker_runner_runs_with_deserialized_payload() -> None:
    # Full path a future consumer takes: serialize → JSON → deserialize → adapt →
    # run through the runner with a fake transport (no network).
    data = json.loads(json.dumps(serialize_worker_dispatch_payload(_payload())))
    worker_input = to_worker_input(deserialize_worker_dispatch_payload(data))

    result = await run_http_security_header_validation(
        worker_input, transport_factory=_fake_factory
    )

    assert isinstance(result, WorkerFinishedRequest)
    assert result.outcome is not None


# --- Import purity ----------------------------------------------------------

_FORBIDDEN_IMPORT_TOKENS = (
    "worker_process",
    "http_transport",
    "SafeHttpTransport",
    "HttpxTransportClient",
    "database",
    "session",
    "repository",
    "service",
    "router",
    "fastapi",
    "sqlalchemy",
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


def test_serialization_module_import_purity() -> None:
    for module_name in _imported_modules(serialization_module):
        assert not any(token in module_name for token in _FORBIDDEN_IMPORT_TOKENS), (
            f"dispatch_serialization must not import: {module_name}"
        )
