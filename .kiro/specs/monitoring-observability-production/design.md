# Design Document — Monitoring & Observability (Production)

## Overview

This design promotes the SecureScope control-plane backend from its current stub
(`app.platform.observability`) and minimal health check (`app.platform.health`)
to full production-grade observability. The four pillars are:

1. **Structured JSON Logging** — every log record is a queryable JSON object
2. **Prometheus RED Metrics** — `/metrics` endpoint with request and pool gauges
3. **Enhanced Health Checks** — separate `/healthz` (liveness) and `/readyz` (readiness)
4. **Distributed Tracing with OTLP Export** — spans exported via OTLP/gRPC in deployed envs

A static **Alerting Contract** file rounds out the deliverable for SRE consumers.

---

## Architecture

All observability logic lives in `app.platform.*` — the cross-cutting platform
layer. No domain module (assets, scans, etc.) imports from this feature directly;
they inherit it via the FastAPI app wiring in `app.main`.

```
app.main
  └── instrument_app(app, settings)          # entry point, unchanged signature
        ├── _configure_logging(settings)      # new: JSON log formatter + filter
        ├── _configure_tracing(settings)      # expanded: OTLP exporter + batch
        ├── _configure_metrics(app, settings) # new: Prometheus middleware + /metrics
        └── health.router                     # expanded: /healthz + /readyz
```

Middleware execution order on an inbound request:

```
PrometheusMiddleware  →  OTel FastAPIInstrumentor  →  route handler
```

---

## Components and Interfaces

### `app.platform.observability` (expand existing file)

**`_configure_logging(settings)`**
- Installs a `StructuredJsonFormatter` on the root logger.
- The formatter serialises each `LogRecord` to a single-line JSON string
  containing: `timestamp` (ISO-8601), `level`, `logger` (= `module`),
  `message`, `trace_id`, `span_id`, `environment`.
- A `TraceContextFilter` reads the active OTel span via
  `opentelemetry.trace.get_current_span()` to inject `trace_id`/`span_id`.
  Falls back to zero-value strings when no span is active.
- Exception info is serialised as a nested `exception` object
  `{type, message, traceback}` when `record.exc_info` is set.
- In `staging`/`production` the plain-text `StreamHandler` is removed; in
  `development`/`test` both formatters coexist for readability.

**`_configure_tracing(settings)`**  
Expands the existing stub:
- Reads `OTEL_EXPORTER_OTLP_ENDPOINT` from the environment.
- If set **and** environment is `production`/`staging`: configures
  `OTLPSpanExporterGRPC` + `BatchSpanProcessor`.
- Otherwise: uses `NoOpSpanExporter` (no environment variable leaks spans in
  development).
- `SpanExportErrorHandler` wraps the processor; export failures emit a
  `WARNING` structured log but never raise into the request path.
- Propagator set to `TraceContextPropagator` (W3C `traceparent`/`tracestate`).
- SQLAlchemy instrumentation added via
  `SQLAlchemyInstrumentor().instrument(engine=engine)` — called from the
  lifespan after engine construction.

**`PrometheusMiddleware`** (new `Starlette` middleware class in this file)
- Wraps every request: records `http_requests_total` (counter, labels:
  `method`, `path_template`, `status_code`) and
  `http_request_duration_seconds` (histogram, labels: `method`,
  `path_template`).
- `path_template` is resolved from `request.scope["route"].path` (FastAPI
  route path, not the raw URL) to avoid cardinality explosion.
- Metrics are registered with `prometheus_client`'s default `REGISTRY`.

**`_configure_metrics(app, settings)`**
- Adds `PrometheusMiddleware` to the app.
- Mounts a bare ASGI handler at `/metrics` using
  `prometheus_client.make_asgi_app()` — registered directly on `app.router`
  with `include_in_schema=False` so it is invisible to OpenAPI.
- A `DBPoolGauge` (single `Gauge` instance) is updated on each scrape by
  reading `engine.pool.checkedout()` from `app.state.db_engine`.

**`instrument_app(app, settings)`** — existing entry point, updated:
- Now calls all three `_configure_*` helpers in order.
- Signature unchanged; callers in `app.main` and tests require no update.

---

### `app.platform.health` (expand existing file)

**`/healthz`** — unchanged behaviour, no dependency probing:
```
GET /healthz → 200 {"status": "ok"}
```

**`/readyz`** — new route (replaces the stub if one exists):
- Runs each dependency check with `asyncio.wait_for(..., timeout=2.0)`.
- Check functions:
  - `_check_database(engine)` — executes `SELECT 1` via `engine.connect()`.
  - `_check_broker(settings)` — connects to `celery_broker_url` only when
    `validation_dispatcher_backend == celery`; skipped otherwise.
- Returns `200` + `{"status":"ok","checks":{...}}` when all pass.
- Returns `503` + `{"status":"degraded","checks":{...}}` on any failure.
  The `checks` dict maps component name → `{"status":"ok"|"failed","error":"..."}`.
- Uses `app.state.db_engine` and `app.state.settings` from the FastAPI
  app state (injected via `Request`).

---

### `alerts/securescope_alerts.yaml` (new static file)

Location: `backend/alerts/securescope_alerts.yaml`

Schema:
```yaml
# schema_version: 1
groups:
  - name: securescope
    rules:
      - alert: HighErrorRate      # HTTP 5xx rate > 5% over 5m
      - alert: HighLatencyP99     # p99 > 2s over 5m
      - alert: ServiceDown        # zero healthy instances > 1m
      - alert: DatabaseUnhealthy  # /readyz failing > 2m
```

Each rule carries labels: `severity` (`critical`|`warning`), `service:
securescope`, `environment: "{{ $labels.environment }}"`. No Alertmanager
`routes:` or `receivers:` keys are present.

---

## Data Models

### `StructuredLog` (JSON schema — not a Python model)

```
{
  "timestamp":   "2024-01-01T00:00:00.000Z",   // ISO-8601 UTC
  "level":       "INFO",
  "logger":      "app.modules.assets.service",  // = module field
  "message":     "...",
  "trace_id":    "00000000000000000000000000000000",
  "span_id":     "0000000000000000",
  "environment": "production",
  "exception": {                                 // only when exc_info set
    "type":      "ValueError",
    "message":   "...",
    "traceback": "..."
  }
}
```

### Prometheus metric descriptors

| Metric | Type | Labels |
|---|---|---|
| `http_requests_total` | Counter | `method`, `path_template`, `status_code` |
| `http_request_duration_seconds` | Histogram | `method`, `path_template` |
| `db_pool_checked_out` | Gauge | _(none)_ |

### Readiness check response

```
{"status": "ok"|"degraded", "checks": {"database": {"status": "ok"|"failed", "error": "..."}, ...}}
```

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Structured log serialisation round-trip

*For any* valid log record (arbitrary level, logger name, message, environment,
and optional exc\_info), serialising it with `StructuredJsonFormatter` then
deserialising the output with `json.loads` SHALL produce a dict with field
values identical to those encoded.

**Validates: Requirements 1.7, 1.1**

---

### Property 2: Trace context injection

*For any* log record emitted while an OpenTelemetry span with a given
`(trace_id, span_id)` is active, the serialised JSON SHALL contain those exact
`trace_id` and `span_id` values.

**Validates: Requirements 1.2, 1.4**

---

### Property 3: Required fields always present

*For any* log record (varied level, logger, message, environment, with or
without active span, with or without exc\_info), the serialised JSON SHALL
contain all mandatory fields: `timestamp`, `level`, `logger`, `message`,
`trace_id`, `span_id`, `environment`.

**Validates: Requirements 1.1, 1.4**

---

### Property 4: Exception serialisation completeness

*For any* Python exception (varied type and message), a log record that carries
that exception as `exc_info` SHALL serialise to JSON containing a nested
`exception` object with non-empty `type`, `message`, and `traceback` fields.

**Validates: Requirements 1.5**

---

### Property 5: HTTP request counter strict monotonicity

*For any* sequence of `(method, path_template, status_code)` label tuples,
recording each label tuple as an HTTP request SHALL cause the counter value
for that label set to be strictly greater after each increment than before.

**Validates: Requirements 2.2, 2.7**

---

### Property 6: HTTP span attribute completeness

*For any* inbound HTTP request with arbitrary `(method, target, route,
status_code)`, the resulting OTel span SHALL contain non-empty attributes for
`http.method`, `http.target`, `http.status_code`, and `http.route`.

**Validates: Requirements 4.2**

---

### Property 7: DB span sanitisation

*For any* SQLAlchemy query string containing literal parameter values, the
`db.statement` attribute on the resulting span SHALL not contain those literal
values (parameters are bound variables, not inlined strings).

**Validates: Requirements 4.3**

---

### Property 8: Span export failure isolation

*For any* export failure (network timeout, gRPC error, serialisation error),
the exporter SHALL emit exactly one `WARNING`-level structured log and SHALL
NOT propagate an exception into the calling request handler.

**Validates: Requirements 4.5**

---

### Property 9: Liveness independence from dependency state

*For any* combination of database and broker states (healthy, failed, or
unreachable), `GET /healthz` SHALL return `HTTP 200` with `{"status":"ok"}`
and SHALL NOT issue any database or broker query.

**Validates: Requirements 3.1, 3.5**

---

### Property 10: Alert rules label completeness

*For all* alert rules defined in `securescope_alerts.yaml`, every rule SHALL
carry labels `severity`, `service`, and `environment`.

**Validates: Requirements 5.2**

---

## Error Handling

| Scenario | Handling |
|---|---|
| OTLP export failure | `SpanExportErrorHandler` catches, emits WARNING structured log, swallows exception |
| DB check timeout in `/readyz` | `asyncio.wait_for` cancels after 2 s; check marked `failed` with `"error": "timeout"` |
| Broker check timeout in `/readyz` | Same 2-second fence as DB check |
| `/metrics` scrape error | `prometheus_client` ASGI app handles internally; 500 with plain body |
| Formatter error inside logger | Falls back to `logging.lastResort` handler; never raises out of the log call |

---

## Testing Strategy

### Unit / property tests (`pytest` + `hypothesis`)

The project uses `pytest`. Add `hypothesis` for property-based tests.

Property tests (minimum 100 iterations each, tagged with design property):

- **Property 1** — `StructuredJsonFormatter` round-trip with `@given(log_record_strategy())`
- **Property 2** — Trace context injection with `@given(trace_id=..., span_id=...)`
- **Property 3** — Required field presence with `@given(log_record_strategy())`
- **Property 4** — Exception serialisation with `@given(exception_strategy())`
- **Property 5** — Counter monotonicity with `@given(label_sequence_strategy())`
- **Property 6** — HTTP span attributes with `@given(http_request_strategy())`
- **Property 7** — DB span sanitisation with `@given(query_with_literals_strategy())`
- **Property 8** — Export failure isolation with `@given(export_error_strategy())`
- **Property 9** — Liveness independence with `@given(dependency_state_strategy())`
- **Property 10** — Alert rule label completeness (parse YAML, iterate all rules)

Tag format: `# Feature: monitoring-observability-production, Property N: <property_text>`

Example-based / smoke tests (`pytest`):

- `GET /healthz` → 200, correct body
- `GET /readyz` with mocked healthy deps → 200, all checks pass
- `GET /readyz` with mocked DB failure → 503, `checks.database.status == "failed"`
- `GET /readyz` with mocked broker failure (celery backend) → 503
- `/readyz` returns within 2 s when a dep mock hangs indefinitely
- `GET /metrics` → 200, `Content-Type: text/plain`
- `/metrics` absent from `GET /openapi.json` paths
- OTLP exporter type with and without `OTEL_EXPORTER_OTLP_ENDPOINT` env var
- `securescope_alerts.yaml` has `# schema_version: 1` header
- `securescope_alerts.yaml` contains HighErrorRate, HighLatencyP99, ServiceDown, DatabaseUnhealthy
- `securescope_alerts.yaml` has no Alertmanager routing keys

### Integration tests

- `db_pool_checked_out` gauge reflects actual SQLAlchemy pool state (1–2 examples)
- End-to-end OTLP span export to a local OTLP collector container (CI optional)
