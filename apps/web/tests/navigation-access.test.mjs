import assert from "node:assert/strict";
import { test } from "node:test";
import { navigationAccess } from "../lib/navigation-access.ts";

const none = { evidence: false, actions: false, approvals: false };

test("agent-only and proposer-only users have no action navigation", () => {
  assert.deepEqual(navigationAccess(["agent_read"]), { ...none, evidence: true });
  assert.deepEqual(navigationAccess(["agent_read", "followup_proposer"]), { ...none, evidence: true });
  assert.deepEqual(navigationAccess(["followup_proposer"]), none);
});

for (const role of ["action_reader", "action_approver", "action_operator"]) {
  test(`${role} can view the action pages under the existing backend policy`, () => {
    assert.deepEqual(navigationAccess([role]), { evidence: false, actions: true, approvals: true });
    assert.deepEqual(navigationAccess([role, "agent_read"]), { evidence: true, actions: true, approvals: true });
  });
}

test("missing, malformed, and invented roles fail closed", () => {
  for (const value of [null, undefined, {}, "action_reader", [], ["admin"], ["ACTION_READER"], ["action_reader "]]) {
    assert.deepEqual(navigationAccess(value), none);
  }
  assert.deepEqual(navigationAccess([{}, 123, true]), none);
});

test("role removal and consecutive users do not reuse earlier privileges", () => {
  const roles = ["agent_read", "action_reader"];
  assert.equal(navigationAccess(roles).actions, true);
  roles.pop();
  assert.equal(navigationAccess(roles).actions, false);
  assert.deepEqual(navigationAccess([]), none);
});
