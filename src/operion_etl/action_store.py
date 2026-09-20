from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from importlib.resources import files
from typing import Any
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .action_models import (
    ActionConflict,
    ActionDenied,
    ActionNotFound,
    ActionState,
    Principal,
    ProposalRequest,
    RevisionRequest,
    validate_action_contract,
)

POLICY_VERSION = "e3-action-policy-v1"


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def utc_now() -> datetime:
    return datetime.now(UTC)


class ActionStore:
    def __init__(self, dsn: str, application_role: str | None = None) -> None:
        self.dsn = dsn
        self.application_role = application_role

    def _connect(
        self, *, privileged: bool = False
    ) -> psycopg.Connection[dict[str, Any]]:
        connection = psycopg.connect(self.dsn, row_factory=dict_row)
        if self.application_role and not privileged:
            connection.execute(
                sql.SQL("SET ROLE {}").format(sql.Identifier(self.application_role))
            )
        return connection

    def migrate(self) -> None:
        migration = (
            files("operion_etl")
            .joinpath("migrations/0001_action_control.sql")
            .read_text(encoding="utf-8")
        )
        with self._connect(privileged=True) as connection:
            connection.execute(migration)

    def _append_event(
        self,
        connection: psycopg.Connection[dict[str, Any]],
        action_id: str,
        event_type: str,
        actor_id: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        previous = connection.execute(
            """
            SELECT event_hash FROM operion_action_events
            WHERE action_id = %s ORDER BY event_id DESC LIMIT 1
            """,
            (action_id,),
        ).fetchone()
        previous_hash = previous["event_hash"] if previous else "GENESIS"
        created_at = utc_now()
        safe_details = details or {}
        digest = content_hash(
            {
                "action_id": action_id,
                "event_type": event_type,
                "actor_id": actor_id,
                "details": safe_details,
                "previous_hash": previous_hash,
                "created_at": created_at.isoformat(),
            }
        )
        connection.execute(
            """
            INSERT INTO operion_action_events(
                action_id, event_type, actor_id, details_json,
                previous_hash, event_hash, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                action_id,
                event_type,
                actor_id,
                Jsonb(safe_details),
                previous_hash,
                digest,
                created_at,
            ),
        )

    @staticmethod
    def _require_scope(row: dict[str, Any], principal: Principal) -> None:
        if row["tenant_id"] != principal.tenant_id:
            raise ActionNotFound("action was not found")
        company = row["payload_json"]["target"]["company"]
        if company not in principal.companies:
            raise ActionNotFound("action was not found")
        customer_id = row["payload_json"]["target"].get("customer_canonical_id")
        if customer_id and customer_id not in principal.customer_ids:
            raise ActionNotFound("action was not found")

    def _select_action(
        self,
        connection: psycopg.Connection[dict[str, Any]],
        action_id: str,
        *,
        for_update: bool = False,
    ) -> dict[str, Any]:
        lock = " FOR UPDATE OF a" if for_update else ""
        row = connection.execute(
            f"""
            SELECT a.*, r.payload_json, r.policy_version
            FROM operion_actions a
            JOIN operion_action_revisions r
              ON r.action_id = a.action_id AND r.revision = a.current_revision
            WHERE a.action_id = %s{lock}
            """,
            (action_id,),
        ).fetchone()
        if row is None:
            raise ActionNotFound("action was not found")
        return row

    def propose(
        self, proposal: ProposalRequest, principal: Principal
    ) -> dict[str, Any]:
        if proposal.target.company not in principal.companies:
            raise ActionDenied("target company is outside the authorized scope")
        if (
            proposal.target.customer_canonical_id
            and proposal.target.customer_canonical_id not in principal.customer_ids
        ):
            raise ActionDenied("target customer is outside the authorized scope")
        if proposal.expires_at <= utc_now():
            raise ActionConflict("proposal is already expired")
        payload = proposal.model_dump(mode="json")
        payload_hash = content_hash(payload)
        action_id = str(uuid4())
        with self._connect() as connection:
            if proposal.compensates_action_id:
                original = self._select_action(
                    connection, proposal.compensates_action_id, for_update=True
                )
                self._require_scope(original, principal)
                if original["state"] != ActionState.SUCCEEDED.value:
                    raise ActionConflict(
                        "only a succeeded action may be referenced for compensation"
                    )
            inserted = connection.execute(
                """
                INSERT INTO operion_actions(
                    action_id, tenant_id, owner_id, action_type, idempotency_key,
                    payload_hash, state, expires_at, compensates_action_id
                ) VALUES (%s, %s, %s, %s, %s, %s, 'PENDING_APPROVAL', %s, %s)
                ON CONFLICT (tenant_id, owner_id, action_type, idempotency_key)
                DO NOTHING RETURNING action_id
                """,
                (
                    action_id,
                    principal.tenant_id,
                    principal.user_id,
                    proposal.action_type,
                    proposal.idempotency_key,
                    payload_hash,
                    proposal.expires_at,
                    proposal.compensates_action_id,
                ),
            ).fetchone()
            if inserted is None:
                existing = connection.execute(
                    """
                    SELECT action_id, payload_hash FROM operion_actions
                    WHERE tenant_id = %s AND owner_id = %s
                      AND action_type = %s AND idempotency_key = %s
                    """,
                    (
                        principal.tenant_id,
                        principal.user_id,
                        proposal.action_type,
                        proposal.idempotency_key,
                    ),
                ).fetchone()
                assert existing is not None
                if existing["payload_hash"] != payload_hash:
                    raise ActionConflict(
                        "idempotency key was already used for different content"
                    )
                action_id = existing["action_id"]
            else:
                connection.execute(
                    """
                    INSERT INTO operion_action_revisions(
                        action_id, revision, payload_json, payload_hash,
                        policy_version, created_by
                    ) VALUES (%s, 1, %s, %s, %s, %s)
                    """,
                    (
                        action_id,
                        Jsonb(payload),
                        payload_hash,
                        POLICY_VERSION,
                        principal.user_id,
                    ),
                )
                self._append_event(
                    connection,
                    action_id,
                    "PROPOSED",
                    principal.user_id,
                    {"revision": 1, "payload_hash": payload_hash},
                )
        return self.get(action_id, principal)

    def get(self, action_id: str, principal: Principal) -> dict[str, Any]:
        with self._connect() as connection:
            row = self._select_action(connection, action_id)
            self._require_scope(row, principal)
            return row

    def list(
        self, principal: Principal, state: ActionState | None = None
    ) -> list[dict[str, Any]]:
        parameters: list[Any] = [
            principal.tenant_id,
            list(principal.companies),
            list(principal.customer_ids),
        ]
        state_clause = ""
        if state is not None:
            state_clause = " AND a.state = %s"
            parameters.append(state.value)
        with self._connect() as connection:
            return connection.execute(
                f"""
                SELECT a.*, r.payload_json, r.policy_version
                FROM operion_actions a
                JOIN operion_action_revisions r
                  ON r.action_id = a.action_id AND r.revision = a.current_revision
                WHERE a.tenant_id = %s
                  AND r.payload_json->'target'->>'company' = ANY(%s)
                  AND (
                    r.payload_json->'target'->>'customer_canonical_id' IS NULL
                    OR r.payload_json->'target'->>'customer_canonical_id' = ANY(%s)
                  ){state_clause}
                ORDER BY a.updated_at DESC, a.action_id
                """,
                parameters,
            ).fetchall()

    def revise(
        self,
        action_id: str,
        revision: RevisionRequest,
        principal: Principal,
    ) -> dict[str, Any]:
        if revision.target.company not in principal.companies:
            raise ActionDenied("target company is outside the authorized scope")
        if (
            revision.target.customer_canonical_id
            and revision.target.customer_canonical_id not in principal.customer_ids
        ):
            raise ActionDenied("target customer is outside the authorized scope")
        if revision.expires_at <= utc_now():
            raise ActionConflict("revision is already expired")
        with self._connect() as connection:
            current = self._select_action(connection, action_id, for_update=True)
            self._require_scope(current, principal)
            if current["action_type"] == "twenty.followup_task":
                raise ActionConflict(
                    "Twenty follow-up proposals must be regenerated from verified facts"
                )
            if current["owner_id"] != principal.user_id:
                raise ActionDenied("only the proposal owner may revise it")
            if current["state"] not in {
                ActionState.PENDING_APPROVAL.value,
                ActionState.APPROVED.value,
            }:
                raise ActionConflict("action can no longer be revised")
            try:
                validate_action_contract(
                    current["action_type"], revision.target, revision.side_effects
                )
            except ValueError as error:
                raise ActionConflict(str(error)) from error
            payload = {
                "idempotency_key": current["idempotency_key"],
                "action_type": current["action_type"],
                **revision.model_dump(mode="json", exclude={"request_id"}),
                "compensates_action_id": current["compensates_action_id"],
            }
            payload_hash = content_hash(payload)
            next_revision = current["current_revision"] + 1
            connection.execute(
                """
                INSERT INTO operion_action_revisions(
                    action_id, revision, payload_json, payload_hash,
                    policy_version, created_by
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    action_id,
                    next_revision,
                    Jsonb(payload),
                    payload_hash,
                    POLICY_VERSION,
                    principal.user_id,
                ),
            )
            connection.execute(
                """
                UPDATE operion_actions SET current_revision = %s,
                    payload_hash = %s, state = 'PENDING_APPROVAL',
                    expires_at = %s, lease_owner = NULL, lease_token = NULL,
                    lease_until = NULL, updated_at = clock_timestamp()
                WHERE action_id = %s
                """,
                (next_revision, payload_hash, revision.expires_at, action_id),
            )
            self._append_event(
                connection,
                action_id,
                "REVISED",
                principal.user_id,
                {
                    "revision": next_revision,
                    "payload_hash": payload_hash,
                    "request_id": revision.request_id,
                    "prior_approval_invalidated": current["state"]
                    == ActionState.APPROVED.value,
                },
            )
        return self.get(action_id, principal)

    def decide(
        self,
        action_id: str,
        revision: int,
        decision: str,
        request_id: str,
        reason: str | None,
        principal: Principal,
    ) -> dict[str, Any]:
        expired = False
        with self._connect() as connection:
            current = self._select_action(connection, action_id, for_update=True)
            self._require_scope(current, principal)
            prior = connection.execute(
                """
                SELECT * FROM operion_action_decisions
                WHERE actor_id = %s AND request_id = %s
                """,
                (principal.user_id, request_id),
            ).fetchone()
            if prior is not None:
                if (
                    prior["action_id"] == action_id
                    and prior["revision"] == revision
                    and prior["decision"] == decision
                ):
                    return current
                raise ActionConflict("decision request_id was already used")
            if not principal.can_approve:
                raise ActionDenied("principal is not an action approver")
            if current["owner_id"] == principal.user_id:
                raise ActionDenied("proposal owner cannot decide their own action")
            if current["current_revision"] != revision:
                raise ActionConflict("decision refers to a stale revision")
            if current["expires_at"] <= utc_now():
                connection.execute(
                    """
                    UPDATE operion_actions SET state = 'EXPIRED',
                        updated_at = clock_timestamp() WHERE action_id = %s
                    """,
                    (action_id,),
                )
                self._append_event(connection, action_id, "EXPIRED", principal.user_id)
                expired = True
            else:
                transitions = {
                    "approve": (
                        {ActionState.PENDING_APPROVAL.value},
                        ActionState.APPROVED.value,
                        "APPROVED",
                    ),
                    "reject": (
                        {ActionState.PENDING_APPROVAL.value},
                        ActionState.REJECTED.value,
                        "REJECTED",
                    ),
                    "revoke": (
                        {ActionState.APPROVED.value},
                        ActionState.REVOKED.value,
                        "REVOKED",
                    ),
                }
                allowed, next_state, event_type = transitions[decision]
                if current["state"] not in allowed:
                    raise ActionConflict(
                        f"cannot {decision} action in state {current['state']}"
                    )
                connection.execute(
                    """
                    INSERT INTO operion_action_decisions(
                        decision_id, action_id, revision, actor_id, decision,
                        request_id, payload_hash, reason
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(uuid4()),
                        action_id,
                        revision,
                        principal.user_id,
                        decision,
                        request_id,
                        current["payload_hash"],
                        reason,
                    ),
                )
                connection.execute(
                    """
                    UPDATE operion_actions SET state = %s,
                        updated_at = clock_timestamp() WHERE action_id = %s
                    """,
                    (next_state, action_id),
                )
                self._append_event(
                    connection,
                    action_id,
                    event_type,
                    principal.user_id,
                    {
                        "revision": revision,
                        "payload_hash": current["payload_hash"],
                        "request_id": request_id,
                    },
                )
        if expired:
            raise ActionConflict("action approval has expired")
        return self.get(action_id, principal)

    def set_pause(self, scope: str, paused: bool, reason: str, actor: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO operion_action_pauses(scope, paused, reason, updated_by)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (scope) DO UPDATE SET paused = EXCLUDED.paused,
                    reason = EXCLUDED.reason, updated_by = EXCLUDED.updated_by,
                    updated_at = clock_timestamp()
                """,
                (scope, paused, reason, actor),
            )

    def is_paused(self, action_type: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT EXISTS(
                    SELECT 1 FROM operion_action_pauses
                    WHERE paused AND scope IN ('global', %s)
                ) AS value
                """,
                (action_type,),
            ).fetchone()
            return bool(row and row["value"])

    def claim(self, worker_id: str, lease_seconds: int = 30) -> dict[str, Any] | None:
        lease_token = str(uuid4())
        attempt_id = str(uuid4())
        with self._connect() as connection:
            expired = connection.execute(
                """
                UPDATE operion_actions SET state = 'EXPIRED',
                    updated_at = clock_timestamp()
                WHERE state IN ('PENDING_APPROVAL', 'APPROVED')
                  AND expires_at <= clock_timestamp()
                RETURNING action_id
                """
            ).fetchall()
            for item in expired:
                self._append_event(connection, item["action_id"], "EXPIRED", worker_id)
            row = connection.execute(
                """
                WITH candidate AS (
                    SELECT a0.action_id FROM operion_actions a0
                    WHERE a0.state = 'APPROVED'
                      AND a0.expires_at > clock_timestamp()
                      AND NOT EXISTS (
                          SELECT 1 FROM operion_action_pauses p
                          WHERE p.paused
                            AND p.scope IN ('global', a0.action_type)
                      )
                    ORDER BY updated_at, action_id
                    FOR UPDATE SKIP LOCKED LIMIT 1
                )
                UPDATE operion_actions a SET
                    state = 'EXECUTING', lease_owner = %s, lease_token = %s,
                    lease_until = clock_timestamp() + (%s * interval '1 second'),
                    updated_at = clock_timestamp()
                FROM candidate c WHERE a.action_id = c.action_id
                RETURNING a.*
                """,
                (worker_id, lease_token, lease_seconds),
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                """
                INSERT INTO operion_action_attempts(
                    attempt_id, action_id, revision, worker_id, lease_token, state
                ) VALUES (%s, %s, %s, %s, %s, 'CLAIMED')
                """,
                (
                    attempt_id,
                    row["action_id"],
                    row["current_revision"],
                    worker_id,
                    lease_token,
                ),
            )
            self._append_event(
                connection,
                row["action_id"],
                "CLAIMED",
                worker_id,
                {"attempt_id": attempt_id, "revision": row["current_revision"]},
            )
            full = self._select_action(connection, row["action_id"])
            full["attempt_id"] = attempt_id
            return full

    def transition_attempt(
        self,
        action_id: str,
        attempt_id: str,
        lease_token: str,
        *,
        state: ActionState,
        event_type: str,
        actor: str,
        remote_ref: str | None = None,
        error_code: str | None = None,
        result: dict[str, Any] | None = None,
    ) -> None:
        with self._connect() as connection:
            current = self._select_action(connection, action_id, for_update=True)
            if current["lease_token"] != lease_token:
                raise ActionConflict("worker lease is no longer valid")
            connection.execute(
                """
                UPDATE operion_actions SET state = %s, remote_ref = %s,
                    result_json = %s, updated_at = clock_timestamp(),
                    lease_owner = CASE WHEN %s IN ('APPROVED','SUCCEEDED','CONFLICT','MANUAL_REVIEW')
                        THEN NULL ELSE lease_owner END,
                    lease_token = CASE WHEN %s IN ('APPROVED','SUCCEEDED','CONFLICT','MANUAL_REVIEW')
                        THEN NULL ELSE lease_token END,
                    lease_until = CASE WHEN %s IN ('APPROVED','SUCCEEDED','CONFLICT','MANUAL_REVIEW')
                        THEN NULL ELSE lease_until END
                WHERE action_id = %s
                """,
                (
                    state.value,
                    remote_ref,
                    Jsonb(result) if result is not None else None,
                    state.value,
                    state.value,
                    state.value,
                    action_id,
                ),
            )
            connection.execute(
                """
                UPDATE operion_action_attempts SET state = %s, remote_ref = %s,
                    error_code = %s, updated_at = clock_timestamp()
                WHERE attempt_id = %s
                """,
                (state.value, remote_ref, error_code, attempt_id),
            )
            self._append_event(
                connection,
                action_id,
                event_type,
                actor,
                {
                    "attempt_id": attempt_id,
                    "remote_ref": remote_ref,
                    "error_code": error_code,
                },
            )

    def recover_expired_leases(self, actor: str) -> list[str]:
        recovered: list[str] = []
        with self._connect() as connection:
            rows = connection.execute(
                """
                UPDATE operion_actions SET state = 'RECONCILING',
                    updated_at = clock_timestamp()
                WHERE state = 'EXECUTING' AND lease_until <= clock_timestamp()
                RETURNING action_id
                """
            ).fetchall()
            for row in rows:
                recovered.append(row["action_id"])
                self._append_event(
                    connection,
                    row["action_id"],
                    "LEASE_EXPIRED_RECONCILING",
                    actor,
                )
        return recovered

    def mark_reconciling(self, action_id: str, actor: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = self._select_action(connection, action_id, for_update=True)
            if row["state"] not in {
                ActionState.UNKNOWN.value,
                ActionState.EXECUTING.value,
                ActionState.RECONCILING.value,
            }:
                raise ActionConflict("action is not eligible for reconciliation")
            connection.execute(
                """
                UPDATE operion_actions SET state = 'RECONCILING',
                    updated_at = clock_timestamp() WHERE action_id = %s
                """,
                (action_id,),
            )
            self._append_event(connection, action_id, "RECONCILING", actor)
            return self._select_action(connection, action_id)

    def cancel(self, action_id: str, principal: Principal) -> dict[str, Any]:
        with self._connect() as connection:
            row = self._select_action(connection, action_id, for_update=True)
            self._require_scope(row, principal)
            if row["state"] in {
                ActionState.PENDING_APPROVAL.value,
                ActionState.APPROVED.value,
            }:
                next_state = ActionState.CANCELLED.value
                event = "CANCELLED_BEFORE_SEND"
                connection.execute(
                    """
                    UPDATE operion_actions SET state = %s,
                        updated_at = clock_timestamp() WHERE action_id = %s
                    """,
                    (next_state, action_id),
                )
            elif row["state"] in {
                ActionState.EXECUTING.value,
                ActionState.UNKNOWN.value,
                ActionState.RECONCILING.value,
            }:
                event = "CANCEL_REQUESTED_IN_FLIGHT"
            else:
                raise ActionConflict("action cannot be cancelled in its current state")
            self._append_event(connection, action_id, event, principal.user_id)
        return self.get(action_id, principal)

    def events(self, action_id: str, principal: Principal) -> list[dict[str, Any]]:
        with self._connect() as connection:
            row = self._select_action(connection, action_id)
            self._require_scope(row, principal)
            return connection.execute(
                """
                SELECT event_id, action_id, event_type, actor_id, details_json,
                    previous_hash, event_hash, created_at
                FROM operion_action_events WHERE action_id = %s ORDER BY event_id
                """,
                (action_id,),
            ).fetchall()

    def verify_event_chain(self, action_id: str) -> bool:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM operion_action_events
                WHERE action_id = %s ORDER BY event_id
                """,
                (action_id,),
            ).fetchall()
        previous = "GENESIS"
        for row in rows:
            expected = content_hash(
                {
                    "action_id": row["action_id"],
                    "event_type": row["event_type"],
                    "actor_id": row["actor_id"],
                    "details": row["details_json"],
                    "previous_hash": previous,
                    "created_at": row["created_at"].isoformat(),
                }
            )
            if row["previous_hash"] != previous or row["event_hash"] != expected:
                return False
            previous = row["event_hash"]
        return True

    def stub_submit(self, action_id: str, payload_hash: str) -> dict[str, Any]:
        with self._connect() as connection:
            existing = connection.execute(
                """
                SELECT * FROM operion_e3_stub_effects WHERE dedupe_key = %s
                """,
                (action_id,),
            ).fetchone()
            if existing is None:
                effect_id = str(uuid4())
                connection.execute(
                    """
                    INSERT INTO operion_e3_stub_effects(
                        effect_id, action_id, dedupe_key, payload_hash
                    ) VALUES (%s, %s, %s, %s)
                    """,
                    (effect_id, action_id, action_id, payload_hash),
                )
                existing = {
                    "effect_id": effect_id,
                    "action_id": action_id,
                    "dedupe_key": action_id,
                    "payload_hash": payload_hash,
                    "effect_kind": "create",
                }
            return existing

    def stub_effects(self, action_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return connection.execute(
                """
                SELECT * FROM operion_e3_stub_effects
                WHERE action_id = %s ORDER BY created_at, effect_id
                """,
                (action_id,),
            ).fetchall()

    def inject_duplicate_stub_effect(self, action_id: str, payload_hash: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO operion_e3_stub_effects(
                    effect_id, action_id, dedupe_key, payload_hash
                ) VALUES (%s, %s, %s, %s)
                """,
                (str(uuid4()), action_id, f"anomaly:{uuid4()}", payload_hash),
            )

    def expire_lease_for_test(self, action_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE operion_actions SET lease_until = %s WHERE action_id = %s
                """,
                (utc_now() - timedelta(seconds=1), action_id),
            )


def migration_main() -> None:
    dsn = os.environ.get("OPERION_ACTION_MIGRATION_DATABASE_URL", "")
    if not dsn:
        raise SystemExit("OPERION_ACTION_MIGRATION_DATABASE_URL is required")
    ActionStore(dsn).migrate()
    print("Operion action-control migration completed.")
