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

test("SSR and hydration input omit action anchors for agent and proposer roles", async () => {
  for (const role of ["agent", "proposer"]) {
    const result = await page(role);
    assert.equal(result.status, 200, serverLog);
    assert.ok(!result.hrefs.includes("/actions"));
    assert.ok(!result.hrefs.includes("/approvals"));
    assert.ok(result.html.includes("New inquiry"));
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
