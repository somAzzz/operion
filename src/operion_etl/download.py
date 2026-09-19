from __future__ import annotations

import hashlib
import json
import os
import tempfile
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

WWI_URL = (
    "https://github.com/microsoft/sql-server-samples/releases/download/"
    "wide-world-importers-v1.0/WideWorldImporters-Full.bak"
)
WWI_RELEASE = "wide-world-importers-v1.0"
WWI_LICENSE_URL = (
    "https://github.com/microsoft/sql-server-samples/blob/master/license.txt"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_wwi(raw_root: Path, snapshot_id: str | None = None) -> Path:
    acquired_at = datetime.now(UTC)
    snapshot_id = snapshot_id or acquired_at.strftime("%Y%m%dT%H%M%SZ")
    snapshot_dir = raw_root / snapshot_id
    backup = snapshot_dir / "WideWorldImporters-Full.bak"
    manifest_path = snapshot_dir / "source_manifest.json"

    if snapshot_dir.exists():
        if backup.is_file() and manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            actual = sha256_file(backup)
            if actual != manifest.get("sha256"):
                raise RuntimeError(
                    f"Existing snapshot checksum mismatch: {snapshot_dir}"
                )
            return snapshot_dir
        raise FileExistsError(
            f"Refusing to overwrite incomplete snapshot: {snapshot_dir}"
        )

    snapshot_dir.mkdir(parents=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix="wwi-", suffix=".part", dir=snapshot_dir
    )
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        request = urllib.request.Request(
            WWI_URL, headers={"User-Agent": "operion-etl/0.1"}
        )
        with (
            urllib.request.urlopen(request, timeout=60) as response,
            temporary.open("wb") as output,
        ):
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        if temporary.stat().st_size < 10_000_000:
            raise RuntimeError(
                "Downloaded file is unexpectedly small; refusing to record it"
            )
        temporary.replace(backup)
    except Exception:
        temporary.unlink(missing_ok=True)
        try:
            snapshot_dir.rmdir()
        except OSError:
            pass
        raise

    manifest = {
        "source": "Microsoft sql-server-samples / Wide World Importers OLTP",
        "source_url": WWI_URL,
        "acquired_at_utc": acquired_at.isoformat(),
        "data_version": WWI_RELEASE,
        "coverage": "WWI sample OLTP history (source database dates retained)",
        "license_url": WWI_LICENSE_URL,
        "usage_class": "public_sample",
        "filename": backup.name,
        "size_bytes": backup.stat().st_size,
        "sha256": sha256_file(backup),
        "immutable": True,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return snapshot_dir
