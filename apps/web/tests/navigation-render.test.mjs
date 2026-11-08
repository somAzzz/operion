/** Exercise the production Next server with isolated synthetic identity data. */
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { createServer } from "node:http";
import { setTimeout as delay } from "node:timers/promises";
import { after, before, test } from "node:test";

const identities = {
  agent: ["agent_read"],
  proposer: ["agent_read", "followup_proposer"],
  reader: ["agent_read", "action_reader"],
  approver: ["agent_read", "action_approver"],
  operator: ["agent_read", "action_operator"],
  "action-only": ["action_reader"],
  "layout-outage": ["agent_read", "action_reader"],
};
let child;
let server;
let serverLog = "";
let outageReads = 0;
const origin = "http://127.0.0.1:34567";

before(async () => {
  server = createServer((request, response) => {
    const user = request.headers.authorization?.replace("Bearer nav-test-", "");
    if (request.method !== "GET" || !identities[user]) {
      response.writeHead(401).end();
      return;
    }
    const path = new URL(request.url, "http://localhost").pathname;
    response.setHeader("Content-Type", "application/json");
    if (path === "/api/identity") {
      if (user === "layout-outage" && ++outageReads > 1) {
        response.writeHead(503).end("{}");
        return;
      }
      response.end(JSON.stringify({ roles: identities[user] }));
    } else if (path === "/api/orders/66823/records" && request.url.endsWith("?erp_only=true")) {
      const sales_order = user === "reader" ? { status: "verified", id: "SO 16" } : { status: "no_match" };
      response.end(JSON.stringify({ sales_order }));
    } else if (path === "/api/orders/66823/records") {
      response.end(JSON.stringify({ person: {
        status: "verified", id: "00000000-0000-4000-a000-000000000001", label: "Order contact",
      } }));
    } else if (path === "/api/actions") {
      response.end(JSON.stringify({ actions: [] }));
    } else {
      response.writeHead(404).end("{}");
    }
  });
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const backend = `http://127.0.0.1:${server.address().port}/api`;
  child = spawn(process.execPath, [".next/standalone/server.js"], {
    env: {
      ...process.env, HOSTNAME: "127.0.0.1", PORT: "34567", NODE_ENV: "production",
      OPERION_ENVIRONMENT: "enterprise", OPERION_OTEL_ENABLED: "0",
      OPERION_PUBLIC_ORIGIN: "https://operion.localhost:8443",
      OPERION_TWENTY_WEB_URL: "https://crm.example.test",
      OPERION_ERPNEXT_WEB_URL: "https://erp.example.test",
      OPERION_AGENT_URL: `${backend}/agent`, OPERION_ACTION_URL: backend,
    },
    stdio: ["ignore", "pipe", "pipe"],
  });
  const collect = (data) => { serverLog = (serverLog + data).slice(-6000); };
  child.stdout.on("data", collect);
  child.stderr.on("data", collect);
  for (let attempt = 0; attempt < 150; attempt++) {
    if (child.exitCode !== null) throw new Error(serverLog);
    try {
      if ((await fetch(`${origin}/health`)).ok) return;
    } catch { /* The server is starting. */ }
    await delay(100);
  }
  throw new Error(`Next server did not become ready: ${serverLog}`);
});

after(async () => {
  if (child && child.exitCode === null) {
    const exited = once(child, "exit");
    child.kill("SIGTERM");
    await exited;
  }
  if (server) {
    server.closeAllConnections();
    await new Promise((resolve) => server.close(resolve));
  }
});

async function page(user, path = "/") {
  const response = await fetch(`${origin}${path}`, {
    headers: { "X-Forwarded-Access-Token": `nav-test-${user}` },
    redirect: "manual",
  });
  const html = await response.text();
  assert.ok(!html.includes(`nav-test-${user}`), "Forwarded token must never reach HTML");
  return { status: response.status, html, hrefs: [...html.matchAll(/<a\b[^>]*\bhref="([^"]+)"/g)].map((m) => m[1]) };
}

test("anonymous login renders English and preserves the fixed return target", async () => {
  for (const expired of [false, true]) {
    const response = await fetch(`${origin}/login${expired ? "?reason=session_expired" : ""}`);
    const html = await response.text();
    assert.equal(response.status, 200);
    assert.ok(html.includes('<main class="login-page" lang="en">'));
    assert.ok(html.includes(expired ? "Sign in to Operion again" : "Sign in to Operion"));
    assert.equal(html.includes("Your session has expired or is no longer valid."), expired);
    assert.ok(html.includes('action="/oauth2/start"'));
    assert.ok(html.includes('name="rd" value="/"'));
    assert.ok(!html.includes("Message input"));
  }
});

test("SSR and hydration input omit action anchors for agent and proposer roles", async () => {
  for (const role of ["agent", "proposer"]) {
    const result = await page(role);
    assert.equal(result.status, 200, serverLog);
    assert.ok(!result.hrefs.includes("/actions"));
    assert.ok(!result.hrefs.includes("/approvals"));
    assert.ok(result.html.includes("New inquiry"));
  }
});

test("shared navigation links directly to complaints and identifies the active workspace", async () => {
  for (const path of ["/", "/complaints", "/actions", "/approvals"]) {
    const result = await page("reader", path);
    assert.equal(result.status, 200);
    const nav = result.html.match(/<nav aria-label="Workspace">([\s\S]*?)<\/nav>/)?.[1] ?? "";
    const links = [...nav.matchAll(/<a\b[^>]*>/g)].map(([tag]) => tag);
    assert.ok(links.some(tag => tag.includes('href="/complaints"')));
    const active = links.filter(tag => tag.includes('aria-current="page"'));
    assert.equal(active.length, 1);
    assert.ok(active[0].includes(`href="${path}"`));
  }
});

for (const role of ["reader", "approver", "operator"]) {
  test(`${role} receives authorized links on both workspace and action shell`, async () => {
    for (const path of ["/", "/actions", "/approvals"]) {
      const result = await page(role, path);
      assert.equal(result.status, 200, serverLog);
      assert.ok(result.hrefs.includes("/actions"), path);
      assert.ok(result.hrefs.includes("/approvals"), path);
    }
  });
}

test("action-only users do not receive a forbidden Evidence desk link", async () => {
  const result = await page("action-only", "/actions");
  assert.equal(result.status, 200);
  assert.ok(!result.hrefs.includes("/"));
  assert.ok(!result.hrefs.includes("/complaints"));
  assert.ok(result.hrefs.includes("/actions"));
});

test("an identity lookup failure in the layout hides navigation", async () => {
  const result = await page("layout-outage");
  assert.equal(result.status, 200);
  assert.ok(!result.hrefs.includes("/actions"));
  assert.ok(!result.hrefs.includes("/approvals"));
});

test("a privileged render does not leak navigation to the next read-only user", async () => {
  assert.ok((await page("reader")).hrefs.includes("/actions"));
  const result = await page("agent");
  assert.ok(!result.hrefs.includes("/actions"));
  assert.ok(!result.hrefs.includes("/approvals"));
});

test("existing page guards still reject direct and RSC requests without roles", async () => {
  for (const path of ["/actions", "/approvals", "/actions?_rsc=nav-regression"]) {
    assert.equal((await page("agent", path)).status, 403, path);
  }
});

test("inline order numbers open the verified native ERPNext form for the current user", async () => {
  const path = "/orders/66823?open=erpnext";
  const response = await fetch(origin + path, {
    headers: { "X-Forwarded-Access-Token": "nav-test-reader" }, redirect: "manual",
  });
  assert.equal(response.status, 307);
  assert.equal(response.headers.get("location"), "https://erp.example.test/desk/sales-order/SO%2016");
  const missing = await page("agent", path);
  assert.ok(missing.html.includes("No matching ERPNext order"));
  assert.ok(!missing.html.includes("erp.example.test"));
  assert.equal((await page("action-only", path)).status, 403);
});

test("CRM deep links recheck the exact record and the current reader", async () => {
  const id = "00000000-0000-4000-a000-000000000001";
  const path = "/orders/66823?open=person&record=";
  const response = await fetch(origin + path + id, {
    headers: { "X-Forwarded-Access-Token": "nav-test-reader" }, redirect: "manual",
  });
  assert.equal(response.status, 307);
  assert.equal(response.headers.get("location"), "https://crm.example.test/object/person/" + id);
  assert.ok((await page("reader", path + id.replace(/1$/, "2"))).html.includes("This CRM link could not be opened"));
  assert.equal((await page("action-only", path + id)).status, 403);
});
