# Rule: Python Style

Concrete conventions for the control plane. General standards are in
`CLAUDE.md`; this file fixes the Python-specific choices so code stays uniform.

## Types and errors

- Full type hints on public functions. mypy runs in strict mode; no `Any`
  escape hatch without a commented reason.
- Return typed results and raise domain-specific exceptions, not bare
  `Exception`/`ValueError`, across module boundaries.
- Represent domain states with `enum.Enum` or frozen value objects, not strings.

## FastAPI and Pydantic

- Pydantic v2 models for all request/response bodies; validate at the edge.
- Keep routers thin: parse, authorize, delegate to a module service, map
  result to a response. No business logic or DB queries in route handlers.
- Dependencies via FastAPI `Depends`; no global mutable state.

## SQLAlchemy and async

- SQLAlchemy 2.x typed models with the async engine and `AsyncSession`.
- Make transaction boundaries explicit; do not rely on implicit autocommit.
- Schema changes go through Alembic — never mutate tables outside a migration.

## Naming and shape

- Domain names over `data`/`helper`/`manager`/`processor`/`utils`.
- No base class, repository interface, or service introduced before a second
  concrete caller exists.

## Tooling

Format with Ruff, lint with Ruff, type-check with mypy, test with pytest +
pytest-asyncio. Code must pass `make lint typecheck test` before "done".
