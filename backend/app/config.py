"""Application configuration for the SecureScope control plane.

Settings are loaded once from the environment. Secret-bearing values use
``SecretStr`` so they never surface in logs, tracebacks, or the ``Settings``
repr — see ``.claude/rules/data-handling.md``.
"""

from enum import StrEnum
from functools import lru_cache
from uuid import UUID

from pydantic import EmailStr, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEVELOPMENT_JWT_SECRET = "securescope-dev-jwt-secret-change-in-production-2026"  # noqa: S105


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

    # A source-visible fallback is permitted solely for local development and
    # tests. Deployed environments must provide a distinct secret below.
    jwt_secret: SecretStr = SecretStr(_DEVELOPMENT_JWT_SECRET)

    # The initial administrator is opt-in, environment-provided, and bound to
    # an existing organization. No application default credential exists.
    bootstrap_admin_email: EmailStr | None = None
    bootstrap_admin_username: str | None = None
    bootstrap_admin_password: SecretStr | None = None
    bootstrap_admin_organization_id: UUID | None = None
    bootstrap_admin_full_name: str | None = None

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
    worker_shared_token_fallback_enabled: bool = False

    # AI Proof-of-Risk Fireworks config
    fireworks_api_key: SecretStr | None = None
    fireworks_base_url: str = "https://api.fireworks.ai/inference/v1"
    fireworks_model_name: str | None = None
    ai_fireworks_timeout_seconds: float = 20.0
    ai_fireworks_max_retries: int = 1
    ai_max_remote_tokens: int = 4000
    ai_temperature: float = 0.2

    # AI Proof-of-Risk AMD Local Model config
    ai_local_amd_enabled: bool = False
    ai_local_amd_base_url: str | None = None
    ai_local_amd_model_name: str | None = None
    ai_local_amd_timeout_seconds: float = 10.0
    ai_local_amd_max_tokens: int = 512
    ai_local_amd_temperature: float = 0.0

    # AI Proof-of-Risk service-level config
    ai_proof_of_risk_enabled: bool = True
    ai_router_mode: str = "deterministic"
    ai_sandbox_simulation_enabled: bool = False

    @field_validator("database_dsn")
    @classmethod
    def _require_postgresql(cls, value: SecretStr) -> SecretStr:
        dsn = value.get_secret_value()
        if not dsn.startswith(("postgresql://", "postgresql+asyncpg://")):
            raise ValueError("database_dsn must be a PostgreSQL DSN")
        return value

    @model_validator(mode="after")
    def _require_secure_jwt_secret_in_deployed_environments(self) -> "Settings":
        if self.environment in (Environment.staging, Environment.production):
            if self.jwt_secret.get_secret_value() == _DEVELOPMENT_JWT_SECRET:
                raise ValueError(
                    "jwt_secret must be configured to a non-development value "
                    "in staging and production"
                )
        return self

    @model_validator(mode="after")
    def _validate_bootstrap_admin_configuration(self) -> "Settings":
        required_values = (
            self.bootstrap_admin_email,
            self.bootstrap_admin_username,
            self.bootstrap_admin_password,
            self.bootstrap_admin_organization_id,
        )
        supplied_count = sum(value is not None for value in required_values)
        if supplied_count not in (0, len(required_values)):
            raise ValueError(
                "bootstrap admin email, username, password, and organization ID "
                "must be configured together"
            )
        if supplied_count:
            password = self.bootstrap_admin_password
            username = self.bootstrap_admin_username
            if password is None or len(password.get_secret_value()) < 12:
                raise ValueError(
                    "bootstrap_admin_password must be at least 12 characters"
                )
            if username is None or not username.strip():
                raise ValueError("bootstrap_admin_username must not be empty")
        return self

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
        """Refuse to start a deployed environment without a worker credential."""
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
        """Refuse to start with the in-memory dispatcher outside development/test."""
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
        """Refuse to start with the Celery backend selected but no broker URL."""
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
    def bootstrap_admin(self) -> tuple[str, str, str, UUID, str | None] | None:
        """Return the complete opt-in bootstrap configuration, if supplied."""
        if self.bootstrap_admin_email is None:
            return None
        password = self.bootstrap_admin_password
        organization_id = self.bootstrap_admin_organization_id
        username = self.bootstrap_admin_username
        if password is None or organization_id is None or username is None:
            raise RuntimeError("validated bootstrap admin configuration is incomplete")
        return (
            str(self.bootstrap_admin_email),
            username,
            password.get_secret_value(),
            organization_id,
            self.bootstrap_admin_full_name,
        )

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
        return [origin.strip() for origin in raw.split(",")]


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings, loaded once from the environment."""
    return Settings()
