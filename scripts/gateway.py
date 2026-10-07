#!/usr/bin/env python3
"""Initialize and operate only the isolated Operion local gateway stack."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "var/gateway"
ORIGIN = "https://operion.localhost:8443"
SUBJECTS = {
    "alice": "10000000-0000-4000-8000-000000000001",
    "bob": "10000000-0000-4000-8000-000000000002",
    "unassigned": "10000000-0000-4000-8000-000000000003",
}


def write_secret(path: Path, content: str | bytes, mode: int = 0o600) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(fd, "wb") as stream:
        stream.write(content.encode() if isinstance(content, str) else content)


def initialize() -> None:
    if RUNTIME.exists():
        raise SystemExit(
            "var/gateway already exists; refusing to rotate or overwrite it"
        )
    RUNTIME.mkdir(mode=0o700, parents=True)
    (RUNTIME / "tls").mkdir(mode=0o700)
    (RUNTIME / "policy").mkdir(mode=0o700)
    client_secret = secrets.token_urlsafe(48)
    write_secret(RUNTIME / "client-secret", client_secret)
    write_secret(RUNTIME / "cookie-secret", secrets.token_bytes(32))
    passwords = {name: secrets.token_urlsafe(24) for name in SUBJECTS}
    write_secret(RUNTIME / "credentials.json", json.dumps(passwords, indent=2) + "\n")
    realm = {
        "realm": "operion",
        "enabled": True,
        "sslRequired": "all",
        "registrationAllowed": False,
        "resetPasswordAllowed": False,
        "bruteForceProtected": True,
        "accessTokenLifespan": 300,
        "ssoSessionIdleTimeout": 1800,
        "ssoSessionMaxLifespan": 28800,
        "clients": [
            {
                "clientId": "operion",
                "secret": client_secret,
                "enabled": True,
                "protocol": "openid-connect",
                "publicClient": False,
                "standardFlowEnabled": True,
                "directAccessGrantsEnabled": False,
                "serviceAccountsEnabled": False,
                "redirectUris": [ORIGIN + "/oauth2/callback"],
                "webOrigins": [ORIGIN],
                "attributes": {"pkce.code.challenge.method": "S256"},
                "protocolMappers": [
                    {
                        "name": "operion-audience",
                        "protocol": "openid-connect",
                        "protocolMapper": "oidc-audience-mapper",
                        "config": {
                            "included.client.audience": "operion",
                            "access.token.claim": "true",
                            "id.token.claim": "false",
                        },
                    }
                ],
            }
        ],
        "users": [
            {
                "id": subject,
                "username": name,
                "email": f"{name}@example.test",
                "emailVerified": True,
                "firstName": name.capitalize(),
                "lastName": "Local Test",
                "enabled": True,
                "credentials": [
                    {"type": "password", "value": passwords[name], "temporary": False}
                ],
            }
            for name, subject in SUBJECTS.items()
        ],
    }
    # Keycloak runs as UID 1000. Only this generated import file is world-readable
    # inside its mount; the host parent directory remains mode 0700.
    write_secret(RUNTIME / "realm.json", json.dumps(realm), mode=0o644)
    policy = {
        "schema_version": "operion-identity-policy-v1",
        "policy_version": 1,
        "revoked_sessions": [],
        "users": {
            SUBJECTS[name]: {
                "active": True,
                "valid_after": 0,
                "user_id": name,
                "tenant_id": "operion-local",
                "companies": ["AI Demo GmbH"],
                "customer_ids": [f"wwi:organization:customer:{customer}"],
                "supplier_ids": ["wwi:organization:supplier:7"]
                if name == "alice"
                else [],
                "roles": ["agent_read"],
            }
            for name, customer in [("alice", 65), ("bob", 60)]
        },
    }
    write_secret(RUNTIME / "policy/identity-policy.json", json.dumps(policy, indent=2))
    make_certificates()
    print(f"Initialized {RUNTIME}; passwords are in credentials.json (not printed).")
    print(
        f"Local HTTPS entry: {ORIGIN}; trust only the generated tls/ca.crt for testing."
    )


def make_certificates() -> None:
    now = datetime.now(UTC)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "Operion local gateway CA")]
    )
    ca = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(False, False, False, False, False, True, True, None, None),
            critical=True,
        )
        .sign(ca_key, hashes.SHA256())
    )
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    cert = (
        x509.CertificateBuilder()
        .subject_name(
            x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "operion.localhost")])
        )
        .issuer_name(ca_name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=30))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("operion.localhost")]),
            critical=False,
        )
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    write_secret(
        RUNTIME / "tls/ca.crt", ca.public_bytes(serialization.Encoding.PEM), mode=0o644
    )
    write_secret(
        RUNTIME / "tls/server.crt",
        cert.public_bytes(serialization.Encoding.PEM),
        mode=0o644,
    )
    write_secret(
        RUNTIME / "tls/server.key",
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
    )
    # No need to retain the CA signing key. Re-initialization requires a new stack.


def compose(*args: str) -> None:
    subprocess.run(
        ["docker", "compose", "-f", str(ROOT / "deploy/gateway/compose.yaml"), *args],
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["init", "up", "stop", "status"])
    args = parser.parse_args()
    if args.command == "init":
        initialize()
    elif args.command == "up":
        if not (RUNTIME / "realm.json").is_file():
            raise SystemExit("Run init first")
        compose("up", "-d", "--build")
    elif args.command == "stop":
        compose("stop")
    else:
        compose("ps")


if __name__ == "__main__":
    main()
