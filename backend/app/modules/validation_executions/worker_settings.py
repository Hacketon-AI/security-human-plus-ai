"""Configuration for the isolated validation-worker process.

The worker runs in an ephemeral, isolated container that must **not** share the
API's secrets or network (``security-boundaries.md`` → scanner execution
isolation). In particular it must never hold the database DSN. The API's
:class:`app.config.Settings` *requires* ``database_dsn``, so the worker gets its
own minimal settings object instead of reusing it — this class declares only what
a worker legitimately needs and reads a distinct ``SECURESCOPE_WORKER_`` env
namespace, so the two config surfaces never overlap.

Secret-bearing values use :class:`SecretStr` so they never surface in logs,
tracebacks, or ``repr``. Import purity: Pydantic settings only — no FastAPI,
SQLAlchemy, repositories, services, routers, dispatcher, or ``app.main``.
"""

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["WorkerSettings"]


class WorkerSettings(BaseSettings):
    """Minimal settings for the validation-worker consumer process.

    Distinct ``SECURESCOPE_WORKER_`` prefix so a worker container is provisioned
    with its own env, never the API's. Notably absent: ``database_dsn`` — the
    worker never touches the database.
    """

    model_config = SettingsConfigDict(
        env_prefix="SECURESCOPE_WORKER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    # Broker the consumer connects to. Same RabbitMQ the API publishes to, but
    # supplied via the worker's own env so the worker image carries no API config.
    celery_broker_url: SecretStr

    # Control-plane root the worker POSTs hooks to and polls the kill switch on.
    # Not a secret (an internal URL), but validated to be http(s).
    control_plane_base_url: str

    # Bounds for the two outbound call classes the worker makes to the control
    # plane: hook delivery (worker-started / worker-finished) and kill-switch
    # polls. Kept tight — both are small, local, first-party requests.
    delivery_timeout_seconds: float = 10.0
    kill_switch_poll_timeout_seconds: float = 5.0

    # Broker addressing. Defaults mirror the publisher's dispatch settings
    # (``app.config.Settings``) so producer and consumer agree without a shared
    # object; override per environment only if the publisher's are overridden.
    queue_name: str = "validation_executions"
    exchange: str = "validation"
    routing_key: str = "validation.execute"
    task_name: str = "validation_executions.run_validation"

    # Transitional shared worker token. Off unless explicitly provided; the
    # control plane still rejects it unless its own fallback flag is enabled, so
    # setting it here cannot unilaterally widen authority.
    shared_token_fallback_token: SecretStr | None = Field(default=None)

    @field_validator("control_plane_base_url")
    @classmethod
    def _require_http_url(cls, value: str) -> str:
        candidate = value.strip()
        if not candidate.startswith(("http://", "https://")):
            raise ValueError("control_plane_base_url must be an http(s) URL")
        return candidate.rstrip("/")
