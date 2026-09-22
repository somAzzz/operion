#!/usr/bin/env bash
set -euo pipefail

repo=$(cd "$(dirname "$0")/.." && pwd)
runtime="$repo/var/interview-demo"

stop_services() {
  if [ -f "$runtime/pids" ]; then
    while read -r pid label; do
      if [ -n "${pid:-}" ] && kill -0 "$pid" 2>/dev/null; then
        kill "$pid"
        echo "stopped $label ($pid)"
      fi
    done < "$runtime/pids"
    rm -f "$runtime/pids"
  fi
}

status_services() {
  if [ ! -f "$runtime/pids" ]; then
    echo "no Operion interview services are recorded as running"
    return
  fi
  while read -r pid label; do
    if kill -0 "$pid" 2>/dev/null; then
      echo "$label running pid=$pid"
    else
      echo "$label stopped pid=$pid"
    fi
  done < "$runtime/pids"
  [ -f "$runtime/effective-config.txt" ] && cat "$runtime/effective-config.txt"
}

ensure_port_free() {
  port=$1
  label=$2
  if ss -H -ltn "sport = :$port" | grep -q .; then
    echo "$label port $port is already in use; stop the stale service first" >&2
    ss -H -ltnp "sport = :$port" >&2 || true
    return 1
  fi
}

wait_for_http() {
  pid=$1
  label=$2
  url=$3
  shift 3
  status=000
  for _ in $(seq 1 30); do
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "$label exited during startup" >&2
      return 1
    fi
    status=$(curl -s -o /dev/null -w '%{http_code}' "$@" "$url" || true)
    [ "$status" = 200 ] && return 0
    sleep 1
  done
  echo "$label did not become ready: $url returned HTTP $status" >&2
  return 1
}

start_profile() {
  profile=$1
  config="$repo/config/interview/$profile.env"
  [ -f "$config" ] || { echo "unknown profile: $profile" >&2; exit 2; }
  stop_services
  mkdir -p "$runtime"
  chmod 700 "$runtime"
  set -a
  # shellcheck disable=SC1090
  source "$config"
  if [ "$profile" = e2-controlled-action ]; then
    # Only the two read-only upstream credentials are inherited by the Agent.
    export TWENTY_API_KEY_READ_ONLY="$(
      "$repo/.venv/bin/python" -c \
        "from pathlib import Path; from operion_etl.twenty import read_env; print(read_env(Path('$repo/.env'))['TWENTY_API_KEY_READ_ONLY'])"
    )"
    export ERPNEXT_API_KEY_READ_ONLY="$(
      "$repo/.venv/bin/python" -c \
        "from pathlib import Path; from operion_etl.twenty import read_env; print(read_env(Path('$repo/.env'))['ERPNEXT_API_KEY_READ_ONLY'])"
    )"
    export OPERION_ACTION_DATABASE_URL='postgresql://operion_demo:operion_demo_local_only@127.0.0.1:55432/operion_action_demo'
  fi
  export OPERION_OBSERVED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  export OPERION_AGENT_TOKEN="$(openssl rand -hex 24)"
  export OPERION_ACTION_TOKEN="$(openssl rand -hex 24)"
  export OPERION_ACTION_CSRF_TOKEN="$(openssl rand -hex 24)"
  export OPERION_SESSION_DB="$runtime/$profile-sessions.sqlite3"
  set +a

  ensure_port_free "$OPERION_AGENT_PORT" "Agent"
  ensure_port_free "$OPERION_WEB_PORT" "Web"
  if [ "$profile" = e2-controlled-action ]; then
    ensure_port_free 8001 "Action API"
  fi

  if [ "$profile" = e2-controlled-action ]; then
    "$repo/scripts/setup-interview-action-db.sh"
  fi
  curl -fsS "$OPERION_MODEL_BASE_URL/models" \
    -H "Authorization: Bearer $OPERION_MODEL_API_KEY" >/dev/null

  cd "$repo"
  nohup .venv/bin/operion-agent >"$runtime/agent.log" 2>&1 &
  agent_pid=$!
  printf '%s agent\n' "$agent_pid" >"$runtime/pids"
  if [ "$profile" = e2-controlled-action ]; then
    nohup .venv/bin/operion-action-api >"$runtime/action.log" 2>&1 &
    action_pid=$!
    printf '%s action-api\n' "$action_pid" >>"$runtime/pids"
  fi
  cd "$repo/apps/web"
  export OPERION_AGENT_URL=http://127.0.0.1:8000/api/agent
  export OPERION_ACTION_URL=http://127.0.0.1:8001/api
  export OPERION_TWENTY_WEB_URL=http://localhost:3000
  nohup ./node_modules/.bin/next start -p "$OPERION_WEB_PORT" \
    >"$runtime/web.log" 2>&1 &
  web_pid=$!
  printf '%s web\n' "$web_pid" >>"$runtime/pids"

  # Check the processes we just launched, not merely whichever stale service
  # happens to answer on the configured ports. The authenticated endpoints also
  # prove that Agent and Next.js inherited the same ephemeral credential.
  if ! wait_for_http "$agent_pid" "Agent" \
    "http://127.0.0.1:$OPERION_AGENT_PORT/api/conversations" \
    -H "Authorization: Bearer $OPERION_AGENT_TOKEN"; then
    stop_services
    return 1
  fi
  if ! wait_for_http "$web_pid" "Web" \
    "http://127.0.0.1:$OPERION_WEB_PORT/api/conversations"; then
    stop_services
    return 1
  fi
  if [ "$profile" = e2-controlled-action ]; then
    curl -fsS http://127.0.0.1:8001/health \
      -H "Authorization: Bearer $OPERION_ACTION_TOKEN" >/dev/null
  fi
  cat >"$runtime/effective-config.txt" <<EOF
profile=$profile
dataset=$OPERION_CANONICAL_DIR
identity_map=$OPERION_IDENTITY_MAP
data_mode=$OPERION_DATA_MODE
observed_at=$OPERION_OBSERVED_AT
customer_scope=$OPERION_CUSTOMER_IDS
supplier_scope=$OPERION_SUPPLIER_IDS
model=$OPERION_MODEL_NAME@$OPERION_MODEL_BASE_URL
model_budget=requests:$OPERION_MAX_MODEL_REQUESTS,tools:$OPERION_MAX_TOOL_CALLS,input_run:$OPERION_MAX_INPUT_TOKENS,output_request:$OPERION_MAX_OUTPUT_TOKENS,output_run:$OPERION_MAX_RUN_OUTPUT_TOKENS,timeout_seconds:$OPERION_RUN_TIMEOUT_SECONDS
web=http://127.0.0.1:$OPERION_WEB_PORT
EOF
  chmod 600 "$runtime/effective-config.txt"
  echo "Operion $profile is ready at http://127.0.0.1:$OPERION_WEB_PORT"
}

case "${1:-status}" in
  start-wwi) start_profile wwi-snapshot ;;
  start-e2) start_profile e2-controlled-action ;;
  stop) stop_services ;;
  status) status_services ;;
  *) echo "usage: $0 {start-wwi|start-e2|stop|status}" >&2; exit 2 ;;
esac
