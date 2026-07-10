# Requirements Document

## Introduction

This feature promotes the SecureScope control-plane backend from basic liveness
probing and stub tracing to full production-grade observability. It covers
structured JSON logging, Prometheus metrics collection, enhanced health checks
(liveness + readiness with dependency probing), distributed tracing with OTLP
export, and an alerting contract for SRE consumers. The platform is a
Python/FastAPI backend with modules: assets, asset\_verifications,
authorizations, engagements, projects, organizations, scans/findings, and
validation\_executions.

---

## Glossary

- **Control\_Plane**: The FastAPI backend process (`app.main`).
- **Platform\_Layer**: `app.platform.*` — cross-cutting infrastructure used by all modules.
- **Observability\_Module**: The new `app.platform.observability` expansion and
  any new sibling platform files introduced by this feature.
- **Health\_Endpoint**: The HTTP endpoints `/healthz` (liveness) and `/readyz`
  (readiness) served by the Control\_Plane.
- **Metrics\_Endpoint**: The HTTP endpoint `/metrics` served by the
  Control\_Plane that emits Prometheus-format metrics.
- **OTLP\_Exporter**: An OpenTelemetry Protocol span exporter configured via
  environment variables (`OTEL_EXPORTER_OTLP_ENDPOINT`, etc.).
- **Structured\_Log**: A log record emitted as a single-line JSON object
  containing at minimum: `timestamp`, `level`, `logger`, `message`,
  `trace_id`, `span_id`, `module`, and `environment` fields.
- **RED\_Metrics**: The three standard service metrics: request Rate, Error
  rate, and request Duration (latency histogram).
- **Span**: An OpenTelemetry distributed-tracing unit of work.
- **Alert\_Rule**: A Prometheus alerting rule (YAML) that fires when a
  threshold is breached, consumed by an external Alertmanager.

---

## Requirements

### Requirement 1: Structured JSON Logging

**User Story:** As an SRE, I want every log record emitted by the control plane
to be a structured JSON object with standard fields, so that I can query,
filter, and correlate logs in a log-aggregation system without parsing
unstructured text.

#### Acceptance Criteria

1. THE Control\_Plane SHALL emit all log records as single-line JSON objects
   conforming to the Structured\_Log schema.
2. WHEN a log record is created inside an active OpenTelemetry Span, THE
   Control\_Plane SHALL include the current `trace_id` and `span_id` in the
   Structured\_Log.
3. WHEN a log record is created outside any active Span, THE Control\_Plane
   SHALL set `trace_id` and `span_id` to `"00000000000000000000000000000000"` and
   `"0000000000000000"` respectively.
4. THE Control\_Plane SHALL include `module` (dotted Python logger name) and
   `environment` (value of `Settings.environment`) in every Structured\_Log.
5. IF a log record contains a Python `exc_info` tuple, THEN THE Control\_Plane
   SHALL serialize the exception type, message, and traceback as a nested
   `exception` object within the Structured\_Log.
6. THE Control\_Plane SHALL NOT emit log records in plain-text format in
   `staging` or `production` environments.
7. FOR ALL valid log records, serializing then deserializing the Structured\_Log
   SHALL produce an object with identical field values (round-trip property).

---

### Requirement 2: Prometheus Metrics Collection

**User Story:** As an SRE, I want the control plane to expose RED metrics and
key business counters on a `/metrics` endpoint, so that I can monitor service
health and set up alerts in Prometheus.

#### Acceptance Criteria

1. THE Observability\_Module SHALL expose a `/metrics` HTTP endpoint that
   returns metrics in Prometheus text exposition format.
2. THE Observability\_Module SHALL record a `http_requests_total` counter
   labelled with `method`, `path_template`, and `status_code` for every HTTP
   response served by the Control\_Plane.
3. THE Observability\_Module SHALL record an `http_request_duration_seconds`
   histogram labelled with `method` and `path_template` for every HTTP response.
4. THE Observability\_Module SHALL record a `db_pool_checked_out` gauge
   reflecting the current number of SQLAlchemy pool connections in use.
5. WHEN the `/metrics` endpoint is scraped, THE Observability\_Module SHALL
   respond within 500 ms under normal load.
6. THE Observability\_Module SHALL NOT expose the `/metrics` endpoint as a
   documented API route in OpenAPI/Swagger.
7. FOR ALL request counts, incrementing the counter then reading it back SHALL
   return the incremented value (idempotence of counter state does not apply;
   counter must be strictly monotonic).

---

### Requirement 3: Enhanced Health Checks

**User Story:** As an SRE and Kubernetes operator, I want separate liveness and
readiness probes that distinguish process health from dependency availability,
so that traffic is only routed to instances that can serve requests.

#### Acceptance Criteria

1. THE Health\_Endpoint `/healthz` SHALL return `HTTP 200` with body
   `{"status": "ok"}` whenever the Control\_Plane process is running, regardless
   of dependency state.
2. THE Health\_Endpoint `/readyz` SHALL return `HTTP 200` with body
   `{"status": "ok", "checks": {...}}` only when all required dependencies
   (database connectivity, broker reachability when celery backend is active)
   report healthy.
3. IF the database connection check fails, THEN THE Health\_Endpoint `/readyz`
   SHALL return `HTTP 503` with body `{"status": "degraded", "checks": {...}}`
   where the `checks` object identifies the failing component.
4. IF the celery broker connection check fails while
   `validation_dispatcher_backend=celery`, THEN THE Health\_Endpoint `/readyz`
   SHALL return `HTTP 503` with body `{"status": "degraded", "checks": {...}}`.
5. THE Health\_Endpoint `/healthz` SHALL NOT perform database or broker queries.
6. THE Health\_Endpoint `/readyz` SHALL complete each dependency check within
   2 seconds and return a result even if a check times out (marking that check
   as failed rather than blocking indefinitely).

---

### Requirement 4: Distributed Tracing with OTLP Export

**User Story:** As a platform engineer, I want every inbound HTTP request and
outbound database query to be captured as an OpenTelemetry Span and exported
via OTLP, so that I can trace end-to-end request flows across services.

#### Acceptance Criteria

1. THE Observability\_Module SHALL configure an OTLP span exporter when the
   environment variable `OTEL_EXPORTER_OTLP_ENDPOINT` is set; otherwise THE
   Observability\_Module SHALL fall back to a no-op exporter.
2. WHEN an HTTP request is received, THE Control\_Plane SHALL record a root Span
   including `http.method`, `http.target`, `http.status_code`, and
   `http.route` attributes.
3. WHEN a database query is executed via SQLAlchemy, THE Control\_Plane SHALL
   record a child Span including `db.system`, `db.statement` (sanitised — no
   literal parameter values), and `db.operation` attributes.
4. WHERE the `environment` is `production` or `staging`, THE
   Observability\_Module SHALL set the OTLP exporter to use gRPC transport and
   batch span processing.
5. IF a Span export attempt fails, THEN THE Observability\_Module SHALL log the
   failure as a Structured\_Log at `WARNING` level without raising an exception
   that would affect the request path.
6. THE Observability\_Module SHALL propagate W3C TraceContext (`traceparent`,
   `tracestate`) headers on all inbound and outbound HTTP calls.

---

### Requirement 5: Alerting Contract

**User Story:** As an SRE, I want a versioned set of Prometheus alert rules
covering error rate, latency, and service availability, so that on-call
engineers are paged before users notice problems.

#### Acceptance Criteria

1. THE Observability\_Module SHALL provide a Prometheus alert-rule YAML file
   defining at minimum the following Alert\_Rules: `HighErrorRate`
   (HTTP 5xx rate > 5 % over 5 min), `HighLatencyP99` (p99 latency > 2 s over
   5 min), `ServiceDown` (Control\_Plane has zero healthy instances for > 1 min),
   and `DatabaseUnhealthy` (readiness probe failing for > 2 min).
2. WHEN an Alert\_Rule fires, THE Alert\_Rule SHALL include labels: `severity`
   (`critical` or `warning`), `service` (`securescope`), and `environment`.
3. THE Alert\_Rule file SHALL be versioned with a `# schema_version: 1` header
   comment so consumers can detect breaking changes.
4. IF an alert threshold is changed, THEN THE Alert\_Rule file schema version
   SHALL be incremented.
5. THE Observability\_Module SHALL NOT hard-code Alertmanager routing or
   notification channels in the alert-rule file; routing is owned by the
   deployment environment.
