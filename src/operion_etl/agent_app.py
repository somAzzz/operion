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

from .agent_runtime import (
    AgentDependencies,
    AgentSettings,
    create_operion_agent,
    repository_from_environment,
    scope_from_environment,
)
from .read_tools import AccessScope, CanonicalRepository
from .session_store import (
    ConversationStore,
    RunReplayError,
    SessionAccessDenied,
)

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
        agent: Agent[AgentDependencies, str] | None = None,
    ) -> None:
        if not token:
            raise RuntimeError("OPERION_AGENT_TOKEN is required")
        self.settings = settings
        self.repository = repository
        self.scope = scope
        self.store = store
        self.token = token
        self.user_id = user_id
        self.agent = agent or create_operion_agent(settings)
        self.semaphore = asyncio.Semaphore(settings.max_concurrent_runs)
        self.conversation_locks: dict[str, asyncio.Lock] = {}
        self.active_runs: dict[str, tuple[str, CancellationToken]] = {}

    def authenticate(self, request: Request) -> str:
        authorization = request.headers.get("authorization", "")
        expected = f"Bearer {self.token}"
        if not secrets.compare_digest(authorization, expected):
            raise HTTPException(status_code=401, detail="invalid agent credential")
        return self.user_id

    def _validate_id(self, value: str, label: str) -> str:
        if not ID_PATTERN.fullmatch(value):
            raise HTTPException(status_code=422, detail=f"invalid {label}")
        return value

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
        owner_id = self.authenticate(request)
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
        self._trusted_prompt(adapter)
        conversation_id = self._validate_id(
            str(adapter.conversation_id or ""), "conversation ID"
        )
        run_id = self._validate_id(str(adapter.run_input.run_id), "run ID")
        try:
            self.store.get_or_create(conversation_id, owner_id)
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
        deps = AgentDependencies(
            repository=self.repository,
            scope=self.scope,
            user_id=owner_id,
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
        owner_id = self.authenticate(request)
        self._validate_id(conversation_id, "conversation ID")
        try:
            messages = self.store.public_history(conversation_id, owner_id)
        except SessionAccessDenied as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        return JSONResponse({"conversation_id": conversation_id, "messages": messages})

    def cancel_run(self, request: Request, run_id: str) -> JSONResponse:
        owner_id = self.authenticate(request)
        self._validate_id(run_id, "run ID")
        active = self.active_runs.get(run_id)
        if active is None:
            try:
                stored = self.store.run(run_id, owner_id)
            except SessionAccessDenied as error:
                raise HTTPException(status_code=403, detail=str(error)) from error
            if stored is None:
                raise HTTPException(status_code=404, detail="run was not found")
            return JSONResponse({"run_id": run_id, "status": stored["status"]})
        active_owner, token = active
        if active_owner != owner_id:
            raise HTTPException(status_code=403, detail="run belongs to another user")
        token.cancel()
        return JSONResponse({"run_id": run_id, "status": "cancelling"})


def create_app(application: AgentApplication) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        for _, cancellation in application.active_runs.values():
            cancellation.cancel()

    app = FastAPI(title="Operion read-only Agent", version="0.2.0", lifespan=lifespan)
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
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type", "Accept"],
    )

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "mode": "read_only",
            "model": application.settings.model_name,
            "tools": ["get_customer_overview", "check_fulfillment"],
        }

    @app.post("/api/agent")
    async def agent_endpoint(request: Request) -> Response:
        return await application.run_agent(request)

    @app.get("/api/conversations/{conversation_id}")
    async def conversation_endpoint(
        request: Request, conversation_id: str
    ) -> JSONResponse:
        return application.conversation(request, conversation_id)

    @app.post("/api/runs/{run_id}/cancel")
    async def cancel_endpoint(request: Request, run_id: str) -> JSONResponse:
        return application.cancel_run(request, run_id)

    return app


def application_from_environment() -> AgentApplication:
    return AgentApplication(
        settings=AgentSettings.from_environment(),
        repository=repository_from_environment(),
        scope=scope_from_environment(),
        store=ConversationStore(
            Path(os.environ.get("OPERION_SESSION_DB", "var/operion-agent.sqlite3"))
        ),
        token=os.environ.get("OPERION_AGENT_TOKEN", ""),
        user_id=os.environ.get("OPERION_AGENT_USER_ID", "e2-demo-user"),
    )


def main() -> None:
    host = os.environ.get("OPERION_AGENT_HOST", "127.0.0.1")
    port = int(os.environ.get("OPERION_AGENT_PORT", "8000"))
    uvicorn.run(create_app(application_from_environment()), host=host, port=port)


if __name__ == "__main__":
    main()
