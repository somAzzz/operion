from __future__ import annotations

import json
import subprocess


class SqlServer:
    """Read WWI through sqlcmd inside the existing isolated SQL Server container."""

    def __init__(
        self,
        container: str = "enterprise-demo-mssql",
        database: str = "WideWorldImporters",
    ):
        self.container = container
        self.database = database

    def query_json(self, select_sql: str) -> list[dict]:
        sql = f"SET NOCOUNT ON;\n{select_sql.rstrip().rstrip(';')} FOR JSON PATH, INCLUDE_NULL_VALUES;\n"
        shell = (
            "sqlcmd=/opt/mssql-tools18/bin/sqlcmd; "
            '[[ -x "$sqlcmd" ]] || sqlcmd=/opt/mssql-tools/bin/sqlcmd; '
            f'"$sqlcmd" -S localhost -U sa -P "$MSSQL_SA_PASSWORD" -C '
            f"-d {self.database} -b -y 0 -w 65535 -i /dev/stdin"
        )
        completed = subprocess.run(
            ["docker", "exec", "-i", self.container, "bash", "-lc", shell],
            input=sql,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(f"SQL query failed: {detail}")
        payload = "".join(completed.stdout.splitlines()).strip()
        if not payload:
            return []
        try:
            value = json.loads(payload)
        except json.JSONDecodeError as error:
            raise RuntimeError(
                f"SQL returned invalid JSON near character {error.pos}"
            ) from error
        if not isinstance(value, list):
            raise RuntimeError("Expected SQL JSON query to return an array")
        return value
