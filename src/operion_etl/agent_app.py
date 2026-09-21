from __future__ import annotations

import asyncio
import os
import re
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
from ag_ui.core import EventType, RunErrorEvent
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError
from pydantic_ai import Agent, CancellationToken
from pydantic_ai.agent import AgentRunResult
from pydantic_ai.exceptions import RunCancelled
from pydantic_ai.messages import ModelRequest, UserPromptPart
from pydantic_ai.ui.ag_ui import AGUIAdapter

from .action_store import ActionStore
from .agent_runtime import (
    FOLLOWUP_TOOLS,
    READ_TOOLS,
    AgentDependencies,
    AgentSettings,
    create_operion_agent,
    repository_from_environment,
    scope_from_environment,
)
from .enterprise_auth import (
    AuthenticationError,
    AuthorizationError,
    EnterpriseIdentity,
    OIDCAuthenticator,
)
from .identity_readback import ERPNextReadClient
from .read_tools import AccessScope, CanonicalRepository
from .session_store import (
    ConversationBusyError,
    ConversationStore,
    RunReplayError,
    SessionAccessDenied,
)
from .twenty import TwentyClient
from .twenty_actions import FollowupProposalService, TwentyFollowupGateway

ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


class AgentApplication:
    def __init__(
        self,
        *,
        settings: AgentSettings,
        repository: CanonicalRepository,
        scope: AccessScope,
        store: ConversationStore,
        token: str,
        user_id: str,
        tenant_id: str = "local-demo",
        agent: Agent[AgentDependencies, str] | None = None,
        proposal_service: FollowupProposalService | None = None,
        authenticator: OIDCAuthenticator | None = None,
    ) -> None:
        if not token and authenticator is None:
            raise RuntimeError("OPERION_AGENT_TOKEN is required")
        self.settings = settings
        self.repository = repository
        self.scope = scope
        self.store = store
        self.token = token
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.authenticator = authenticator
        self.proposal_service = proposal_service
        self.allowed_tools = (
            READ_TOOLS | FOLLOWUP_TOOLS if proposal_service is not None else READ_TOOLS
        )
        self.agent = agent or create_operion_agent(settings)
        self.semaphore = asyncio.Semaphore(settings.max_concurrent_runs)
        self.conversation_locks: dict[str, asyncio.Lock] = {}
        self.active_runs: dict[str, tuple[str, CancellationToken]] = {}

    def authenticate(self, request: Request) -> EnterpriseIdentity:
        authorization = request.headers.get("authorization", "")
        if self.authenticator is not None:
            try:
                identity = self.authenticator.authenticate(authorization)
                identity.require("agent_read")
                return identity
            except AuthenticationError as error:
                raise HTTPException(status_code=401, detail=str(error)) from error
            except AuthorizationError as error:
                raise HTTPException(status_code=403, detail=str(error)) from error
        expected = f"Bearer {self.token}"
        if not secrets.compare_digest(authorization, expected):
            raise HTTPException(status_code=401, detail="invalid agent credential")
        return EnterpriseIdentity(
            user_id=self.user_id,
            tenant_id=self.tenant_id,
            operating_company=self.scope.operating_company,
            customer_ids=self.scope.customer_ids,
            roles=frozenset(
                {"agent_read"}
                | ({"followup_proposer"} if self.proposal_service else set())
            ),
            subject=self.user_id,
            session_id="static-local-session",
            supplier_ids=self.scope.supplier_ids,
        )

    def _validate_id(self, value: str, label: str) -> str:
        if not ID_PATTERN.fullmatch(value):
            raise HTTPException(status_code=422, detail=f"invalid {label}")
        return value

    def _owner_key(self, identity: EnterpriseIdentity) -> str:
        if self.authenticator is None:
            return identity.user_id
        return f"{identity.tenant_id}:{identity.user_id}"

    def _trusted_prompt(self, adapter: AGUIAdapter[Any, Any]) -> str:
        for message in reversed(adapter.messages):
            if not isinstance(message, ModelRequest):
                continue
            for part in reversed(message.parts):
                if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                    prompt = part.content.strip()
                    if not prompt:
                        raise HTTPException(status_code=422, detail="empty user prompt")
                    if len(prompt) > self.settings.max_prompt_characters:
                        raise HTTPException(
                            status_code=413, detail="prompt is too large"
                        )
                    adapter.messages.clear()
                    adapter.messages.append(ModelRequest(parts=[part]))
                    return prompt
        raise HTTPException(status_code=422, detail="one user prompt is required")

    async def run_agent(self, request: Request) -> Response:
        identity = self.authenticate(request)
        owner_id = self._owner_key(identity)
        try:
            content_length = int(request.headers.get("content-length") or 0)
        except ValueError as error:
            raise HTTPException(
                status_code=400, detail="invalid content-length header"
            ) from error
        if content_length > self.settings.max_request_bytes:
            raise HTTPException(status_code=413, detail="request is too large")
        try:
            adapter = await AGUIAdapter.from_request(
                request,
                agent=self.agent,
                manage_system_prompt="server",
                allow_uploaded_files=False,
                allowed_file_url_schemes=frozenset(),
                allowed_content_types=frozenset({"application/json"}),
            )
        except ValidationError as error:
            return Response(
                content=error.json(include_input=False),
                media_type="application/json",
                status_code=422,
            )
        # Tool definitions sent by the browser are presentation metadata only.
        # The server owns the executable tool allowlist; letting AG-UI add the
        # browser definitions as a second toolset both crosses that trust
        # boundary and collides with the server tools that share their names.
        adapter.run_input.tools.clear()
        self._trusted_prompt(adapter)
        conversation_id = self._validate_id(
            str(adapter.conversation_id or ""), "conversation ID"
        )
        run_id = self._validate_id(str(adapter.run_input.run_id), "run ID")
        try:
            self.store.get_or_create(conversation_id, owner_id)
            self.store.record_access(
                owner_id, "conversation", conversation_id, "agent_run"
            )
            history = self.store.history(conversation_id, owner_id)
            self.store.start_run(
                run_id, conversation_id, owner_id, self.settings.model_name
            )
        except SessionAccessDenied as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except RunReplayError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

        lock = self.conversation_locks.setdefault(conversation_id, asyncio.Lock())
        if lock.locked():
            self.store.finish_run(
                run_id,
                status="rejected",
                tool_calls=[],
                error_code="CONVERSATION_BUSY",
            )
            raise HTTPException(
                status_code=409, detail="conversation already has a run"
            )
        await lock.acquire()
        await self.semaphore.acquire()
        cancellation = CancellationToken()
        self.active_runs[run_id] = (owner_id, cancellation)
        allowed_tools = READ_TOOLS
        if self.proposal_service is not None and "followup_proposer" in identity.roles:
            allowed_tools |= FOLLOWUP_TOOLS
        deps = AgentDependencies(
            repository=self.repository,
            scope=AccessScope(
                identity.operating_company,
                identity.customer_ids,
                identity.supplier_ids,
            ),
            user_id=identity.user_id,
            allowed_tools=allowed_tools,
            proposal_service=self.proposal_service,
            conversation_id=conversation_id,
            run_id=run_id,
            tenant_id=identity.tenant_id,
        )
        completed = False

        async def on_complete(result: AgentRunResult[Any]) -> None:
            nonlocal completed
            completed = True
            self.store.save_history(conversation_id, owner_id, result.all_messages())
            usage = result.usage
            self.store.finish_run(
                run_id,
                status="succeeded",
                tool_calls=deps.tool_calls,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
            )

        async def on_cancel(cancelled: RunCancelled) -> None:
            nonlocal completed
            completed = True
            self.store.save_history(conversation_id, owner_id, cancelled.all_messages())
            self.store.finish_run(
                run_id,
                status="cancelled",
                tool_calls=deps.tool_calls,
                error_code="CANCELLED",
            )

        async def events() -> AsyncIterator[Any]:
            nonlocal completed
            try:
                async with asyncio.timeout(self.settings.run_timeout_seconds):
                    async for event in adapter.run_stream(
                        message_history=history,
                        conversation_id=conversation_id,
                        run_id=run_id,
                        deps=deps,
                        usage_limits=self.settings.usage_limits(),
                        cancellation_token=cancellation,
                        on_complete=on_complete,
                        on_cancel=on_cancel,
                    ):
                        if isinstance(event, RunErrorEvent) and not completed:
                            completed = True
                            self.store.finish_run(
                                run_id,
                                status="failed",
                                tool_calls=deps.tool_calls,
                                error_code=event.code or "AGENT_ERROR",
                            )
                        yield event
            except TimeoutError:
                completed = True
                cancellation.cancel()
                self.store.finish_run(
                    run_id,
                    status="failed",
                    tool_calls=deps.tool_calls,
                    error_code="LIMIT_EXCEEDED",
                )
                yield RunErrorEvent(
                    type=EventType.RUN_ERROR,
                    message="Agent run exceeded its time limit.",
                    code="LIMIT_EXCEEDED",
                )
            except asyncio.CancelledError:
                if not completed:
                    self.store.finish_run(
                        run_id,
                        status="cancelled",
                        tool_calls=deps.tool_calls,
                        error_code="CLIENT_DISCONNECTED",
                    )
                raise
            finally:
                self.active_runs.pop(run_id, None)
                self.semaphore.release()
                lock.release()

        return adapter.streaming_response(events())

    def conversation(self, request: Request, conversation_id: str) -> JSONResponse:
        identity = self.authenticate(request)
        owner_id = self._owner_key(identity)
        self._validate_id(conversation_id, "conversation ID")
        try:
            messages = self.store.public_history(conversation_id, owner_id)
        except SessionAccessDenied as error:
            self.store.record_access(
                owner_id,
                "conversation",
                conversation_id,
                "read_history",
                "denied",
            )
            raise HTTPException(status_code=403, detail=str(error)) from error
        self.store.record_access(
            owner_id, "conversation", conversation_id, "read_history"
        )
        return JSONResponse({"conversation_id": conversation_id, "messages": messages})

    def conversations(self, request: Request) -> JSONResponse:
        identity = self.authenticate(request)
        owner_id = self._owner_key(identity)
        self.store.record_access(owner_id, "conversation", "*", "list_history")
        return JSONResponse({"conversations": self.store.list_conversations(owner_id)})

    def delete_conversation(
        self, request: Request, conversation_id: str
    ) -> JSONResponse:
        identity = self.authenticate(request)
        owner_id = self._owner_key(identity)
        self._validate_id(conversation_id, "conversation ID")
        if request.headers.get("x-operion-intent") != "delete-conversation":
            raise HTTPException(
                status_code=403, detail="missing conversation deletion intent"
            )
        try:
            deleted = self.store.delete_conversation(conversation_id, owner_id)
        except SessionAccessDenied as error:
            self.store.record_access(
                owner_id,
                "conversation",
                conversation_id,
                "delete_history",
                "denied",
            )
            raise HTTPException(status_code=403, detail=str(error)) from error
        except ConversationBusyError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        if not deleted:
            raise HTTPException(status_code=404, detail="conversation was not found")
        return JSONResponse({"conversation_id": conversation_id, "deleted": True})

    def cancel_run(self, request: Request, run_id: str) -> JSONResponse:
        identity = self.authenticate(request)
        owner_id = self._owner_key(identity)
        self._validate_id(run_id, "run ID")
        active = self.active_runs.get(run_id)
        if active is None:
            try:
                stored = self.store.run(run_id, owner_id)
            except SessionAccessDenied as error:
                self.store.record_access(
                    owner_id, "agent_run", run_id, "cancel", "denied"
                )
                raise HTTPException(status_code=403, detail=str(error)) from error
            if stored is None:
                raise HTTPException(status_code=404, detail="run was not found")
            self.store.record_access(owner_id, "agent_run", run_id, "cancel")
            return JSONResponse({"run_id": run_id, "status": stored["status"]})
        active_owner, token = active
        if active_owner != owner_id:
            self.store.record_access(owner_id, "agent_run", run_id, "cancel", "denied")
            raise HTTPException(status_code=403, detail="run belongs to another user")
        token.cancel()
        self.store.record_access(owner_id, "agent_run", run_id, "cancel")
        return JSONResponse({"run_id": run_id, "status": "cancelling"})


def create_app(application: AgentApplication) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        for _, cancellation in application.active_runs.values():
            cancellation.cancel()

    app = FastAPI(title="Operion controlled Agent", version="0.4.0", lifespan=lifespan)
    origins = [
        item.strip()
        for item in os.environ.get(
            "OPERION_WEB_ORIGINS", "http://localhost:3000"
        ).split(",")
        if item.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Accept",
            "X-Operion-Intent",
        ],
    )

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "mode": (
                "controlled_followup_proposals"
                if application.proposal_service is not None
                else "read_only"
            ),
            "model": application.settings.model_name,
            "tools": sorted(application.allowed_tools),
        }

    @app.post("/api/agent")
    async def agent_endpoint(request: Request) -> Response:
        return await application.run_agent(request)

    @app.get("/api/conversations")
    async def conversations_endpoint(request: Request) -> JSONResponse:
        return application.conversations(request)

    @app.get("/api/conversations/{conversation_id}")
    async def conversation_endpoint(
        request: Request, conversation_id: str
    ) -> JSONResponse:
        return application.conversation(request, conversation_id)

    @app.delete("/api/conversations/{conversation_id}")
    async def delete_conversation_endpoint(
        request: Request, conversation_id: str
    ) -> JSONResponse:
        return application.delete_conversation(request, conversation_id)

    @app.post("/api/runs/{run_id}/cancel")
    async def cancel_endpoint(request: Request, run_id: str) -> JSONResponse:
        return application.cancel_run(request, run_id)

    return app


def application_from_environment() -> AgentApplication:
    repository = repository_from_environment()
    scope = scope_from_environment()
    proposal_service = None
    enterprise = os.environ.get("OPERION_ENVIRONMENT") == "enterprise"
    proposals_enabled = os.environ.get("OPERION_ENABLE_FOLLOWUP_PROPOSALS", "0") == "1"
    if (
        enterprise
        and proposals_enabled
        and os.environ.get("OPERION_WRITES_ENABLED") != "1"
    ):
        raise RuntimeError(
            "follow-up proposals require the enterprise write release gate"
        )
    if proposals_enabled:
        values = os.environ
        database_url = values.get("OPERION_ACTION_DATABASE_URL", "")
        assignee_id = values.get("OPERION_FOLLOWUP_ASSIGNEE_ID", "")
        twenty_key = values.get("TWENTY_API_KEY_READ_ONLY", "")
        erpnext_key = values.get("ERPNEXT_API_KEY_READ_ONLY", "")
        if not all((database_url, assignee_id, twenty_key, erpnext_key)):
            raise RuntimeError(
                "controlled proposals require the action database, fixed assignee, "
                "and both read-only business credentials"
            )
        proposal_service = FollowupProposalService(
            store=ActionStore(
                database_url,
                values.get("OPERION_ACTION_DATABASE_ROLE") or None,
            ),
            repository=repository,
            scope=scope,
            gateway=TwentyFollowupGateway(
                TwentyClient(
                    values.get("TWENTY_API_BASE_URL", "http://localhost:3000"),
                    twenty_key,
                ),
                ERPNextReadClient(
                    values.get("ERPNEXT_API_BASE_URL", "http://localhost:8080"),
                    erpnext_key,
                ),
            ),
            assignee_id=assignee_id,
            tenant_id=values.get("OPERION_ACTION_TENANT_ID", "operion-demo"),
        )
    authenticator = OIDCAuthenticator.from_environment() if enterprise else None
    return AgentApplication(
        settings=AgentSettings.from_environment(),
        repository=repository,
        scope=scope,
        store=ConversationStore(
            Path(os.environ.get("OPERION_SESSION_DB", "var/operion-agent.sqlite3"))
        ),
        token="" if enterprise else os.environ.get("OPERION_AGENT_TOKEN", ""),
        user_id=os.environ.get("OPERION_AGENT_USER_ID", "e2-demo-user"),
        tenant_id=os.environ.get("OPERION_ACTION_TENANT_ID", "operion-demo"),
        proposal_service=proposal_service,
        authenticator=authenticator,
    )


def main() -> None:
    host = os.environ.get("OPERION_AGENT_HOST", "127.0.0.1")
    port = int(os.environ.get("OPERION_AGENT_PORT", "8000"))
    uvicorn.run(create_app(application_from_environment()), host=host, port=port)


if __name__ == "__main__":
    main()
