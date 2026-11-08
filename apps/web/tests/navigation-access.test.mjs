import assert from "node:assert/strict";
import { test } from "node:test";
import { navigationAccess } from "../lib/navigation-access.ts";

import { orderMentions, remarkOrderMentions } from "../lib/order-mentions.ts";

test("sales order numbers link inline without turning invoices, quantities or purchase orders into sales links", () => {
  const text = "Order 66823: 48 units. Invoice 33513, purchase order 1904, order line 210128. WWI sales order #31349.";
  const parts = orderMentions(text);
  assert.equal(parts.map(p => p.type === "text" ? p.value : p.children[0].value).join(""), text);
  assert.deepEqual(parts.filter(p => p.type === "link").map(p => p.url), ["/orders/66823?open=erpnext", "/orders/31349?open=erpnext"]);
  const raw = "wwi:sales_order:66823";
  const existing = { type: "link", url: "/orders/66823", children: [{ type: "text", value: raw }] };
  const code = { type: "inlineCode", value: raw };
  const tree = { type: "root", children: [{ type: "paragraph", children: [{ type: "text", value: raw }, existing, code] }] };
  remarkOrderMentions()(tree);
  const children = tree.children[0].children;
  assert.equal(children[1].url, "/orders/66823?open=erpnext");
  assert.deepEqual(children.slice(2), [existing, code]);
  assert.equal(existing.children.length, 1);
});

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
