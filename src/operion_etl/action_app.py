from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from typing import Any, Literal

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from .action_models import (
    ActionConflict,
    ActionDenied,
    ActionNotFound,
    ActionState,
    DecisionRequest,
    Principal,
    ProposalRequest,
    RevisionRequest,
    StrictModel,
)
from .action_store import ActionStore


class CancelRequest(StrictModel):
    request_id: str


class PauseRequest(StrictModel):
    scope: Literal["global", "stub.followup_task", "twenty.followup_task"]
    paused: bool
    reason: str


@dataclass(frozen=True)
class ActionCredential:
    token: str
    csrf_token: str
    principal: Principal


class ActionApplication:
    def __init__(
        self,
        store: ActionStore,
        credentials: list[ActionCredential],
    ) -> None:
        if not credentials:
            raise RuntimeError("at least one action credential is required")
        self.store = store
        self.credentials = credentials

    def authenticate(self, request: Request, *, mutation: bool = False) -> Principal:
        authorization = request.headers.get("authorization", "")
        supplied = authorization.removeprefix("Bearer ")
        for credential in self.credentials:
            if secrets.compare_digest(supplied, credential.token):
                if mutation and not secrets.compare_digest(
                    request.headers.get("x-operion-csrf", ""),
                    credential.csrf_token,
                ):
                    raise HTTPException(status_code=403, detail="invalid CSRF token")
                return credential.principal
        raise HTTPException(status_code=401, detail="invalid action credential")


def create_action_app(application: ActionApplication) -> FastAPI:
    app = FastAPI(title="Operion action control", version="0.3.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            value.strip()
            for value in os.environ.get(
                "OPERION_WEB_ORIGINS", "http://localhost:3000"
            ).split(",")
            if value.strip()
        ],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Operion-CSRF",
        ],
    )

    @app.exception_handler(ActionNotFound)
    async def not_found(_: Request, error: ActionNotFound):
        return _error(404, "ACTION_NOT_FOUND", str(error))

    @app.exception_handler(ActionDenied)
    async def denied(_: Request, error: ActionDenied):
        return _error(403, "ACTION_DENIED", str(error))

    @app.exception_handler(ActionConflict)
    async def conflict(_: Request, error: ActionConflict):
        return _error(409, "ACTION_CONFLICT", str(error))

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "mode": "e4_controlled_followup",
            "writes_enabled": True,
            "write_scope": "approved_internal_followup_tasks_only",
            "action_types": ["stub.followup_task", "twenty.followup_task"],
        }

    @app.post("/api/action-proposals")
    async def propose(request: Request, body: ProposalRequest) -> dict[str, Any]:
        principal = application.authenticate(request, mutation=True)
        if body.action_type == "twenty.followup_task":
            raise ActionDenied(
                "Twenty follow-up proposals must use the verified server-side service"
            )
        return application.store.propose(body, principal)

    @app.get("/api/actions")
    async def list_actions(
        request: Request,
        status: ActionState | None = Query(default=None),
    ) -> dict[str, Any]:
        principal = application.authenticate(request)
        return {"actions": application.store.list(principal, status)}

    @app.get("/api/actions/{action_id}")
    async def get_action(request: Request, action_id: str) -> dict[str, Any]:
        principal = application.authenticate(request)
        return application.store.get(action_id, principal)

    @app.get("/api/actions/{action_id}/events")
    async def events(request: Request, action_id: str) -> dict[str, Any]:
        principal = application.authenticate(request)
        return {"events": application.store.events(action_id, principal)}

    @app.post("/api/actions/{action_id}/decisions")
    async def decide(
        request: Request,
        action_id: str,
        body: DecisionRequest,
    ) -> dict[str, Any]:
        principal = application.authenticate(request, mutation=True)
        return application.store.decide(
            action_id,
            body.revision,
            body.decision,
            body.request_id,
            body.reason,
            principal,
        )

    @app.post("/api/actions/{action_id}/revisions")
    async def revise(
        request: Request,
        action_id: str,
        body: RevisionRequest,
    ) -> dict[str, Any]:
        principal = application.authenticate(request, mutation=True)
        return application.store.revise(action_id, body, principal)

    @app.post("/api/actions/{action_id}/cancel")
    async def cancel(
        request: Request,
        action_id: str,
        body: CancelRequest,
    ) -> dict[str, Any]:
        principal = application.authenticate(request, mutation=True)
        result = application.store.cancel(action_id, principal)
        result["cancel_request_id"] = body.request_id
        return result

    @app.post("/api/action-pauses")
    async def set_pause(request: Request, body: PauseRequest) -> dict[str, Any]:
        principal = application.authenticate(request, mutation=True)
        if not principal.can_approve:
            raise ActionDenied("principal cannot operate the pause switch")
        application.store.set_pause(
            body.scope, body.paused, body.reason, principal.user_id
        )
        return {"scope": body.scope, "paused": body.paused}

    return app


def _error(status: int, code: str, detail: str):
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=status, content={"error": {"code": code, "detail": detail}}
    )


def application_from_environment() -> ActionApplication:
    dsn = os.environ.get("OPERION_ACTION_DATABASE_URL", "")
    token = os.environ.get("OPERION_ACTION_TOKEN", "")
    csrf_token = os.environ.get("OPERION_ACTION_CSRF_TOKEN", "")
    if not dsn or not token or not csrf_token:
        raise RuntimeError(
            "OPERION_ACTION_DATABASE_URL, OPERION_ACTION_TOKEN, and "
            "OPERION_ACTION_CSRF_TOKEN are required"
        )
    store = ActionStore(
        dsn,
        os.environ.get("OPERION_ACTION_DATABASE_ROLE") or None,
    )
    principal = Principal(
        user_id=os.environ.get("OPERION_ACTION_USER_ID", "e3-local-user"),
        tenant_id=os.environ.get("OPERION_ACTION_TENANT_ID", "e3-local-tenant"),
        companies=frozenset(
            value.strip()
            for value in os.environ.get(
                "OPERION_ACTION_COMPANIES", "AI Demo GmbH"
            ).split(",")
            if value.strip()
        ),
        customer_ids=frozenset(
            value.strip()
            for value in os.environ.get("OPERION_ACTION_CUSTOMER_IDS", "").split(",")
            if value.strip()
        ),
        can_approve=os.environ.get("OPERION_ACTION_CAN_APPROVE", "0") == "1",
    )
    return ActionApplication(store, [ActionCredential(token, csrf_token, principal)])


def main() -> None:
    host = os.environ.get("OPERION_ACTION_HOST", "127.0.0.1")
    port = int(os.environ.get("OPERION_ACTION_PORT", "8001"))
    uvicorn.run(create_action_app(application_from_environment()), host=host, port=port)


if __name__ == "__main__":
    main()
