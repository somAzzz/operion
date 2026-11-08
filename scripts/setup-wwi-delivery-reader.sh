#!/usr/bin/env bash
set -euo pipefail
umask 077
repo=$(cd "$(dirname "$0")/.." && pwd)
source "$repo/scripts/demo-runtime.sh"
secret="$repo/var/demo/wwi-delivery-password"
mkdir -p "$(dirname "$secret")"
if [[ ! -e "$secret" ]]; then
  temp=$(mktemp "${secret}.XXXXXX")
  trap 'rm -f "$temp"' EXIT
  { printf 'Op1@'; openssl rand -hex 32; } >"$temp"
  ln "$temp" "$secret" || [[ -f "$secret" ]]
fi
password=$(<"$secret")
[[ "$password" =~ ^Op1@[a-f0-9]{64}$ ]] || { echo 'Invalid local reader secret' >&2; exit 1; }
{
  cat "$repo/scripts/wwi_delivery.sql"
  cat <<SQL
IF SUSER_ID('operion_delivery_reader') IS NULL
    CREATE LOGIN operion_delivery_reader WITH PASSWORD = '$password', CHECK_POLICY = ON;
IF DATABASE_PRINCIPAL_ID('operion_delivery_reader') IS NULL
    CREATE USER operion_delivery_reader FOR LOGIN operion_delivery_reader;
GRANT EXECUTE ON OBJECT::dbo.operion_read_delivery TO operion_delivery_reader;
GO
SQL
} | docker exec -i "${WWI_SQL_CONTAINER:-enterprise-demo-mssql}" bash -ec '
  cmd=/opt/mssql-tools18/bin/sqlcmd
  [[ -x "$cmd" ]] || cmd=/opt/mssql-tools/bin/sqlcmd
  export SQLCMDPASSWORD="$MSSQL_SA_PASSWORD"
  exec "$cmd" -S localhost -U sa -C -b -d WideWorldImporters -i /dev/stdin
'
