from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

STUB_SIDE_EFFECTS = ("internal_stub_record",)
FOLLOWUP_SIDE_EFFECTS = (
    "twenty_internal_task",
    "twenty_company_link",
    "twenty_timeline_activity",
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ActionState(StrEnum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    EXECUTING = "EXECUTING"
    UNKNOWN = "UNKNOWN"
    RECONCILING = "RECONCILING"
    SUCCEEDED = "SUCCEEDED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    CONFLICT = "CONFLICT"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    CANCELLED = "CANCELLED"
    COMPENSATED = "COMPENSATED"


class ActionTarget(StrictModel):
    system: Literal["e3_stub", "twenty"]
    company: str = Field(min_length=1, max_length=120)
    customer_id: str = Field(min_length=1, max_length=160)
    order_id: str = Field(min_length=1, max_length=160)
    customer_canonical_id: str | None = Field(default=None, max_length=200)
    order_canonical_id: str | None = Field(default=None, max_length=200)
    erpnext_customer_id: str | None = Field(default=None, max_length=160)


class ActionParameters(StrictModel):
    title: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=2_000)
    assignee_id: str = Field(min_length=1, max_length=160)
    due_at: datetime

    @field_validator("due_at")
    @classmethod
    def due_at_has_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("due_at must include a timezone")
        return value


class ActionPreconditions(StrictModel):
    target_version: str = Field(min_length=1, max_length=120)


class ProposalRequest(StrictModel):
    idempotency_key: str = Field(pattern=r"^[A-Za-z0-9_.:-]{1,128}$")
    action_type: Literal["stub.followup_task", "twenty.followup_task"]
    target: ActionTarget
    parameters: ActionParameters
    preconditions: ActionPreconditions
    side_effects: tuple[str, ...] = Field(min_length=1, max_length=8)
    expires_at: datetime
    compensates_action_id: str | None = Field(
        default=None, pattern=r"^[A-Za-z0-9-]{1,128}$"
    )

    @field_validator("side_effects")
    @classmethod
    def unique_side_effects(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("side_effects must be unique")
        if value not in {STUB_SIDE_EFFECTS, FOLLOWUP_SIDE_EFFECTS}:
            raise ValueError("side_effects do not match an allowed action contract")
        return value

    @field_validator("expires_at")
    @classmethod
    def expires_at_has_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("expires_at must include a timezone")
        return value

    @model_validator(mode="after")
    def action_contract_matches_target(self) -> ProposalRequest:
        validate_action_contract(self.action_type, self.target, self.side_effects)
        return self


class DecisionRequest(StrictModel):
    revision: int = Field(ge=1)
    decision: Literal["approve", "reject", "revoke"]
    request_id: str = Field(pattern=r"^[A-Za-z0-9_.:-]{1,128}$")
    reason: str | None = Field(default=None, max_length=500)


class RevisionRequest(StrictModel):
    request_id: str = Field(pattern=r"^[A-Za-z0-9_.:-]{1,128}$")
    target: ActionTarget
    parameters: ActionParameters
    preconditions: ActionPreconditions
    side_effects: tuple[str, ...] = Field(min_length=1, max_length=8)
    expires_at: datetime

    @field_validator("expires_at")
    @classmethod
    def expires_at_has_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("expires_at must include a timezone")
        return value

    @field_validator("side_effects")
    @classmethod
    def allowed_side_effects(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value not in {STUB_SIDE_EFFECTS, FOLLOWUP_SIDE_EFFECTS}:
            raise ValueError("side_effects do not match an allowed action contract")
        return value


class Principal(StrictModel):
    user_id: str
    tenant_id: str
    companies: frozenset[str]
    customer_ids: frozenset[str] = frozenset()
    can_approve: bool = False


def validate_action_contract(
    action_type: str,
    target: ActionTarget,
    side_effects: tuple[str, ...],
) -> None:
    if action_type == "stub.followup_task":
        if target.system != "e3_stub" or side_effects != STUB_SIDE_EFFECTS:
            raise ValueError("stub action contract does not match its target")
        return
    if action_type == "twenty.followup_task":
        if target.system != "twenty" or side_effects != FOLLOWUP_SIDE_EFFECTS:
            raise ValueError("Twenty follow-up contract does not match its target")
        required = {
            "customer_canonical_id": target.customer_canonical_id,
            "order_canonical_id": target.order_canonical_id,
            "erpnext_customer_id": target.erpnext_customer_id,
        }
        if any(not value for value in required.values()):
            raise ValueError("Twenty follow-up target is missing canonical identity")
        return
    raise ValueError("unsupported action type")


class ActionConflict(RuntimeError):
    pass


class ActionDenied(RuntimeError):
    pass


class ActionNotFound(RuntimeError):
    pass


class ActionUnavailable(RuntimeError):
    pass
