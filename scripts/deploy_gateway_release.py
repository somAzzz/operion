from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def release_images(directory: Path, repository: str, revision: str) -> dict[str, str]:
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Release revision must be a complete Git SHA")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Invalid repository name")
    images = {}
    for service in ("agent", "web"):
        record = json.loads((directory / f"image-{service}.json").read_text())
        if not isinstance(record, dict) or set(record) != {
            "revision",
            "service",
            "image",
        }:
            raise ValueError("Invalid image record fields")
        if record["revision"] != revision or record["service"] != service:
            raise ValueError("Image record does not match the requested release")
        prefix = f"ghcr.io/{repository.lower()}-{service}@sha256:"
        image = record["image"]
        if not isinstance(image, str) or not re.fullmatch(
            re.escape(prefix) + r"[0-9a-f]{64}", image
        ):
            raise ValueError("Image must use this repository's immutable GHCR digest")
        images[service] = image
    return images


def deploy(args) -> None:
    images = release_images(args.manifest_dir, args.repository, args.revision)
    actual = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    if actual != args.revision:
        raise ValueError("Deployment checkout does not match the release revision")
    if not args.env_file.is_absolute() or not args.env_file.is_file():
        raise ValueError("Gateway telemetry env file must be an existing absolute path")
    if not args.runtime_dir.is_absolute() or not args.runtime_dir.is_dir():
        raise ValueError("Gateway runtime directory must be an existing absolute path")
    for name in ("tls/ca.crt", "policy/identity-policy.json"):
        if not (args.runtime_dir / name).is_file():
            raise ValueError(f"Gateway runtime is missing {name}")
    with tempfile.TemporaryDirectory(prefix="operion-release-") as temporary:
        override = Path(temporary) / "images.json"
        override.write_text(
            json.dumps(
                {
                    "services": {
                        service: {"image": image} for service, image in images.items()
                    }
                }
            )
        )
        environment = dict(
            os.environ,
            OPERION_GATEWAY_ENV_FILE=str(args.env_file),
            OPERION_GATEWAY_RUNTIME_DIR=str(args.runtime_dir),
            OPERION_GATEWAY_IMAGE_OVERRIDE=str(override),
            OPERION_RELEASE_ID=args.revision,
        )
        command = ["bash", str(ROOT / "scripts/deploy_gateway_observed.sh")]
        if args.check:
            command.append("--check")
        subprocess.run(command, cwd=ROOT, env=environment, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Deploy verified gateway image digests to an initialized host."
    )
    parser.add_argument("--manifest-dir", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--runtime-dir", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        deploy(args)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Gateway release failed: {error}\n")


if __name__ == "__main__":
    main()
