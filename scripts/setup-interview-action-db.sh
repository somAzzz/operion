#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
container=operion-action-test-postgres
if ! docker inspect "$container" >/dev/null 2>&1; then
  docker run -d --name "$container" \
    -e POSTGRES_USER=operion_test \
    -e POSTGRES_PASSWORD=operion_test_local_only \
    -e POSTGRES_DB=operion_action_test \
    -p 127.0.0.1:55432:5432 postgres:16 >/dev/null
elif [ "$(docker inspect -f '{{.State.Running}}' "$container")" != true ]; then
  docker start "$container" >/dev/null
fi

for _ in $(seq 1 30); do
  if docker exec "$container" pg_isready -U operion_test -d operion_action_test \
    >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
docker exec "$container" pg_isready -U operion_test -d operion_action_test \
  >/dev/null

if ! docker exec "$container" psql -U operion_test -d postgres -tAc \
  "SELECT 1 FROM pg_database WHERE datname='operion_action_demo'" | grep -qx 1; then
  docker exec "$container" createdb -U operion_test operion_action_demo
fi

OPERION_ACTION_MIGRATION_DATABASE_URL='postgresql://operion_test:operion_test_local_only@127.0.0.1:55432/operion_action_demo' \
  .venv/bin/operion-action-migrate >/dev/null

docker exec "$container" psql -U operion_test -d operion_action_demo -v ON_ERROR_STOP=1 \
  -c "DO \$\$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='operion_demo') THEN CREATE ROLE operion_demo LOGIN PASSWORD 'operion_demo_local_only'; END IF; END \$\$;" \
  -c "GRANT operion_action_app TO operion_demo;" >/dev/null

echo "Isolated action demo database is ready on 127.0.0.1:55432."
