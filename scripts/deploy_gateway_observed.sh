#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

env_file=${OPERION_GATEWAY_ENV_FILE:-.env.langfuse.local}
if [[ ! -f "$env_file" ]]; then
  echo "Missing $env_file; the observed gateway must not start without its telemetry configuration." >&2
  exit 1
fi

check_only=0
if [[ "${1:-}" == "--check" ]]; then
  check_only=1
  shift
fi

if (( $# == 0 )); then
  services=(agent web)
else
  services=("$@")
fi
for service in "${services[@]}"; do
  case "$service" in
    agent|web) ;;
    *) echo "Usage: $0 [--check] [agent] [web]" >&2; exit 2 ;;
  esac
done

compose=(docker compose --env-file "$env_file" -f deploy/gateway/compose.yaml)
if [[ -n "${OPERION_GATEWAY_IMAGE_OVERRIDE:-}" ]]; then
  compose+=(-f "$OPERION_GATEWAY_IMAGE_OVERRIDE")
fi
"${compose[@]}" config --format json | python3 -c '
import json
import sys

services = json.load(sys.stdin)["services"]
for name in ("agent", "web"):
    environment = services[name]["environment"]
    if str(environment.get("OPERION_OTEL_ENABLED")) != "1":
        raise SystemExit(f"{name}: OPERION_OTEL_ENABLED must be 1")
    if environment.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT") != "http://collector:4318/v1/traces":
        raise SystemExit(f"{name}: OTLP endpoint must target the gateway Collector")
'

collector_id=$("${compose[@]}" ps -q collector)
if [[ -z "$collector_id" ]] || [[ "$(docker inspect -f '{{.State.Running}}' "$collector_id")" != true ]]; then
  echo "Collector is not running; start it using the Langfuse runbook before deploying." >&2
  exit 1
fi

if (( check_only )); then
  echo "Observed gateway configuration is ready for: ${services[*]}"
  exit 0
fi

if [[ -n "${OPERION_GATEWAY_IMAGE_OVERRIDE:-}" ]]; then
  "${compose[@]}" pull "${services[@]}"
  "${compose[@]}" up -d --no-deps --no-build --pull never --wait "${services[@]}"
else
  "${compose[@]}" build "${services[@]}"
  "${compose[@]}" up -d --no-deps --wait "${services[@]}"
fi

for service in "${services[@]}"; do
  container_id=$("${compose[@]}" ps -q "$service")
  if [[ -z "$container_id" ]] || ! docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$container_id" | rg -q '^OPERION_OTEL_ENABLED=1$'; then
    echo "$service is not running with tracing enabled." >&2
    exit 1
  fi
done
echo "Observed gateway deployed with tracing enabled: ${services[*]}"
