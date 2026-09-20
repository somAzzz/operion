from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid5

from .action_models import (
    FOLLOWUP_SIDE_EFFECTS,
    Principal,
    ProposalRequest,
)
from .action_store import ActionStore, canonical_json
from .identity_readback import ERPNextReadClient
from .read_tools import AccessScope, CanonicalRepository, InvalidBusinessInputError
from .twenty import TwentyClient


class TwentyActionError(RuntimeError):
    pass


class TwentyActionMismatch(TwentyActionError):
    pass


class TwentyActionUnavailable(TwentyActionError):
    pass


def _as_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _same_timestamp(left: str, right: str) -> bool:
    return abs((_as_utc(left) - _as_utc(right)).total_seconds()) < 0.001


def followup_target_id(action_id: str) -> str:
    return str(uuid5(UUID(action_id), "operion:twenty:company-target"))


class TwentyFollowupGateway:
    """Fixed-path Twenty Task writer plus ERPNext/Twenty preflight reader."""

    def __init__(
        self,
        twenty: TwentyClient,
        erpnext: ERPNextReadClient,
    ) -> None:
        self.twenty = twenty
        self.erpnext = erpnext

    def current_snapshot(self, target: dict[str, Any], assignee_id: str) -> str:
        try:
            data = self.twenty.graphql(
                """
                query FollowupPreflight($company: UUID!, $member: UUID!) {
                  company(filter: {id: {eq: $company}}) {
                    id updatedAt deletedAt wwiExternalId
                  }
                  workspaceMember(filter: {id: {eq: $member}}) {
                    id updatedAt deletedAt userId
                  }
                }
                """,
                {"company": target["customer_id"], "member": assignee_id},
            )
            company = data.get("company")
            member = data.get("workspaceMember")
            order = self.erpnext.record("Sales Order", target["order_id"])
        except Exception as error:
            raise TwentyActionUnavailable("preflight source is unavailable") from error
        if not company or company.get("deletedAt"):
            raise TwentyActionMismatch("TARGET_COMPANY_INVALID")
        if company.get("wwiExternalId") != target.get("customer_canonical_id"):
            raise TwentyActionMismatch("TARGET_COMPANY_IDENTITY_CHANGED")
        if not member or member.get("deletedAt"):
            raise TwentyActionMismatch("ASSIGNEE_INVALID")
        if order.get("name") != target["order_id"]:
            raise TwentyActionMismatch("TARGET_ORDER_INVALID")
        if order.get("customer") != target.get("erpnext_customer_id"):
            raise TwentyActionMismatch("TARGET_ORDER_CUSTOMER_CHANGED")
        if int(order.get("docstatus") or 0) != 1:
            raise TwentyActionMismatch("TARGET_ORDER_NOT_SUBMITTED")
        if order.get("status") in {"Cancelled", "Closed"}:
            raise TwentyActionMismatch("TARGET_ORDER_NOT_ACTIVE")
        snapshot = {
            "twenty_company_id": company["id"],
            "twenty_company_updated_at": company["updatedAt"],
            "assignee_id": member["id"],
            "erpnext_order_id": order["name"],
            "erpnext_order_modified": order.get("modified"),
            "erpnext_order_customer": order.get("customer"),
            "erpnext_order_docstatus": order.get("docstatus"),
            "erpnext_order_status": order.get("status"),
        }
        return hashlib.sha256(canonical_json(snapshot).encode()).hexdigest()

    def preflight(self, action: dict[str, Any]) -> str | None:
        payload = action["payload_json"]
        try:
            current = self.current_snapshot(
                payload["target"], payload["parameters"]["assignee_id"]
            )
        except TwentyActionMismatch as error:
            return str(error)
        if current != payload["preconditions"]["target_version"]:
            return "TARGET_VERSION_CHANGED"
        return None

    def _task_rows(self, task_id: str) -> list[dict[str, Any]]:
        data = self.twenty.graphql(
            """
            query FollowupTask($id: UUID!) {
              tasks(filter: {id: {eq: $id}}) {
                totalCount
                edges { node {
                  id title dueAt status assigneeId deletedAt
                  bodyV2 { markdown }
                } }
              }
            }
            """,
            {"id": task_id},
        )["tasks"]
        return [edge["node"] for edge in data["edges"]]

    def _target_rows(self, target_id: str) -> list[dict[str, Any]]:
        data = self.twenty.graphql(
            """
            query FollowupTarget($id: UUID!) {
              taskTargets(filter: {id: {eq: $id}}) {
                totalCount
                edges { node { id taskId targetCompanyId deletedAt } }
              }
            }
            """,
            {"id": target_id},
        )["taskTargets"]
        return [edge["node"] for edge in data["edges"]]

    @staticmethod
    def _task_matches(task: dict[str, Any], action: dict[str, Any]) -> bool:
        parameters = action["payload_json"]["parameters"]
        return (
            task.get("id") == action["action_id"]
            and task.get("deletedAt") is None
            and task.get("title") == parameters["title"]
            and (task.get("bodyV2") or {}).get("markdown") == parameters["body"]
            and task.get("status") == "TODO"
            and task.get("assigneeId") == parameters["assignee_id"]
            and _same_timestamp(task["dueAt"], parameters["due_at"])
        )

    @staticmethod
    def _target_matches(
        target: dict[str, Any], action: dict[str, Any], target_id: str
    ) -> bool:
        return (
            target.get("id") == target_id
            and target.get("deletedAt") is None
            and target.get("taskId") == action["action_id"]
            and target.get("targetCompanyId")
            == action["payload_json"]["target"]["customer_id"]
        )

    def inspect(self, action: dict[str, Any]) -> dict[str, Any]:
        task_id = action["action_id"]
        target_id = followup_target_id(task_id)
        try:
            tasks = self._task_rows(task_id)
            targets = self._target_rows(target_id)
        except Exception as error:
            raise TwentyActionUnavailable("Twenty readback is unavailable") from error
        if len(tasks) > 1 or len(targets) > 1:
            raise TwentyActionMismatch("MULTIPLE_REMOTE_RESULTS")
        try:
            if tasks and not self._task_matches(tasks[0], action):
                raise TwentyActionMismatch("REMOTE_TASK_CONTENT_MISMATCH")
            if targets and not self._target_matches(targets[0], action, target_id):
                raise TwentyActionMismatch("REMOTE_TARGET_CONTENT_MISMATCH")
        except TwentyActionMismatch:
            raise
        except Exception as error:
            raise TwentyActionMismatch("REMOTE_READBACK_INVALID") from error
        return {
            "task": tasks[0] if tasks else None,
            "target": targets[0] if targets else None,
            "task_id": task_id,
            "target_id": target_id,
        }

    def _create_task(self, action: dict[str, Any]) -> None:
        parameters = action["payload_json"]["parameters"]
        self.twenty.graphql(
            """
            mutation CreateFollowup($data: TaskCreateInput!) {
              createTask(data: $data) { id }
            }
            """,
            {
                "data": {
                    "id": action["action_id"],
                    "title": parameters["title"],
                    "bodyV2": {"markdown": parameters["body"]},
                    "dueAt": parameters["due_at"],
                    "status": "TODO",
                    "assigneeId": parameters["assignee_id"],
                }
            },
        )

    def _create_target(self, action: dict[str, Any], target_id: str) -> None:
        self.twenty.graphql(
            """
            mutation CreateFollowupTarget($data: TaskTargetCreateInput!) {
              createTaskTarget(data: $data) { id }
            }
            """,
            {
                "data": {
                    "id": target_id,
                    "taskId": action["action_id"],
                    "targetCompanyId": action["payload_json"]["target"]["customer_id"],
                }
            },
        )

    def submit(self, action: dict[str, Any]) -> dict[str, Any]:
        state = self.inspect(action)
        try:
            if state["task"] is None:
                self._create_task(action)
            state = self.inspect(action)
            if state["task"] is None:
                raise TwentyActionUnavailable("Task create was not observable")
            if state["target"] is None:
                self._create_target(action, state["target_id"])
            state = self.inspect(action)
        except TwentyActionMismatch:
            raise
        except Exception as error:
            raise TwentyActionUnavailable("Twenty result is unknown") from error
        if state["task"] is None or state["target"] is None:
            raise TwentyActionUnavailable("Twenty result is incomplete")
        return self._effect(action, state)

    def reconcile(self, action: dict[str, Any]) -> list[dict[str, Any]]:
        state = self.inspect(action)
        if state["task"] is None:
            return []
        if state["target"] is None:
            try:
                self._create_target(action, state["target_id"])
            except Exception as error:
                raise TwentyActionUnavailable("TaskTarget repair is unknown") from error
            state = self.inspect(action)
        if state["target"] is None:
            raise TwentyActionUnavailable("TaskTarget is still missing")
        return [self._effect(action, state)]

    @staticmethod
    def _effect(action: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        return {
            "effect_id": state["task_id"],
            "task_id": state["task_id"],
            "task_target_id": state["target_id"],
            "payload_hash": action["payload_hash"],
            "effect_kind": "twenty.followup_task",
        }


class FollowupProposalService:
    def __init__(
        self,
        *,
        store: ActionStore,
        repository: CanonicalRepository,
        scope: AccessScope,
        gateway: TwentyFollowupGateway,
        assignee_id: str,
        tenant_id: str,
        approval_window_minutes: int = 30,
    ) -> None:
        self.store = store
        self.repository = repository
        self.scope = scope
        self.gateway = gateway
        self.assignee_id = assignee_id
        self.tenant_id = tenant_id
        self.approval_window_minutes = approval_window_minutes

    def propose(
        self,
        *,
        case_id: str,
        title: str,
        body: str,
        due_at: datetime,
        idempotency_key: str,
        user_id: str,
    ) -> dict[str, Any]:
        case = self.repository.fulfillment_case(case_id)
        if case["result"] != "shortfall":
            raise InvalidBusinessInputError(
                "follow-up proposals require a verified shortfall"
            )
        if due_at.tzinfo is None or due_at.utcoffset() is None:
            raise InvalidBusinessInputError("due_at must include a timezone")
        now = datetime.now(UTC)
        due_at = due_at.astimezone(UTC)
        due_at = due_at.replace(microsecond=(due_at.microsecond // 1000) * 1000)
        if not now < due_at <= now + timedelta(days=30):
            raise InvalidBusinessInputError("due_at must be within the next 30 days")
        order_canonical_id = f"operion:e2:sales_order:{case_id}"
        orders = [
            row
            for row in self.repository.data["sales_orders"]
            if row["canonical_id"] == order_canonical_id
        ]
        if len(orders) != 1:
            raise InvalidBusinessInputError("case does not resolve to one sales order")
        customer_canonical_id = orders[0]["customer_canonical_id"]
        overview = self.repository.customer_overview(customer_canonical_id, self.scope)
        customer = overview["customer"]
        matching_orders = [
            row
            for row in overview["orders"]
            if row["canonical_id"] == order_canonical_id
        ]
        if len(matching_orders) != 1:
            raise InvalidBusinessInputError("order is outside the authorized scope")
        target = {
            "system": "twenty",
            "company": self.scope.operating_company,
            "customer_id": customer["twenty_id"],
            "order_id": matching_orders[0]["erpnext_id"],
            "customer_canonical_id": customer_canonical_id,
            "order_canonical_id": order_canonical_id,
            "erpnext_customer_id": customer["erpnext_id"],
        }
        target_version = self.gateway.current_snapshot(target, self.assignee_id)
        normalized_body = (
            f"{body.strip()}\n\n"
            f"ERPNext order: {target['order_id']}\n"
            f"Fulfillment case: {case_id}"
        )
        proposal = ProposalRequest(
            idempotency_key=idempotency_key,
            action_type="twenty.followup_task",
            target=target,
            parameters={
                "title": title.strip(),
                "body": normalized_body,
                "assignee_id": self.assignee_id,
                "due_at": due_at,
            },
            preconditions={"target_version": target_version},
            side_effects=FOLLOWUP_SIDE_EFFECTS,
            expires_at=now + timedelta(minutes=self.approval_window_minutes),
        )
        principal = Principal(
            user_id=user_id,
            tenant_id=self.tenant_id,
            companies=frozenset({self.scope.operating_company}),
            customer_ids=self.scope.customer_ids,
        )
        return self.store.propose(proposal, principal)
