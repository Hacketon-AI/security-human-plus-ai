"""Unit tests for the production broker contract.

Pin the wire envelope shape, the JSON-safety guarantee, the canonical
SHA-256, and — critically — the import purity and Protocol surface so the
contract module cannot drift toward executing scanner logic or leaking
sensitive state. No real broker is implemented yet; production dispatch
stays fail-closed until a concrete publisher is wired (see
``docs/validation-dispatch-broker-design.md``).
"""

import ast
import json
from datetime import UTC, datetime
from typing import Any, get_type_hints

import pytest
from app.modules.validation_executions import (
    broker_contracts as broker_contracts_module,
)
from app.modules.validation_executions import (
    dispatcher as dispatcher_module,
)
from app.modules.validation_executions import (
    router as router_module,
)
from app.modules.validation_executions import (
    service as service_module,
)
from app.modules.validation_executions.broker_contracts import (
    DISPATCH_CONTENT_TYPE,
    DISPATCH_ENVELOPE_SCHEMA_VERSION,
    BrokerConsumerOutcome,
    BrokerConsumerResult,
    BrokerEnvelopeError,
    DispatchPublishOutcome,
    DispatchPublishResult,
    ValidationDispatchConsumer,
    ValidationDispatchEnvelope,
    ValidationDispatchPublisher,
    build_dispatch_envelope,
    canonical_payload_sha256,
)
from app.modules.validation_executions.dispatch_contracts import WorkerDispatchPayload
from app.modules.validation_executions.templates import HTTP_SECURITY_HEADER_VALIDATION

_BASE_PAYLOAD_SPEC: dict[str, Any] = {
    "template_id": HTTP_SECURITY_HEADER_VALIDATION,
    "target": "https://app.example.com/login",
    "kill_switch_token": "opaque-poll-key",
}
_BASE_SCOPE: dict[str, Any] = {
    "allowed_ports": [443],
    "allowed_paths": None,
    "excluded_paths": None,
}
_BASE_SAFETY: dict[str, Any] = {
    "timeout_seconds": 5.0,
    "redirect_limit": 3,
    "max_requests": 5,
    "max_response_bytes": 65536,
    "kill_switch_active": False,
}
_CREATED_AT = datetime(2026, 6, 25, 12, tzinfo=UTC).isoformat()


def _payload(
    execution_id: str = "11111111-1111-1111-1111-111111111111",
) -> WorkerDispatchPayload:
    return WorkerDispatchPayload(
        execution_id=execution_id,
        template_id=HTTP_SECURITY_HEADER_VALIDATION,
        execution_specification=dict(_BASE_PAYLOAD_SPEC),
        scope_snapshot=dict(_BASE_SCOPE),
        safety_snapshot=dict(_BASE_SAFETY),
    )


def _envelope(**overrides: Any) -> ValidationDispatchEnvelope:
    return build_dispatch_envelope(
        _payload(),
        message_id=overrides.pop("message_id", "msg-1"),
        created_at=overrides.pop("created_at", _CREATED_AT),
        attempt=overrides.pop("attempt", 1),
        trace_id=overrides.pop("trace_id", None),
        idempotency_key=overrides.pop("idempotency_key", None),
    )


# --- Envelope shape: contract fields, JSON-safe values ---------------------


def test_envelope_payload_has_exact_contract_field_set() -> None:
    envelope = _envelope()
    assert set(envelope.payload.keys()) == {
        "execution_id",
        "template_id",
        "execution_specification",
        "scope_snapshot",
        "safety_snapshot",
    }
    assert envelope.schema_version == DISPATCH_ENVELOPE_SCHEMA_VERSION
    assert envelope.content_type == DISPATCH_CONTENT_TYPE
    assert envelope.attempt == 1


def test_envelope_payload_is_json_safe() -> None:
    envelope = _envelope()
    # No custom encoder — round-trips through stdlib json with no errors.
    encoded = json.dumps(envelope.payload)
    assert json.loads(encoded) == dict(envelope.payload)


def test_envelope_payload_contains_no_evidence_tenant_or_credentials() -> None:
    envelope = _envelope()
    forbidden_keys = {
        "organization_id",
        "tenant_id",
        "x-organization-id",
        "X-Organization-Id",
        "x-worker-authorization",
        "X-Worker-Authorization",
        "auth_token",
        "user_id",
        "requested_by",
        "credential",
        "credentials",
        "evidence",
        "step_results",
    }
    _assert_keys_absent(dict(envelope.payload), forbidden_keys)


def _assert_keys_absent(value: object, forbidden: set[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            assert key not in forbidden, f"forbidden key {key!r} in envelope payload"
            _assert_keys_absent(item, forbidden)
    elif isinstance(value, list):
        for item in value:
            _assert_keys_absent(item, forbidden)


# --- SHA-256: stable for same payload, changes on mutation ----------------


def test_payload_sha256_is_stable_for_same_payload() -> None:
    first = _envelope(message_id="a")
    second = _envelope(message_id="b")
    # Same payload → same hash, even when the envelope metadata differs.
    assert first.payload_sha256 == second.payload_sha256


def test_payload_sha256_changes_when_payload_changes() -> None:
    base = _envelope()
    other = build_dispatch_envelope(
        _payload(execution_id="22222222-2222-2222-2222-222222222222"),
        message_id="msg-2",
        created_at=_CREATED_AT,
    )
    assert base.payload_sha256 != other.payload_sha256


def test_canonical_sha256_is_key_order_independent() -> None:
    payload_a: dict[str, Any] = {"a": 1, "b": [1, 2, 3], "c": {"x": 1, "y": 2}}
    payload_b: dict[str, Any] = {"c": {"y": 2, "x": 1}, "b": [1, 2, 3], "a": 1}
    assert canonical_payload_sha256(payload_a) == canonical_payload_sha256(payload_b)


# --- Envelope rejects non-JSON-safe values --------------------------------


def test_envelope_rejects_datetime_in_payload() -> None:
    payload = _payload()
    serialized = dict(_envelope().payload)
    serialized["execution_specification"] = dict(serialized["execution_specification"])
    serialized["execution_specification"]["start"] = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(BrokerEnvelopeError) as exc_info:
        ValidationDispatchEnvelope(
            message_id="m",
            schema_version=DISPATCH_ENVELOPE_SCHEMA_VERSION,
            payload=serialized,
            payload_sha256="ignored",
            created_at=_CREATED_AT,
            attempt=1,
        )
    # The error names the rule but not the offending value.
    assert "non-JSON-safe" in str(exc_info.value)
    assert payload.execution_id not in str(exc_info.value)


def test_envelope_rejects_bytes_in_payload() -> None:
    serialized = dict(_envelope().payload)
    serialized["execution_specification"] = dict(serialized["execution_specification"])
    serialized["execution_specification"]["target"] = b"https://leak.example"
    with pytest.raises(BrokerEnvelopeError) as exc_info:
        ValidationDispatchEnvelope(
            message_id="m",
            schema_version=DISPATCH_ENVELOPE_SCHEMA_VERSION,
            payload=serialized,
            payload_sha256="ignored",
            created_at=_CREATED_AT,
            attempt=1,
        )
    assert "non-JSON-safe" in str(exc_info.value)
    # The bytes literal value must not appear in the error message.
    assert "leak.example" not in str(exc_info.value)


def test_envelope_rejects_non_string_dict_keys() -> None:
    serialized = dict(_envelope().payload)
    serialized["execution_specification"] = {1: "bad"}
    with pytest.raises(BrokerEnvelopeError):
        ValidationDispatchEnvelope(
            message_id="m",
            schema_version=DISPATCH_ENVELOPE_SCHEMA_VERSION,
            payload=serialized,
            payload_sha256="ignored",
            created_at=_CREATED_AT,
            attempt=1,
        )


def test_envelope_rejects_extra_payload_field() -> None:
    serialized = dict(_envelope().payload)
    serialized["unexpected"] = "x"
    with pytest.raises(BrokerEnvelopeError):
        ValidationDispatchEnvelope(
            message_id="m",
            schema_version=DISPATCH_ENVELOPE_SCHEMA_VERSION,
            payload=serialized,
            payload_sha256=canonical_payload_sha256(serialized),
            created_at=_CREATED_AT,
            attempt=1,
        )


def test_envelope_rejects_missing_payload_field() -> None:
    serialized = dict(_envelope().payload)
    del serialized["safety_snapshot"]
    with pytest.raises(BrokerEnvelopeError):
        ValidationDispatchEnvelope(
            message_id="m",
            schema_version=DISPATCH_ENVELOPE_SCHEMA_VERSION,
            payload=serialized,
            payload_sha256=canonical_payload_sha256(serialized),
            created_at=_CREATED_AT,
            attempt=1,
        )


def test_envelope_rejects_bad_content_type() -> None:
    serialized = dict(_envelope().payload)
    with pytest.raises(BrokerEnvelopeError):
        ValidationDispatchEnvelope(
            message_id="m",
            schema_version=DISPATCH_ENVELOPE_SCHEMA_VERSION,
            payload=serialized,
            payload_sha256=canonical_payload_sha256(serialized),
            created_at=_CREATED_AT,
            attempt=1,
            content_type="application/octet-stream",
        )


def test_envelope_rejects_non_positive_attempt() -> None:
    serialized = dict(_envelope().payload)
    with pytest.raises(BrokerEnvelopeError):
        ValidationDispatchEnvelope(
            message_id="m",
            schema_version=DISPATCH_ENVELOPE_SCHEMA_VERSION,
            payload=serialized,
            payload_sha256=canonical_payload_sha256(serialized),
            created_at=_CREATED_AT,
            attempt=0,
        )


def test_envelope_rejects_empty_message_id_or_created_at_or_schema() -> None:
    serialized = dict(_envelope().payload)
    sha = canonical_payload_sha256(serialized)
    for kwargs in (
        {"message_id": ""},
        {"created_at": ""},
        {"schema_version": ""},
    ):
        with pytest.raises(BrokerEnvelopeError):
            ValidationDispatchEnvelope(
                message_id=kwargs.get("message_id", "m"),
                schema_version=kwargs.get(
                    "schema_version", DISPATCH_ENVELOPE_SCHEMA_VERSION
                ),
                payload=serialized,
                payload_sha256=sha,
                created_at=kwargs.get("created_at", _CREATED_AT),
                attempt=1,
            )


def test_envelope_rejects_tampered_payload_sha() -> None:
    serialized = dict(_envelope().payload)
    with pytest.raises(BrokerEnvelopeError):
        ValidationDispatchEnvelope(
            message_id="m",
            schema_version=DISPATCH_ENVELOPE_SCHEMA_VERSION,
            payload=serialized,
            payload_sha256="0" * 64,  # plausible-looking but wrong
            created_at=_CREATED_AT,
            attempt=1,
        )


# --- Publisher Protocol surface -------------------------------------------


def test_publisher_protocol_exposes_only_publish() -> None:
    """The publisher Protocol must declare exactly one public method.

    Adding a method like ``run_scan`` or ``execute`` would break the
    boundary: the publisher commits to the broker and stops there. Any
    new method must be reviewed against the security boundaries.
    """
    public_attrs = {
        name for name in vars(ValidationDispatchPublisher) if not name.startswith("_")
    }
    assert public_attrs == {"publish"}


def test_consumer_protocol_exposes_only_consume_once() -> None:
    public_attrs = {
        name for name in vars(ValidationDispatchConsumer) if not name.startswith("_")
    }
    assert public_attrs == {"consume_once"}


def test_publisher_returns_dispatch_publish_result() -> None:
    hints = get_type_hints(ValidationDispatchPublisher.publish)
    assert hints["return"] is DispatchPublishResult


def test_consumer_returns_broker_consumer_result() -> None:
    hints = get_type_hints(ValidationDispatchConsumer.consume_once)
    assert hints["return"] is BrokerConsumerResult


def test_publish_result_outcome_enum_is_exhaustive() -> None:
    assert {member.value for member in DispatchPublishOutcome} == {
        "published",
        "rejected",
        "publish_failed",
    }


def test_broker_consumer_outcome_enum_is_exhaustive() -> None:
    assert {member.value for member in BrokerConsumerOutcome} == {
        "no_message",
        "malformed",
        "started_delivery_failed",
        "finished_delivery_failed",
        "delivered",
    }


# --- Import purity --------------------------------------------------------


_FORBIDDEN_IMPORT_TOKENS = (
    "fastapi",
    "sqlalchemy",
    "repository",
    "service",
    "router",
    "worker_runner",
    "worker_process",
    "worker_client",
    "http_transport",
    "app.main",
    "app.platform.database",
    "app.platform.dependencies",
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


def test_broker_contracts_module_imports_no_runtime() -> None:
    for module_name in _imported_modules(broker_contracts_module):
        assert not any(token in module_name for token in _FORBIDDEN_IMPORT_TOKENS), (
            f"broker_contracts must not import: {module_name}"
        )


def test_api_path_does_not_import_broker_contracts_yet() -> None:
    """Until a concrete publisher exists, broker_contracts stays isolated.

    Once a Celery publisher lands, ``dispatcher`` may import the publisher
    Protocol — but at the current rollout step (contract only) no module on
    the API path imports it.
    """
    for module in (dispatcher_module, service_module, router_module):
        names = _imported_modules(module)
        for module_name in names:
            assert "broker_contracts" not in module_name, (
                f"{module.__name__} must not import broker_contracts at this "
                f"rollout step; found: {module_name}"
            )


def test_main_does_not_import_broker_contracts() -> None:
    from app import main as main_module

    for module_name in _imported_modules(main_module):
        assert "broker_contracts" not in module_name, (
            f"app.main must not import broker_contracts; found: {module_name}"
        )


def test_consumer_protocol_is_not_wired_in_app_main_source() -> None:
    """The consumer Protocol is not wired: app.main must not name it.

    The lifespan does wire the *publisher* (a concrete
    ``CeleryValidationDispatchPublisher`` from the celery_publisher module,
    not the Protocol from broker_contracts) so this check pins only the
    consumer-side guarantee. The publisher Protocol is also not imported
    here: the publisher is bound by concrete class, never via the Protocol.
    """
    from app import main as main_module

    source = main_module.__file__
    assert source is not None
    with open(source, encoding="utf-8") as handle:
        text = handle.read()
    assert "broker_contracts" not in text
    assert "ValidationDispatchConsumer" not in text


# --- build_dispatch_envelope: optional fields default to None -------------


def test_build_envelope_optional_fields_default_none() -> None:
    envelope = _envelope()
    assert envelope.trace_id is None
    assert envelope.idempotency_key is None


def test_build_envelope_round_trips_through_json() -> None:
    envelope = _envelope(trace_id="trace-xyz", idempotency_key="idem-1")
    rebuilt = json.loads(
        json.dumps(
            {
                "message_id": envelope.message_id,
                "schema_version": envelope.schema_version,
                "payload": dict(envelope.payload),
                "payload_sha256": envelope.payload_sha256,
                "created_at": envelope.created_at,
                "attempt": envelope.attempt,
                "content_type": envelope.content_type,
                "trace_id": envelope.trace_id,
                "idempotency_key": envelope.idempotency_key,
            }
        )
    )
    # Hash is recomputed from the round-tripped payload to confirm stability
    # across an actual JSON encode/decode cycle.
    assert rebuilt["payload_sha256"] == canonical_payload_sha256(rebuilt["payload"])
    assert rebuilt["schema_version"] == DISPATCH_ENVELOPE_SCHEMA_VERSION
    assert rebuilt["content_type"] == DISPATCH_CONTENT_TYPE
