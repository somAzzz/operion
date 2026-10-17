import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { test } from "node:test";

async function sessionModule() {
  const url = new URL("../lib/session-fetch.ts", import.meta.url);
  url.searchParams.set("test", randomUUID());
  return import(url.href);
}

function browser(t, pathname = "/") {
  const previous = Object.getOwnPropertyDescriptor(globalThis, "window");
  const navigations = [];
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: {
      location: { pathname, replace: (url) => navigations.push(url) },
      get localStorage() { throw new Error("Session expiry must preserve conversation storage"); },
    },
  });
  t.after(() => previous
    ? Object.defineProperty(globalThis, "window", previous)
    : delete globalThis.window);
  return navigations;
}

test("concurrent history and agent 401s navigate once to the fixed login URL", async (t) => {
  const navigations = browser(t);
  t.mock.method(globalThis, "fetch", async () => new Response("{}", { status: 401 }));
  const { fetchWithSession, SESSION_EXPIRED_MESSAGE } = await sessionModule();
  const results = await Promise.allSettled([
    fetchWithSession("/api/conversations"),
    fetchWithSession("/api/agent", { method: "POST", body: "question" }),
  ]);
  assert.deepEqual(navigations, ["/login?reason=session_expired"]);
  assert.ok(results.every((r) => r.status === "rejected" && r.reason.message === SESSION_EXPIRED_MESSAGE));
  assert.equal(globalThis.fetch.mock.callCount(), 2); // No automatic POST replay.
});

test("401 invokes the workspace transition callback before rejecting", async (t) => {
  t.mock.method(globalThis, "fetch", async () => new Response("", { status: 401 }));
  const { fetchWithSession } = await sessionModule();
  let transitioned = false;
  await assert.rejects(fetchWithSession("/api/conversations", undefined, () => { transitioned = true; }));
  assert.equal(transitioned, true);
});

test("403 policy denial remains an application response and never redirects", async (t) => {
  const navigations = browser(t);
  const response = new Response("Forbidden", { status: 403 });
  t.mock.method(globalThis, "fetch", async () => response);
  const { fetchWithSession } = await sessionModule();
  assert.equal(await fetchWithSession("/api/actions"), response);
  assert.deepEqual(navigations, []);
});

test("successful streaming response and request options pass through unchanged", async (t) => {
  const response = new Response("data: verified\n\n", { headers: { "Content-Type": "text/event-stream" } });
  const mock = t.mock.method(globalThis, "fetch", async () => response);
  const { fetchWithSession } = await sessionModule();
  const init = { method: "POST", body: "question", headers: { Accept: "text/event-stream" } };
  assert.equal(await fetchWithSession("/api/agent", init), response);
  assert.deepEqual(mock.mock.calls[0].arguments, ["/api/agent", init]);
});

test("network errors do not claim that the session expired", async (t) => {
  const navigations = browser(t);
  const error = new TypeError("Network unavailable");
  t.mock.method(globalThis, "fetch", async () => { throw error; });
  const { fetchWithSession } = await sessionModule();
  await assert.rejects(fetchWithSession("/api/conversations"), (actual) => actual === error);
  assert.deepEqual(navigations, []);
});

test("login page cannot redirect to itself on a stray 401", async (t) => {
  const navigations = browser(t, "/login");
  t.mock.method(globalThis, "fetch", async () => new Response("", { status: 401 }));
  const { fetchWithSession } = await sessionModule();
  await assert.rejects(fetchWithSession("/api/conversations"));
  assert.deepEqual(navigations, []);
});
