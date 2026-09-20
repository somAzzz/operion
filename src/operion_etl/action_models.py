from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    system: Literal["e3_stub"]
    company: str = Field(min_length=1, max_length=120)
    customer_id: str = Field(min_length=1, max_length=160)
    order_id: str = Field(min_length=1, max_length=160)


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
    action_type: Literal["stub.followup_task"]
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
        if value != ("internal_stub_record",):
            raise ValueError("only the E3 internal stub side effect is allowed")
        return value

    @field_validator("expires_at")
    @classmethod
    def expires_at_has_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("expires_at must include a timezone")
        return value


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
    def only_stub_side_effect(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != ("internal_stub_record",):
            raise ValueError("only the E3 internal stub side effect is allowed")
        return value


class Principal(StrictModel):
    user_id: str
    tenant_id: str
    companies: frozenset[str]
    can_approve: bool = False


class ActionConflict(RuntimeError):
    pass


class ActionDenied(RuntimeError):
    pass


class ActionNotFound(RuntimeError):
    pass


class ActionUnavailable(RuntimeError):
    pass
