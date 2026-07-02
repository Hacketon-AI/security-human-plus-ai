"""OpenTelemetry tracing wiring for the control plane.

This configures the tracer provider and FastAPI instrumentation only. Span
exporters (e.g. an OTLP endpoint) are supplied by the deployment environment,
not hard-coded here.
"""

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider

from app.config import Settings

# The global tracer provider is process-wide and must be set once; repeated
# app construction (e.g. in tests) reuses it rather than replacing it.
_provider_configured = False


def instrument_app(app: FastAPI, settings: Settings) -> None:
    """Attach the tracer provider and FastAPI instrumentation to ``app``."""
    global _provider_configured
    if not _provider_configured:
        resource = Resource.create(
            {
                "service.name": settings.app_name,
                "deployment.environment": settings.environment.value,
            }
        )
        trace.set_tracer_provider(TracerProvider(resource=resource))
        _provider_configured = True

    FastAPIInstrumentor.instrument_app(app)
