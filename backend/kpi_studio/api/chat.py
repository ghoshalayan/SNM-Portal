"""Smart-analysis chatbot endpoints — Phase B1.

Endpoints:
  GET    /chat/sessions                      list (mine, newest first)
  POST   /chat/sessions                      create empty session
  GET    /chat/sessions/{id}                 detail with full message list
  PUT    /chat/sessions/{id}                 rename
  DELETE /chat/sessions/{id}                 soft delete
  POST   /chat/sessions/{id}/turn            send a prompt → run agent →
                                             persist + return user + assistant turns

Per-user — sessions are not shared in B1. Reuses the A7 NL→SQL agent
for the turn pipeline; insight generation + rolling-summary compaction
land in B3.
"""
from __future__ import annotations

import json
import logging
import threading
from typing import Any, Generator, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from kpi_studio import deps
from kpi_studio.models import KpiChatMessage, KpiChatSession
from kpi_studio.schemas import (
    ChatMessage, ChatSessionCreateRequest, ChatSessionDetail,
    ChatSessionListResponse, ChatSessionSummary, ChatSessionUpdateRequest,
    ChatTurnRequest, ChatTurnResponse, NlAgentStep,
)
from kpi_studio.services import chat_service

log = logging.getLogger(__name__)

# In-memory registry of cancel signals keyed by chat_session_id. The SSE
# turn endpoint registers an Event before kicking off the agent; the
# cancel endpoint sets it. Single-process / single-pod by design — chat
# sessions can't run concurrently within one user, and users typically
# stay pinned to one pod for the duration of a turn anyway.
_active_turn_cancels: dict[int, threading.Event] = {}
_active_turns_lock = threading.Lock()


def _user_id(user: Any) -> Optional[int]:
    for attr in ("user_id", "id", "userId"):
        v = getattr(user, attr, None)
        if isinstance(v, int):
            return v
    return None


def _company_id(user: Any) -> Optional[int]:
    cfg = deps.get_config()
    if cfg.tenant_resolver is None:
        return None
    try:
        return cfg.tenant_resolver(user)
    except Exception:
        return None


def _msg_to_payload(m: KpiChatMessage) -> ChatMessage:
    """Convert ORM row → API shape. ``agent_steps`` is stored as JSON
    so we Pydantic-validate it back into typed ``NlAgentStep`` objects
    for the response."""
    steps_raw = m.agent_steps or None
    steps_typed: Optional[list[NlAgentStep]] = None
    if steps_raw is not None:
        steps_typed = [NlAgentStep(**s) for s in steps_raw]

    return ChatMessage(
        chat_message_id=m.chat_message_id,
        chat_session_id=m.chat_session_id,
        role=m.role,
        kind=getattr(m, "kind", None) or "answer",
        content=m.content or "",
        sql=m.sql,
        rewritten_sql=m.rewritten_sql,
        result_columns=m.result_columns,
        result_rows=m.result_rows,
        chart_config=m.chart_config,  # type: ignore[arg-type]
        agent_steps=steps_typed,
        insight=m.insight,
        recommendations=list(m.recommendations) if m.recommendations else None,
        succeeded=m.succeeded,
        error=m.error,
        provider=m.provider,
        model=m.model,
        tokens=m.tokens,
        duration_ms=m.duration_ms,
        created_at=m.created_at,
    )


def _session_summary(session: KpiChatSession, count: int) -> ChatSessionSummary:
    last_at = session.messages[-1].created_at if session.messages else None
    return ChatSessionSummary(
        chat_session_id=session.chat_session_id,
        title=session.title,
        is_active=session.is_active,
        message_count=count,
        last_message_at=last_at,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


def _session_detail(session: KpiChatSession) -> ChatSessionDetail:
    return ChatSessionDetail(
        chat_session_id=session.chat_session_id,
        title=session.title,
        company_id=session.company_id,
        user_id=session.user_id,
        is_active=session.is_active,
        rolling_summary=session.rolling_summary,
        created_at=session.created_at,
        updated_at=session.updated_at,
        messages=[_msg_to_payload(m) for m in session.messages],
    )


def build_router() -> APIRouter:
    router = APIRouter()
    auth = deps.get_current_user
    db_dep = deps.get_metadata_db
    perm = deps.require_kpi_permission

    @router.get(
        "/sessions",
        response_model=ChatSessionListResponse,
        # Chat is gated to ``kpi:author`` — same code that protects the
        # KPI editor's "Generate from prompt", since it consumes tokens.
        dependencies=[Depends(perm("kpi:author"))],
    )
    def list_sessions(
        db: Session = Depends(db_dep),
        user: Any = Depends(auth),
        include_inactive: bool = Query(default=False),
        limit: int = Query(default=50, ge=1, le=200),
    ) -> ChatSessionListResponse:
        rows = chat_service.list_sessions(
            db, user_id=_user_id(user),
            include_inactive=include_inactive, limit=limit,
        )
        items = [_session_summary(s, c) for s, c in rows]
        return ChatSessionListResponse(items=items, total=len(items))

    @router.post(
        "/sessions",
        response_model=ChatSessionDetail,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(perm("kpi:author"))],
    )
    def create_session(
        payload: ChatSessionCreateRequest,
        db: Session = Depends(db_dep),
        user: Any = Depends(auth),
    ) -> ChatSessionDetail:
        sess = chat_service.create_session(
            db,
            user_id=_user_id(user),
            company_id=_company_id(user),
            title=payload.title,
        )
        # Reload via get_session so we get the messages relationship in a
        # consistent shape (empty list, not lazy-uninitialized).
        sess = chat_service.get_session(db, sess.chat_session_id, user_id=_user_id(user))
        return _session_detail(sess)  # type: ignore[arg-type]

    @router.get(
        "/sessions/{session_id}",
        response_model=ChatSessionDetail,
        dependencies=[Depends(perm("kpi:author"))],
    )
    def get_session(
        session_id: int,
        db: Session = Depends(db_dep),
        user: Any = Depends(auth),
    ) -> ChatSessionDetail:
        sess = chat_service.get_session(db, session_id, user_id=_user_id(user))
        if sess is None:
            # 404 not 403 — we don't leak the existence of other users' sessions.
            raise HTTPException(status_code=404, detail="Chat session not found.")
        return _session_detail(sess)

    @router.put(
        "/sessions/{session_id}",
        response_model=ChatSessionDetail,
        dependencies=[Depends(perm("kpi:author"))],
    )
    def rename_session(
        session_id: int,
        payload: ChatSessionUpdateRequest,
        db: Session = Depends(db_dep),
        user: Any = Depends(auth),
    ) -> ChatSessionDetail:
        sess = chat_service.get_session(db, session_id, user_id=_user_id(user))
        if sess is None:
            raise HTTPException(status_code=404, detail="Chat session not found.")
        if payload.title is not None:
            chat_service.update_session_title(db, sess, payload.title.strip())
        return _session_detail(sess)

    @router.delete(
        "/sessions/{session_id}",
        dependencies=[Depends(perm("kpi:author"))],
    )
    def delete_session(
        session_id: int,
        db: Session = Depends(db_dep),
        user: Any = Depends(auth),
    ) -> dict:
        sess = chat_service.get_session(db, session_id, user_id=_user_id(user))
        if sess is None:
            raise HTTPException(status_code=404, detail="Chat session not found.")
        chat_service.soft_delete_session(db, sess)
        return {"deleted": True, "chat_session_id": session_id}

    @router.post(
        "/sessions/{session_id}/turn",
        response_model=ChatTurnResponse,
        dependencies=[Depends(perm("kpi:author"))],
    )
    def send_turn(
        session_id: int,
        payload: ChatTurnRequest,
        db: Session = Depends(db_dep),
        user: Any = Depends(auth),
    ) -> ChatTurnResponse:
        sess = chat_service.get_session(db, session_id, user_id=_user_id(user))
        if sess is None:
            raise HTTPException(status_code=404, detail="Chat session not found.")

        cfg = deps.get_config()
        user_msg, assistant_msg = chat_service.run_turn(
            db, sess,
            prompt=payload.prompt,
            cfg=cfg,
            user_id=_user_id(user),
            company_id=_company_id(user),
        )
        return ChatTurnResponse(
            user_message=_msg_to_payload(user_msg),
            assistant_message=_msg_to_payload(assistant_msg),
        )

    @router.post(
        "/sessions/{session_id}/turn/stream",
        dependencies=[Depends(perm("kpi:author"))],
    )
    def send_turn_stream(
        session_id: int,
        payload: ChatTurnRequest,
        db: Session = Depends(db_dep),
        user: Any = Depends(auth),
    ):
        """Server-Sent Events variant of ``/turn`` that streams agent
        steps as they happen, then a final ``done`` event with the
        canonical message pair.

        Wire format (one SSE record per agent event):

            event: step
            data: {"type":"step","step":{...}}

            event: done
            data: {"type":"done","user_message":{...},"assistant_message":{...}}

            event: error
            data: {"type":"error","error":"..."}

        The agent runs in a worker thread (with its own DB session) so
        the event stream isn't blocked behind the synchronous LLM calls.
        Cancellation is delivered out-of-band via
        ``POST /sessions/{id}/turn/cancel``.
        """
        # Validate session ownership via the request-thread session BEFORE
        # spawning the worker. The worker re-fetches in its own session
        # to avoid cross-thread SQLAlchemy use.
        sess = chat_service.get_session(db, session_id, user_id=_user_id(user))
        if sess is None:
            raise HTTPException(status_code=404, detail="Chat session not found.")

        cfg = deps.get_config()
        cancel_event = threading.Event()
        with _active_turns_lock:
            # Replace any stale entry from a previous turn that wasn't
            # cleaned up — only one live turn per session at a time.
            prior = _active_turn_cancels.get(session_id)
            if prior is not None:
                prior.set()
            _active_turn_cancels[session_id] = cancel_event

        captured_user_id = _user_id(user)
        captured_company_id = _company_id(user)

        def event_stream() -> Generator[bytes, None, None]:
            """Format each event as an SSE record. Encoded as bytes so
            uvicorn can write straight to the socket."""
            try:
                for evt in chat_service.run_turn_streaming(
                    cfg=cfg,
                    session_factory=cfg.metadata_session_factory,
                    chat_session_id=session_id,
                    prompt=payload.prompt,
                    user_id=captured_user_id,
                    company_id=captured_company_id,
                    cancel_event=cancel_event,
                ):
                    name = evt.get("type", "message")
                    yield f"event: {name}\ndata: {json.dumps(evt, default=str)}\n\n".encode("utf-8")
            except Exception as exc:  # noqa: BLE001
                log.exception("kpi_studio.chat: stream handler crashed")
                payload_err = {"type": "error", "error": str(exc)}
                yield f"event: error\ndata: {json.dumps(payload_err)}\n\n".encode("utf-8")
            finally:
                with _active_turns_lock:
                    # Only clear if it's still the same Event we registered;
                    # a fresh turn may have replaced it already.
                    if _active_turn_cancels.get(session_id) is cancel_event:
                        _active_turn_cancels.pop(session_id, None)

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                # Disable nginx-style proxy buffering so events flush in
                # real time rather than batching at gateway boundaries.
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    @router.post(
        "/sessions/{session_id}/turn/cancel",
        dependencies=[Depends(perm("kpi:author"))],
    )
    def cancel_turn(
        session_id: int,
        db: Session = Depends(db_dep),
        user: Any = Depends(auth),
    ) -> dict:
        """Signal the in-flight streaming turn for this session to abort.

        Idempotent and safe to call when no turn is in flight; returns
        ``{"cancelled": false}`` in that case so the client can decide
        whether to surface a notice."""
        # Verify session ownership before flipping the cancel flag — we
        # don't want a malicious user to grief another user's chat.
        sess = chat_service.get_session(db, session_id, user_id=_user_id(user))
        if sess is None:
            raise HTTPException(status_code=404, detail="Chat session not found.")
        with _active_turns_lock:
            evt = _active_turn_cancels.get(session_id)
        if evt is None:
            return {"cancelled": False, "chat_session_id": session_id}
        evt.set()
        return {"cancelled": True, "chat_session_id": session_id}

    return router
