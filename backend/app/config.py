"""Application configuration for the SecureScope control plane.

Settings are loaded once from the environment. Secret-bearing values use
``SecretStr`` so they never surface in logs, tracebacks, or the ``Settings``
repr — see ``.claude/rules/data-handling.md``.
"""

from enum import StrEnum
from functools import lru_cache

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    """Deployment environment. Drives docs exposure and approval policy."""

    development = "development"
    test = "test"
    staging = "staging"
    production = "production"


class ValidationDispatcherBackend(StrEnum):
    """Selected backend for the validation-execution dispatch seam.

    ``unconfigured`` keeps the fail-closed default: no execution can leave
    the API process. ``in_memory`` selects the development-only in-process
    queue adapter (see :mod:`app.modules.validation_executions.in_memory_queue`)
    and is rejected outside ``development``/``test`` at startup. ``celery``
    selects the Celery/RabbitMQ publisher (see
    :mod:`app.modules.validation_executions.celery_publisher`) and is rejected
    at startup unless a broker URL is configured.
    """

    unconfigured = "unconfigured"
    in_memory = "in_memory"
    celery = "celery"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SECURESCOPE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
        frozen=True,
    )

    app_name: str = "SecureScope"
    environment: Environment = Environment.development

    # Carries database credentials; SecretStr keeps it out of logs and repr.
    # The async engine is constructed from this in the platform layer.
    database_dsn: SecretStr

    # Development-only adapters (header-based tenant auth and organization
    # provisioning). ``None`` means "derive from environment": enabled in
    # development/test, disabled otherwise. Explicitly enabling either outside
    # development/test fails fast at startup rather than silently weakening
    # production. Resolve usage through the ``*_active`` properties.
    development_auth_enabled: bool | None = None
    development_provisioning_enabled: bool | None = None

    # Validation-execution dispatch backend. Defaults to the fail-closed
    # ``unconfigured`` backend so no real broker is implied; the development-only
    # ``in_memory`` adapter must be selected explicitly and is rejected outside
    # development/test by the validator below. Production dispatch remains
    # fail-closed until a real broker is wired
    # (see ``.claude/rules/security-boundaries.md``).
    validation_dispatcher_backend: ValidationDispatcherBackend = (
        ValidationDispatcherBackend.unconfigured
    )

    # Celery/RabbitMQ broker URL. ``SecretStr`` keeps the credentials embedded in
    # the URL out of logs, repr, and tracebacks. ``None`` is the default; the
    # validator below refuses to start with ``validation_dispatcher_backend=celery``
    # while this is unset. No default URL is invented — fail closed.
    celery_broker_url: SecretStr | None = None

    # Static broker addressing for the validation dispatch task. Plain strings
    # (never SecretStr) so the publisher cannot accidentally log a credential;
    # the broker URL is the only secret in this group.
    validation_dispatch_exchange: str = "validation"
    validation_dispatch_routing_key: str = "validation.execute"
    validation_dispatch_queue_name: str = "validation_executions"
    validation_dispatch_task_name: str = "validation_executions.run_validation"
    # Producer's promise to consumers. Bumped when the envelope shape changes.
    validation_dispatch_schema_version: str = "1"

    # Machine-to-machine credential for the worker transition hooks
    # (worker-started / worker-finished). Those endpoints are authenticated as an
    # isolated worker, not a tenant user, so they require this shared token rather
    # than the tenant ``X-Organization-Id`` header. ``SecretStr`` keeps it out of
    # logs, repr, and tracebacks. When unset the worker hooks fail closed in every
    # environment — no default token is ever assumed
    # (see ``.claude/rules/security-boundaries.md``).
    worker_auth_token: SecretStr | None = None

    # CORS origins string — comma-separated (e.g. "http://localhost:3000").
    # Defaults to "*" in development/test for convenience; explicitly set to a
    # specific origin in deployed environments.
    cors_origins: str = "*"

    # Transitional fallback gate for the shared ``worker_auth_token``.
    # Default off in every environment: a worker must present a
    # per-execution credential (see ``worker_credential_contracts``) to
    # authenticate. Set to True only as an explicit transitional step
    # while migrating workers to the per-execution model — staging /
    # production must enable it deliberately, and the worker hook logs
    # a deprecation warning every time the shared token is accepted
    # (``.claude/rules/security-boundaries.md`` → least-privilege,
    # single-scan worker credentials).
    worker_shared_token_fallback_enabled: bool = False

    @field_validator("database_dsn")
    @classmethod
    def _require_postgresql(cls, value: SecretStr) -> SecretStr:
        dsn = value.get_secret_value()
        if not dsn.startswith(("postgresql://", "postgresql+asyncpg://")):
            raise ValueError("database_dsn must be a PostgreSQL DSN")
        return value

    @model_validator(mode="after")
    def _reject_development_adapters_outside_development(self) -> "Settings":
        if self.environment in (Environment.development, Environment.test):
            return self
        explicitly_enabled = [
            name
            for name, value in (
                ("DEVELOPMENT_AUTH_ENABLED", self.development_auth_enabled),
                (
                    "DEVELOPMENT_PROVISIONING_ENABLED",
                    self.development_provisioning_enabled,
                ),
            )
            if value is True
        ]
        if explicitly_enabled:
            raise ValueError(
                "development adapters must be disabled outside development/test: "
                + ", ".join(explicitly_enabled)
            )
        return self

    @model_validator(mode="after")
    def _require_worker_auth_token_in_deployed_environments(self) -> "Settings":
        """Refuse to start a deployed environment without a worker credential.

        Staging and production must configure ``worker_auth_token`` so the worker
        transition hooks can authenticate a real worker. Without it the hooks
        would fail closed at runtime — safe, but the worker pipeline could never
        advance an execution, so this surfaces the misconfiguration at startup
        instead. Development/test may omit it (the hooks simply stay closed until
        a token is set). The token value is never included in the error.
        """
        if (
            self.environment in (Environment.staging, Environment.production)
            and self.worker_auth_token is None
        ):
            raise ValueError(
                "worker_auth_token must be configured in staging and production"
            )
        return self

    @model_validator(mode="after")
    def _reject_in_memory_dispatcher_outside_development(self) -> "Settings":
        """Refuse to start with the in-memory dispatcher outside development/test.

        The in-memory adapter is a local development convenience: it stores
        dispatch messages in process memory and runs no worker. Allowing it in
        staging or production would mean executions are accepted but never
        delivered to a real worker, defeating the fail-closed default
        (``.claude/rules/security-boundaries.md``). Selecting it outside
        development/test fails fast at startup rather than silently weakening
        production.
        """
        if (
            self.validation_dispatcher_backend is ValidationDispatcherBackend.in_memory
            and self.environment not in (Environment.development, Environment.test)
        ):
            raise ValueError(
                "validation_dispatcher_backend=in_memory is only allowed in "
                "development and test environments"
            )
        return self

    @model_validator(mode="after")
    def _require_broker_url_for_celery_backend(self) -> "Settings":
        """Refuse to start with the Celery backend selected but no broker URL.

        The Celery publisher needs a broker URL to connect to RabbitMQ; without
        one it would fail at dispatch time. Surfacing the misconfiguration at
        startup keeps the contract honest in every environment — dev/test,
        staging, and production. The broker URL itself is never echoed in the
        error message; the value is a :class:`SecretStr` and the validator
        names only the rule.
        """
        if (
            self.validation_dispatcher_backend is ValidationDispatcherBackend.celery
            and self.celery_broker_url is None
        ):
            raise ValueError(
                "celery_broker_url must be configured when "
                "validation_dispatcher_backend=celery"
            )
        return self

    def _resolve_development_flag(self, explicit: bool | None) -> bool:
        if explicit is None:
            return self.environment in (Environment.development, Environment.test)
        return explicit

    @property
    def development_auth_active(self) -> bool:
        """Whether the header-based development tenant adapter is in effect."""
        return self._resolve_development_flag(self.development_auth_enabled)

    @property
    def development_provisioning_active(self) -> bool:
        """Whether the development organization-provisioning adapter is in effect."""
        return self._resolve_development_flag(self.development_provisioning_enabled)

    @property
    def cors_origins_list(self) -> list[str]:
        """Split ``cors_origins`` into a list for the CORS middleware."""
        raw = self.cors_origins.strip()
        if not raw:
            return []
        return [o.strip() for o in raw.split(",")]


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings, loaded once from the environment."""
    return Settings()
