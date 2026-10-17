#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

case "${1:-offline}" in
  setup)
    uv sync --frozen --extra dev --extra observability
    npm ci --prefix apps/web
    ;;
  offline)
    unset OPERION_TEST_ACTION_DATABASE_URL
    uv run --frozen --extra observability ruff check src tests
    PYDANTIC_AI_NO_BANNER=1 PYTHONPATH=src uv run --frozen --extra observability python -m unittest discover -s tests -q
    ;;
  case)
    shift
    PYTHONPATH=src uv run --frozen --extra observability python scripts/verify_cases.py "$@"
    ;;
  postgres)
    PYDANTIC_AI_NO_BANNER=1 PYTHONPATH=src uv run --frozen --extra observability python scripts/test_postgres.py
    ;;
  web)
    (cd apps/web && npm ci && npx tsc --noEmit && npm run build -- --webpack)
    ;;
  *)
    echo "usage: scripts/verify.sh {setup|offline|case [id] [--layer domain|agent|mcp]|postgres|web}" >&2
    exit 2
    ;;
esac
