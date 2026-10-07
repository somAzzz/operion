#!/usr/bin/env python3
"""Protocol acceptance of the isolated gateway; no browser click claims.

Runs against only scripts/gateway.py's local realm and synthetic test users.
Does not print passwords, authorization codes, tokens, or session cookies.
"""

from __future__ import annotations

import argparse
import copy
import http.cookiejar
import json
import socket
import ssl
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "var/gateway"
ORIGIN = "https://operion.localhost:8443"
POLICY = RUNTIME / "policy/identity-policy.json"
ALICE = "10000000-0000-4000-8000-000000000001"
COOKIE = "__Host-operion_session"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class LoginForm(HTMLParser):
    def __init__(self):
        super().__init__()
        self.action = None

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "form" and values.get("id") == "kc-form-login":
            self.action = values["action"]


class Client:
    def __init__(self, ca: Path):
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPSHandler(
                context=ssl.create_default_context(cafile=str(ca))
            ),
            urllib.request.HTTPCookieProcessor(self.jar),
            NoRedirect(),
        )

    def request(self, path, *, method="GET", data=None, headers=None):
        url = urllib.parse.urljoin(ORIGIN, path)
        if urllib.parse.urlsplit(url).netloc != "operion.localhost:8443":
            raise RuntimeError("acceptance client refuses external redirects")
        req = urllib.request.Request(
            url, method=method, data=data, headers=headers or {}
        )
        try:
            response = self.opener.open(req, timeout=130)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, response.headers, response.read()

    def login(self, username, password):
        status, headers, body = self.request("/oauth2/start?rd=%2F")
        assert status == 302, "login did not start"
        authorize = headers["Location"]
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(authorize).query)
        assert query.get("code_challenge_method") == ["S256"], "PKCE missing"
        assert query.get("nonce") and query.get("state"), "nonce/state missing"
        status, headers, body = self.request(authorize)
        assert status == 200, "identity provider unavailable"
        form = LoginForm()
        form.feed(body.decode())
        assert form.action, "login form missing"
        status, headers, body = self.request(
            form.action,
            method="POST",
            data=urllib.parse.urlencode(
                {"username": username, "password": password, "credentialId": ""}
            ).encode(),
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": ORIGIN,
            },
        )
        assert status == 302, "credentials were not accepted"
        callback = headers["Location"]
        # A separate browser without the login CSRF cookie must fail closed.
        missing_cookie = Client(RUNTIME / "tls/ca.crt").request(callback)[0]
        assert missing_cookie == 403, "callback accepted without state cookie"
        status, headers, body = self.request(callback)
        assert status == 302, "OIDC callback failed"
        assert any(c.name == COOKIE for c in self.jar), "gateway session missing"
        return callback


def compose_output(*args):
    return subprocess.check_output(
        ["docker", "compose", "-f", str(ROOT / "deploy/gateway/compose.yaml"), *args],
        text=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--model", action="store_true", help="Also exercise a real scoped Agent query"
    )
    args = parser.parse_args()
    # Local DNS override for this process only; TLS still validates hostname/CA.
    original_resolver = socket.getaddrinfo
    socket.getaddrinfo = lambda host, *a, **kw: original_resolver(
        "127.0.0.1" if host == "operion.localhost" else host, *a, **kw
    )
    results = []
    started = datetime.now(UTC).isoformat()

    def check(name, predicate):
        results.append({"case": name, "passed": bool(predicate)})
        assert predicate, name
        print("PASS", name, flush=True)

    def client():
        return Client(RUNTIME / "tls/ca.crt")

    def set_policy(value):
        temporary = POLICY.with_suffix(".tmp")
        temporary.write_text(json.dumps(value))
        temporary.chmod(0o600)
        temporary.replace(POLICY)

    original_policy = json.loads(POLICY.read_text())
    failure = None
    try:
        anonymous = client()
        for attempt in range(90):
            try:
                ready = anonymous.request("/")[0] == 302
            except (OSError, urllib.error.URLError):
                ready = False
            if ready:
                break
            time.sleep(1)
        check("anonymous-page-redirect", ready)
        check("anonymous-api-401", anonymous.request("/api/conversations")[0] == 401)
        check(
            "forged-forwarding-headers-denied",
            anonymous.request(
                "/api/conversations",
                headers={
                    "X-Forwarded-Access-Token": "forged",
                    "Authorization": "Bearer forged",
                    "X-Forwarded-User": "alice",
                    "X-Middleware-Subrequest": "proxy:proxy:proxy:proxy:proxy",
                },
            )[0]
            == 401,
        )
        check(
            "browser-token-cookie-not-accepted",
            anonymous.request(
                "/api/conversations", headers={"Cookie": "operion_access_token=forged"}
            )[0]
            == 401,
        )
        check("admin-not-public", anonymous.request("/identity/admin/")[0] == 404)
        check(
            "wrong-host-denied",
            anonymous.request("/", headers={"Host": "evil.example"})[0] == 421,
        )
        config = json.loads(compose_output("config", "--format", "json"))
        published = {
            name for name, service in config["services"].items() if service.get("ports")
        }
        check(
            "only-loopback-ingress-published",
            published == {"ingress"}
            and all(
                port["host_ip"] == "127.0.0.1"
                for port in config["services"]["ingress"]["ports"]
            ),
        )
        running = json.loads(
            subprocess.check_output(
                ["docker", "inspect", *compose_output("ps", "-q").split()], text=True
            )
        )
        check(
            "runtime-ports-match-isolation",
            all(
                not container["HostConfig"]["PortBindings"]
                or (
                    container["Config"]["Labels"]["com.docker.compose.service"]
                    == "ingress"
                    and all(
                        binding["HostIp"] == "127.0.0.1"
                        for bindings in container["HostConfig"]["PortBindings"].values()
                        for binding in bindings
                    )
                )
                for container in running
            ),
        )
        # Probe private services from inside the trusted network: even a direct
        # request with forged forwarding headers cannot impersonate a user.
        boundary = json.loads(
            compose_output(
                "exec",
                "-T",
                "agent",
                "python",
                "-c",
                """
import json, urllib.request, urllib.error
results = []
for url, headers in [
    ("http://web:3000/", {}),
    ("http://web:3000/", {"X-Forwarded-Access-Token": "forged"}),
    ("http://agent:8000/api/identity", {"X-Forwarded-Access-Token": "forged"}),
    ("http://agent:8000/api/identity", {"Authorization": "Bearer forged"}),
]:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=10) as r:
            results.append(r.status)
    except urllib.error.HTTPError as e:
        results.append(e.code)
print(json.dumps(results))
""",
            )
        )
        for name, status in zip(
            [
                "private-web-requires-auth",
                "private-web-verifies-forwarded-token",
                "private-agent-rejects-forwarding-header",
                "private-agent-rejects-forged-token",
            ],
            boundary,
            strict=True,
        ):
            check(name, status == 401)
        passwords = json.loads((RUNTIME / "credentials.json").read_text())
        alice = client()
        callback = alice.login("alice", passwords["alice"])
        check("authorization-code-pkce-state-nonce", True)
        check("callback-replay-denied", alice.request(callback)[0] in {400, 403})
        cookie = next(c for c in alice.jar if c.name == COOKIE)
        check(
            "secure-httponly-samesite-cookie",
            cookie.secure
            and cookie.has_nonstandard_attr("HttpOnly")
            and cookie.get_nonstandard_attr("SameSite", "").lower() == "lax"
            and cookie.path == "/"
            and not cookie.domain_specified,
        )
        status, headers, body = alice.request("/")
        check("authenticated-web-page", status == 200 and b"Evidence desk" in body)
        check("responses-not-cached", "no-store" in headers.get("Cache-Control", ""))
        check(
            "tokens-not-rendered",
            b"access_token" not in body and b"refresh_token" not in body,
        )
        check("authorized-api", alice.request("/api/conversations")[0] == 200)
        check(
            "forged-token-overwritten-after-login",
            alice.request(
                "/api/conversations", headers={"X-Forwarded-Access-Token": "forged"}
            )[0]
            == 200,
        )
        check(
            "cross-origin-mutation-denied",
            alice.request(
                "/api/agent",
                method="POST",
                data=b"{}",
                headers={"Origin": "https://evil.example"},
            )[0]
            == 403,
        )
        check(
            "missing-origin-mutation-denied",
            alice.request("/api/agent", method="POST", data=b"{}")[0] == 403,
        )
        check("logout-get-denied", alice.request("/oauth2/sign_out")[0] == 405)
        check(
            "logout-cross-origin-denied",
            alice.request(
                "/oauth2/sign_out",
                method="POST",
                data=b"",
                headers={"Origin": "https://evil.example"},
            )[0]
            == 403,
        )
        unassigned = client()
        unassigned.login("unassigned", passwords["unassigned"])
        check("valid-idp-user-without-policy-denied", unassigned.request("/")[0] == 403)
        changed = copy.deepcopy(original_policy)
        changed["users"][ALICE]["active"] = False
        set_policy(changed)
        check("disabled-user-page-denied", alice.request("/")[0] == 403)
        check("disabled-user-api-denied", alice.request("/api/conversations")[0] == 403)
        set_policy(original_policy)
        check(
            "policy-restore-without-restart",
            alice.request("/api/conversations")[0] == 200,
        )
        changed = copy.deepcopy(original_policy)
        changed["users"][ALICE]["roles"] = ["action_approver"]
        set_policy(changed)
        check(
            "wrong-application-role-denied",
            alice.request("/api/conversations")[0] == 403,
        )
        set_policy(original_policy)
        changed = copy.deepcopy(original_policy)
        changed["users"][ALICE]["valid_after"] = int(time.time()) + 60
        set_policy(changed)
        check("old-login-revoked", alice.request("/api/conversations")[0] == 401)
        set_policy(original_policy)
        if args.model:
            run_agent_cases(alice, passwords, client, check)
        replay = client()
        replay.jar.set_cookie(copy.copy(cookie))
        status, headers, body = alice.request(
            "/oauth2/sign_out", method="POST", data=b"", headers={"Origin": ORIGIN}
        )
        check(
            "same-origin-logout",
            status == 302 and headers.get("Location") == "/signed-out",
        )
        check(
            "logout-clears-browser-session",
            alice.request("/api/conversations")[0] == 401,
        )
        check(
            "logout-deletes-server-session",
            replay.request("/api/conversations")[0] == 401,
        )
        check("signed-out-page", alice.request("/signed-out")[0] == 200)
        silent_url = (
            "/identity/realms/operion/protocol/openid-connect/auth?"
            + urllib.parse.urlencode(
                {
                    "client_id": "operion",
                    "redirect_uri": ORIGIN + "/oauth2/callback",
                    "response_type": "code",
                    "scope": "openid",
                    "prompt": "none",
                    "state": "logout-probe",
                    "nonce": "logout-probe",
                    "code_challenge_method": "S256",
                    "code_challenge": "A" * 43,
                }
            )
        )
        status, headers, body = alice.request(silent_url)
        check(
            "logout-ends-keycloak-session",
            status == 302
            and urllib.parse.parse_qs(
                urllib.parse.urlsplit(headers.get("Location", "")).query
            ).get("error")
            == ["login_required"],
        )
    except Exception as error:
        # Do not emit exception strings that might contain OAuth URLs or cookies.
        failure = type(error).__name__
        results.append(
            {"case": "acceptance-interrupted", "passed": False, "error_type": failure}
        )
        print("FAIL", failure, "after", len(results) - 1, "checks")
    finally:
        set_policy(original_policy)
        socket.getaddrinfo = original_resolver
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(
                {
                    "status": "failed" if failure else "passed",
                    "started_at": started,
                    "completed_at": datetime.now(UTC).isoformat(),
                    "scope": "local_keycloak_public_sample_protocol_acceptance",
                    "browser_clicks": "not_run_no_available_browser",
                    "model_cases": args.model,
                    "results": results,
                },
                indent=2,
            )
            + "\n"
        )
    if failure:
        raise SystemExit(1)


def run_agent_cases(alice, passwords, client, check):
    import uuid

    thread = "gateway-" + str(uuid.uuid4())
    payload = {
        "threadId": thread,
        "runId": str(uuid.uuid4()),
        "state": {},
        "context": [],
        "forwardedProps": {},
        "tools": [],
        "messages": [
            {
                "id": str(uuid.uuid4()),
                "role": "user",
                "content": "概览客户 wwi:organization:customer:65，说明数据来源和订单数量。",
            }
        ],
    }
    status, headers, body = alice.request(
        "/api/agent",
        method="POST",
        data=json.dumps(payload).encode(),
        headers={"Origin": ORIGIN, "Content-Type": "application/json"},
    )
    check(
        "real-agent-through-gateway",
        status == 200 and b'"RUN_FINISHED"' in body and b'"RUN_ERROR"' not in body,
    )
    check(
        "alice-can-read-own-history",
        alice.request(f"/api/conversations/{thread}")[0] == 200,
    )
    bob = client()
    bob.login("bob", passwords["bob"])
    check(
        "bob-cannot-read-alice-history",
        bob.request(f"/api/conversations/{thread}")[0] in {403, 404},
    )


if __name__ == "__main__":
    main()
