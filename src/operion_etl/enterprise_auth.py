from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any, Protocol

import jwt


class AuthenticationError(RuntimeError):
    pass


class AuthorizationError(RuntimeError):
    pass


@dataclass(frozen=True)
class EnterpriseIdentity:
    user_id: str
    tenant_id: str
    operating_company: str
    customer_ids: frozenset[str]
    roles: frozenset[str]
    subject: str
    session_id: str

    def require(self, *allowed_roles: str) -> None:
        if not self.roles.intersection(allowed_roles):
            raise AuthorizationError("identity is not authorized for this operation")


class TokenKeyResolver(Protocol):
    def resolve(self, token: str) -> Any: ...


class JwksUrlKeyResolver:
    def __init__(self, url: str) -> None:
        self.client = jwt.PyJWKClient(url, cache_keys=True, max_cached_keys=16)

    def resolve(self, token: str) -> Any:
        return self.client.get_signing_key_from_jwt(token).key


class JwksFileKeyResolver:
    """Local JWKS resolver for offline deployments and deterministic drills."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def resolve(self, token: str) -> Any:
        try:
            kid = jwt.get_unverified_header(token)["kid"]
            document = json.loads(self.path.read_text(encoding="utf-8"))
            matches = [item for item in document["keys"] if item.get("kid") == kid]
            if len(matches) != 1:
                raise AuthenticationError("token signing key is unavailable")
            return jwt.PyJWK.from_dict(matches[0]).key
        except AuthenticationError:
            raise
        except Exception as error:
            raise AuthenticationError("token signing key is unavailable") from error


class IdentityPolicy:
    """Reloadable server-side scope and revocation policy.

    JWT claims prove the login. They never grant tenant, company, customer, or
    application roles; those are loaded from this server-controlled document on
    every request, with an mtime cache for inexpensive revocation checks.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = Lock()
        self._mtime_ns = -1
        self._document: dict[str, Any] = {}

    def _load(self) -> dict[str, Any]:
        try:
            mtime_ns = self.path.stat().st_mtime_ns
            with self._lock:
                if mtime_ns != self._mtime_ns:
                    document = json.loads(self.path.read_text(encoding="utf-8"))
                    if document.get("schema_version") != "operion-identity-policy-v1":
                        raise AuthorizationError("unsupported identity policy")
                    if not isinstance(document.get("users"), dict):
                        raise AuthorizationError("identity policy has no users")
                    self._document = document
                    self._mtime_ns = mtime_ns
                return self._document
        except AuthorizationError:
            raise
        except Exception as error:
            raise AuthorizationError("identity policy is unavailable") from error

    def resolve(self, claims: dict[str, Any]) -> EnterpriseIdentity:
        document = self._load()
        subject = str(claims["sub"])
        session_id = str(claims.get("sid") or claims.get("jti") or "")
        if not session_id:
            raise AuthenticationError("token has no revocable session identifier")
        if session_id in set(document.get("revoked_sessions", [])):
            raise AuthenticationError("session has been revoked")
        user = document["users"].get(subject)
        if not isinstance(user, dict) or not user.get("active", False):
            raise AuthorizationError("user is not active")
        valid_after = int(user.get("valid_after", 0))
        if int(claims["iat"]) < valid_after:
            raise AuthenticationError("token predates the current access policy")
        companies = user.get("companies", [])
        if len(companies) != 1:
            raise AuthorizationError("pilot users require exactly one company")
        customer_ids = frozenset(str(item) for item in user.get("customer_ids", []))
        if not customer_ids:
            raise AuthorizationError("user has no customer scope")
        roles = frozenset(str(item) for item in user.get("roles", []))
        allowed_roles = {
            "agent_read",
            "followup_proposer",
            "action_reader",
            "action_approver",
            "action_operator",
        }
        if not roles or not roles <= allowed_roles:
            raise AuthorizationError("user has invalid application roles")
        return EnterpriseIdentity(
            user_id=str(user["user_id"]),
            tenant_id=str(user["tenant_id"]),
            operating_company=str(companies[0]),
            customer_ids=customer_ids,
            roles=roles,
            subject=subject,
            session_id=session_id,
        )


class OIDCAuthenticator:
    def __init__(
        self,
        *,
        issuer: str,
        audience: str,
        algorithms: tuple[str, ...],
        key_resolver: TokenKeyResolver,
        policy: IdentityPolicy,
        leeway_seconds: int = 30,
    ) -> None:
        allowed = {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512"}
        if not algorithms or not set(algorithms) <= allowed:
            raise RuntimeError(
                "OIDC algorithms must be an explicit asymmetric allowlist"
            )
        self.issuer = issuer
        self.audience = audience
        self.algorithms = algorithms
        self.key_resolver = key_resolver
        self.policy = policy
        self.leeway_seconds = leeway_seconds

    def authenticate(self, authorization: str) -> EnterpriseIdentity:
        if not authorization.startswith("Bearer "):
            raise AuthenticationError("bearer token is required")
        token = authorization.removeprefix("Bearer ").strip()
        if not token or len(token) > 16_384:
            raise AuthenticationError("bearer token is invalid")
        try:
            claims = jwt.decode(
                token,
                self.key_resolver.resolve(token),
                algorithms=list(self.algorithms),
                audience=self.audience,
                issuer=self.issuer,
                leeway=self.leeway_seconds,
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )
        except AuthenticationError:
            raise
        except jwt.PyJWTError as error:
            raise AuthenticationError("bearer token validation failed") from error
        return self.policy.resolve(claims)

    @classmethod
    def from_environment(cls) -> OIDCAuthenticator:
        issuer = os.environ.get("OPERION_OIDC_ISSUER", "").rstrip("/")
        audience = os.environ.get("OPERION_OIDC_AUDIENCE", "")
        policy_path = os.environ.get("OPERION_IDENTITY_POLICY", "")
        jwks_url = os.environ.get("OPERION_OIDC_JWKS_URL", "")
        jwks_file = os.environ.get("OPERION_OIDC_JWKS_FILE", "")
        if not issuer or not audience or not policy_path:
            raise RuntimeError(
                "enterprise auth requires OIDC issuer, audience, and identity policy"
            )
        if bool(jwks_url) == bool(jwks_file):
            raise RuntimeError("configure exactly one OIDC JWKS URL or file")
        resolver: TokenKeyResolver = (
            JwksUrlKeyResolver(jwks_url)
            if jwks_url
            else JwksFileKeyResolver(Path(jwks_file))
        )
        algorithms = tuple(
            item.strip()
            for item in os.environ.get("OPERION_OIDC_ALGORITHMS", "RS256").split(",")
            if item.strip()
        )
        return cls(
            issuer=issuer,
            audience=audience,
            algorithms=algorithms,
            key_resolver=resolver,
            policy=IdentityPolicy(Path(policy_path)),
            leeway_seconds=int(os.environ.get("OPERION_OIDC_LEEWAY_SECONDS", "30")),
        )
