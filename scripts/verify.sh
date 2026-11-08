#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

case "${1:-offline}" in
  english)
    python3 scripts/check_english.py
    ;;
  setup)
    uv sync --frozen --extra dev --extra observability
    npm ci --prefix apps/web
    ;;
  offline)
    unset OPERION_TEST_ACTION_DATABASE_URL
    python3 scripts/check_english.py
    uv run --frozen --extra observability ruff check --no-fix src tests scripts/check_english.py scripts/deploy_gateway_release.py
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
    (cd apps/web && npm ci && npm run test:session && npm run test:navigation && npx tsc --noEmit && npm run build -- --webpack && npm run test:navigation:render)
    ;;
  *)
    echo "usage: scripts/verify.sh {english|setup|offline|case [id] [--layer domain|agent|mcp]|postgres|web}" >&2
    exit 2
    ;;
esac
