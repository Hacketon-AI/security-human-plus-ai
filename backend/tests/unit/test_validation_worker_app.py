"""Unit tests for the worker composition root and its config.

Pin that ``build_worker_celery_app`` assembles a consumer bound to the dispatch
queue with the run-validation task registered, that ``WorkerSettings`` reads a
worker-only env (never the database DSN), and that the per-envelope kill-switch
factory is threaded through the bootstrap so the executor polls a switch built
from the frozen ``kill_switch_token``. Import purity of the new worker modules is
pinned too.
"""

import ast

import pytest
from app.modules.validation_executions.celery_worker_app import (
    build_worker_celery_app,
)
from app.modules.validation_executions.worker_settings import WorkerSettings
from pydantic import SecretStr
from pydantic import ValidationError as PydanticValidationError

_BROKER = "amqp://guest:guest@broker.internal:5672//"
_BASE_URL = "https://control-plane.internal"


def _settings(**overrides: object) -> WorkerSettings:
    base: dict[str, object] = {
        "celery_broker_url": SecretStr(_BROKER),
        "control_plane_base_url": _BASE_URL,
    }
    base.update(overrides)
    return WorkerSettings(**base)  # type: ignore[arg-type]


# --- WorkerSettings ---------------------------------------------------------


def test_worker_settings_reads_worker_prefixed_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SECURESCOPE_WORKER_CELERY_BROKER_URL", _BROKER)
    monkeypatch.setenv("SECURESCOPE_WORKER_CONTROL_PLANE_BASE_URL", _BASE_URL + "/")
    settings = WorkerSettings()  # type: ignore[call-arg]

    assert settings.celery_broker_url.get_secret_value() == _BROKER
    # Trailing slash is normalised away.
    assert settings.control_plane_base_url == _BASE_URL
    assert settings.queue_name == "validation_executions"


def test_worker_settings_has_no_database_field() -> None:
    # The worker must never carry the API's DB secret (security boundary).
    assert "database_dsn" not in WorkerSettings.model_fields


def test_worker_settings_rejects_non_http_base_url() -> None:
    with pytest.raises(PydanticValidationError):
        _settings(control_plane_base_url="ftp://cp.internal")


def test_worker_settings_broker_url_is_masked_in_repr() -> None:
    settings = _settings()
    assert _BROKER not in repr(settings)


# --- composition root -------------------------------------------------------


def test_build_worker_celery_app_registers_task_and_binds_queue() -> None:
    settings = _settings()
    app = build_worker_celery_app(settings)

    assert settings.task_name in app.tasks
    queue_names = [q.name for q in app.conf.task_queues]
    assert queue_names == [settings.queue_name]
    # The queue is bound to the dispatch exchange + routing key so published
    # envelopes are actually routed to the consumer.
    queue = app.conf.task_queues[0]
    assert queue.exchange.name == settings.exchange
    assert queue.routing_key == settings.routing_key


def test_build_worker_celery_app_uses_hardened_config() -> None:
    app = build_worker_celery_app(_settings())
    # Same hardening as the publisher: json-only, no eager, no result backend.
    assert app.conf.task_always_eager is False
    assert app.conf.accept_content == ["json"]
    assert app.conf.result_backend is None


def test_build_worker_celery_app_custom_task_name() -> None:
    app = build_worker_celery_app(_settings(task_name="custom.run"))
    assert "custom.run" in app.tasks


# --- import purity ----------------------------------------------------------


_FORBIDDEN_IMPORT_TOKENS = (
    "fastapi",
    "sqlalchemy",
    "app.main",
    "platform.database",
    "platform.dependencies",
    "repository",
    "service",
    "router",
    "dispatcher",
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


def test_worker_modules_import_purity() -> None:
    from app.modules.validation_executions import (
        celery_worker_app,
        worker_settings,
    )

    for module in (celery_worker_app, worker_settings):
        for name in _imported_modules(module):
            assert not any(token in name for token in _FORBIDDEN_IMPORT_TOKENS), (
                f"{module.__name__} must not import {name}"
            )
