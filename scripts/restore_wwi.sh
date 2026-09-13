#!/usr/bin/env bash
set -euo pipefail

container="${WWI_SQL_CONTAINER:-enterprise-demo-mssql}"
backup_path="${1:?usage: scripts/restore_wwi.sh PATH_TO_WWI_BAK}"

if [[ ! -f "$backup_path" ]]; then
  echo "Backup does not exist: $backup_path" >&2
  exit 2
fi
if ! docker inspect "$container" >/dev/null 2>&1; then
  echo "SQL Server container not found: $container" >&2
  exit 2
fi

container_backup="/tmp/operion-WideWorldImporters-Full.bak"
cleanup() {
  docker exec -u 0 "$container" rm -f "$container_backup" >/dev/null 2>&1 || true
}
trap cleanup EXIT
docker cp "$backup_path" "$container:$container_backup" >/dev/null
docker exec -u 0 "$container" chmod 0644 "$container_backup"

docker exec -i "$container" bash -lc '
  set -euo pipefail
  sqlcmd=/opt/mssql-tools18/bin/sqlcmd
  [[ -x "$sqlcmd" ]] || sqlcmd=/opt/mssql-tools/bin/sqlcmd
  "$sqlcmd" -S localhost -U sa -P "$MSSQL_SA_PASSWORD" -C -b -Q "
IF DB_ID(N'\''WideWorldImporters'\'') IS NULL
BEGIN
  RESTORE DATABASE [WideWorldImporters]
  FROM DISK = N'\''/tmp/operion-WideWorldImporters-Full.bak'\''
  WITH
    MOVE N'\''WWI_Primary'\'' TO N'\''/var/opt/mssql/data/WideWorldImporters.mdf'\'',
    MOVE N'\''WWI_UserData'\'' TO N'\''/var/opt/mssql/data/WideWorldImporters_UserData.ndf'\'',
    MOVE N'\''WWI_Log'\'' TO N'\''/var/opt/mssql/data/WideWorldImporters.ldf'\'',
    MOVE N'\''WWI_InMemory_Data_1'\'' TO N'\''/var/opt/mssql/data/WideWorldImporters_InMemory_Data_1'\'',
    RECOVERY, STATS = 10;
END;
DBCC CHECKDB ([WideWorldImporters]) WITH PHYSICAL_ONLY, NO_INFOMSGS;
SELECT DB_NAME(database_id) AS database_name, state_desc
FROM sys.databases WHERE name = N'\''WideWorldImporters'\'';
"
'
