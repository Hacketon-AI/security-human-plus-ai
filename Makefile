# SecureScope quality gates. Targets run real tools against the backend; they
# fail loudly when a tool is missing or a check does not pass. No fake success.

BACKEND := backend
PYTHON := .venv/bin/python

.PHONY: install format lint typecheck test check

install:
	cd $(BACKEND) && $(PYTHON) -m pip install -e ".[dev]"

format:
	cd $(BACKEND) && $(PYTHON) -m ruff format .

lint:
	cd $(BACKEND) && $(PYTHON) -m ruff check .

typecheck:
	cd $(BACKEND) && $(PYTHON) -m mypy app

test:
	cd $(BACKEND) && $(PYTHON) -m pytest

# Aggregate gate matching the required workflow: lint, type, then test.
check: lint typecheck test
