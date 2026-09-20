from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from operion_etl.enterprise_auth import (
    AuthenticationError,
    AuthorizationError,
    IdentityPolicy,
    JwksFileKeyResolver,
    OIDCAuthenticator,
)


class EnterpriseAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.private_key = rsa.generate_private_key(
            public_exponent=65537, key_size=2048
        )
        jwk = jwt.algorithms.RSAAlgorithm.to_jwk(
            self.private_key.public_key(), as_dict=True
        )
        jwk.update({"kid": "test-key", "use": "sig", "alg": "RS256"})
        self.jwks_path = root / "jwks.json"
        self.jwks_path.write_text(json.dumps({"keys": [jwk]}), encoding="utf-8")
        self.policy_path = root / "identity-policy.json"
        self.policy = {
            "schema_version": "operion-identity-policy-v1",
            "policy_version": 1,
            "revoked_sessions": [],
            "users": {
                "subject-1": {
                    "active": True,
                    "valid_after": 0,
                    "user_id": "alice",
                    "tenant_id": "tenant-1",
                    "companies": ["AI Demo GmbH"],
                    "customer_ids": ["customer-1"],
                    "roles": ["agent_read", "action_reader"],
                }
            },
        }
        self._write_policy()
        self.authenticator = OIDCAuthenticator(
            issuer="https://identity.example.test",
            audience="operion",
            algorithms=("RS256",),
            key_resolver=JwksFileKeyResolver(self.jwks_path),
            policy=IdentityPolicy(self.policy_path),
            leeway_seconds=0,
        )

    def tearDown(self):
        self.temp.cleanup()

    def _write_policy(self):
        self.policy_path.write_text(json.dumps(self.policy), encoding="utf-8")
        current = self.policy_path.stat().st_mtime_ns
        os.utime(self.policy_path, ns=(current + 1, current + 1))

    def _token(self, **overrides):
        now = datetime.now(UTC)
        claims = {
            "iss": "https://identity.example.test",
            "aud": "operion",
            "sub": "subject-1",
            "sid": "session-1",
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "tenant_id": "attacker-controlled",
            "roles": ["action_approver"],
        }
        claims.update(overrides)
        return jwt.encode(
            claims,
            self.private_key,
            algorithm="RS256",
            headers={"kid": "test-key"},
        )

    def test_signature_claims_and_server_policy_define_identity(self):
        identity = self.authenticator.authenticate(f"Bearer {self._token()}")
        self.assertEqual("tenant-1", identity.tenant_id)
        self.assertEqual(frozenset({"agent_read", "action_reader"}), identity.roles)
        self.assertNotIn("action_approver", identity.roles)
        with self.assertRaises(AuthenticationError):
            self.authenticator.authenticate(
                f"Bearer {self._token(aud='another-service')}"
            )

    def test_policy_reload_revokes_session_and_user(self):
        token = self._token()
        self.authenticator.authenticate(f"Bearer {token}")
        self.policy["revoked_sessions"] = ["session-1"]
        self._write_policy()
        with self.assertRaises(AuthenticationError):
            self.authenticator.authenticate(f"Bearer {token}")

        self.policy["revoked_sessions"] = []
        self.policy["users"]["subject-1"]["active"] = False
        self._write_policy()
        with self.assertRaises(AuthorizationError):
            self.authenticator.authenticate(f"Bearer {token}")

    def test_symmetric_algorithms_and_missing_session_are_rejected(self):
        with self.assertRaises(RuntimeError):
            OIDCAuthenticator(
                issuer="issuer",
                audience="audience",
                algorithms=("HS256",),
                key_resolver=JwksFileKeyResolver(self.jwks_path),
                policy=IdentityPolicy(self.policy_path),
            )
        with self.assertRaises(AuthenticationError):
            self.authenticator.authenticate(f"Bearer {self._token(sid=None, jti=None)}")


if __name__ == "__main__":
    unittest.main()
