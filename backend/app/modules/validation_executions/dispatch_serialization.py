"""JSON-safe serialization for the worker dispatch contract.

A future queue broker will carry a :class:`WorkerDispatchPayload` across a
process boundary as JSON. This pure module is the single place that contract is
encoded, decoded, and adapted to the worker-side :class:`WorkerInput`. It
performs no I/O and imports no broker, HTTP transport, worker process, database,
session, repository, service, or FastAPI machinery — only the two value objects
it bridges, so it can never become an execution path.

The three snapshots are produced by the control plane from JSON columns and the
JSON-safe specification builder, so their contents are already primitives
(strings, numbers, booleans, ``None``, lists, nested mappings) with any datetime
already rendered to ISO strings and any enum to its value. This module therefore
validates *structure* and passes snapshot contents through unchanged; it never
reinterprets, masks, or reformats them.
"""

from collections.abc import Mapping
from typing import Any

from app.modules.validation_executions.dispatch_contracts import WorkerDispatchPayload
from app.modules.validation_executions.worker_runner import WorkerInput

# The exact, ordered contract field set. Used both to build the serialized form
# and to reject any payload whose top-level keys differ.
_FIELDS: tuple[str, ...] = (
    "execution_id",
    "template_id",
    "execution_specification",
    "scope_snapshot",
    "safety_snapshot",
)
_FIELD_SET = frozenset(_FIELDS)
_SNAPSHOT_FIELDS: tuple[str, ...] = (
    "execution_specification",
    "scope_snapshot",
    "safety_snapshot",
)


class WorkerDispatchSerializationError(Exception):
    """A dispatch payload failed the serialization contract.

    Messages reference only the fixed contract field names, never the payload's
    values or caller-supplied keys, so a malformed or hostile payload cannot leak
    its contents through an error.
    """


def serialize_worker_dispatch_payload(payload: WorkerDispatchPayload) -> dict[str, Any]:
    """Render a :class:`WorkerDispatchPayload` as a plain JSON-safe dict.

    Returns a dict with exactly the contract fields. The snapshot mappings are
    shallow-copied into plain dicts; their contents are already JSON-safe, so no
    value is reformatted. The result contains no ORM object, enum object, bytes,
    ``SecretStr``, evidence, result field, or tenant/credential data.
    """
    return {
        "execution_id": payload.execution_id,
        "template_id": payload.template_id,
        "execution_specification": dict(payload.execution_specification),
        "scope_snapshot": dict(payload.scope_snapshot),
        "safety_snapshot": dict(payload.safety_snapshot),
    }


def deserialize_worker_dispatch_payload(
    data: Mapping[str, Any],
) -> WorkerDispatchPayload:
    """Validate an untrusted mapping and rebuild a :class:`WorkerDispatchPayload`.

    Rejects, with a content-free :class:`WorkerDispatchSerializationError`: a
    non-mapping top level, any missing or unexpected field, an ``execution_id``
    or ``template_id`` that is not a non-empty string, and any snapshot that is
    not a mapping. Snapshot contents are not otherwise interpreted.
    """
    if not isinstance(data, Mapping):
        raise WorkerDispatchSerializationError(
            "dispatch payload must be a mapping of the contract fields"
        )

    keys = set(data.keys())
    if keys != _FIELD_SET:
        # Only the fixed contract names are ever named — never the caller's keys.
        missing = sorted(_FIELD_SET - keys)
        if missing:
            raise WorkerDispatchSerializationError(
                "dispatch payload is missing required fields: " + ", ".join(missing)
            )
        raise WorkerDispatchSerializationError(
            "dispatch payload contains unexpected fields"
        )

    execution_id = data["execution_id"]
    if not isinstance(execution_id, str) or not execution_id:
        raise WorkerDispatchSerializationError(
            "execution_id must be a non-empty string"
        )
    template_id = data["template_id"]
    if not isinstance(template_id, str) or not template_id:
        raise WorkerDispatchSerializationError("template_id must be a non-empty string")

    snapshots: dict[str, dict[str, Any]] = {}
    for name in _SNAPSHOT_FIELDS:
        value = data[name]
        if not isinstance(value, Mapping):
            raise WorkerDispatchSerializationError(f"{name} must be a mapping")
        snapshots[name] = dict(value)

    return WorkerDispatchPayload(
        execution_id=execution_id,
        template_id=template_id,
        execution_specification=snapshots["execution_specification"],
        scope_snapshot=snapshots["scope_snapshot"],
        safety_snapshot=snapshots["safety_snapshot"],
    )


def to_worker_input(payload: WorkerDispatchPayload) -> WorkerInput:
    """Adapt a :class:`WorkerDispatchPayload` to a worker-side :class:`WorkerInput`.

    The two value objects share a field set; the conversion is kept explicit
    (field by field) rather than relying on structural coincidence, so a future
    divergence is a compile/type error here, not a silent mismatch at the worker.
    """
    return WorkerInput(
        execution_id=payload.execution_id,
        template_id=payload.template_id,
        execution_specification=payload.execution_specification,
        scope_snapshot=payload.scope_snapshot,
        safety_snapshot=payload.safety_snapshot,
    )
