"""Chat endpoints - the bridge between the web app and the LangGraph multi-agent workflow.

Responses are streamed with Server-Sent Events (SSE): as each graph node finishes, its
trace steps are sent immediately, so the UI shows "Supervisor routed to Fraud Agent",
"Fraud Agent called scan_suspicious_transactions" ... live, before the final answer.

Event types:  trace | confirmation | final | error | done
"""
import json
import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from langgraph.types import Command
from pydantic import BaseModel, Field

from ..audit import audit
from ..config import settings
from ..db.models import User
from ..agents.graph import new_turn_input
from .deps import chat_limiter, current_user, trace_id

log = logging.getLogger("smartbank.chat")
router = APIRouter(prefix="/api/chat", tags=["chat"])
CONVERSATION_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: str = "default"


class ConfirmRequest(BaseModel):
    conversation_id: str = "default"
    approved: bool


def _config(request: Request, user: User, conversation_id: str) -> dict:
    if not CONVERSATION_ID.match(conversation_id):
        raise HTTPException(422, "Invalid conversation id")
    # The thread id is namespaced by user, so nobody can read or resume another user's conversation.
    thread_id = f"user{user.id}:{conversation_id}"
    return {
        "configurable": {"thread_id": thread_id},
        # visible in LangSmith: filter traces by user, conversation or request trace id
        "run_name": "smartbank_chat",
        "tags": ["smartbank", f"user:{user.id}"],
        "metadata": {"user_id": user.id, "conversation_id": conversation_id, "trace_id": trace_id(request)},
    }


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str, ensure_ascii=False)}\n\n"


def _friendly_error(e: Exception) -> str:
    text = str(e)
    if "429" in text or "RESOURCE_EXHAUSTED" in text or "quota" in text.lower():
        return "The AI model is receiving too many requests right now (rate limit). Please wait a moment and retry."
    if "API key" in text or "API_KEY" in text or "PERMISSION_DENIED" in text:
        return "The AI model rejected the API key. Check GOOGLE_API_KEY in your .env file."
    if "not found" in text.lower() and "model" in text.lower():
        return f"The configured Gemini model '{settings.gemini_model}' was not found. Check GEMINI_MODEL in .env."
    return "Something went wrong while processing your request. Please try again."


def _stream(graph, payload, config: dict, user_id: int, tid: str):
    current = graph.get_state(config).values
    sent = len(current.get("trace", [])) if isinstance(payload, Command) else 0
    final = None
    try:
        for chunk in graph.stream(payload, config, stream_mode="updates"):
            for node, update in chunk.items():
                if node == "__interrupt__":
                    yield _sse("confirmation", update[0].value)
                    continue
                if not update:
                    continue
                trace = update.get("trace")
                if trace is not None:
                    for item in trace[sent:]:
                        yield _sse("trace", item)
                    sent = len(trace)
                if node == "aggregate":
                    final = update.get("final")
        if final is not None:
            yield _sse("final", {"reply": final})
    except Exception as e:
        log.exception("chat stream failed")
        audit(tid, "error", {"error": str(e)[:500]}, user_id=user_id)
        yield _sse("error", {"message": _friendly_error(e)})
    yield _sse("done", {"trace_id": tid})


def _require_llm():
    if not settings.llm_configured:
        raise HTTPException(503, "The AI assistant is not configured yet: add GOOGLE_API_KEY to the .env file "
                                 "and restart the server.")


@router.post("")
def chat(body: ChatRequest, request: Request, user: User = Depends(current_user)):
    _require_llm()
    chat_limiter.check(user.id)
    graph = request.app.state.graph
    config = _config(request, user, body.conversation_id)
    if graph.get_state(config).interrupts:
        raise HTTPException(409, "Please confirm or cancel the pending action first.")
    tid = trace_id(request)
    audit(tid, "chat_request", {"chars": len(body.message), "conversation_id": body.conversation_id},
          user_id=user.id)
    payload = new_turn_input(body.message, user.customer_id, tid)
    return StreamingResponse(_stream(graph, payload, config, user.id, tid), media_type="text/event-stream")


@router.post("/confirm")
def confirm(body: ConfirmRequest, request: Request, user: User = Depends(current_user)):
    _require_llm()
    graph = request.app.state.graph
    config = _config(request, user, body.conversation_id)
    if not graph.get_state(config).interrupts:
        raise HTTPException(409, "There is no pending action to confirm.")
    tid = trace_id(request)
    payload = Command(resume={"approved": body.approved})
    return StreamingResponse(_stream(graph, payload, config, user.id, tid), media_type="text/event-stream")


@router.get("/history")
def history(request: Request, conversation_id: str = "default", user: User = Depends(current_user)):
    """Restores a conversation after a page reload (from the checkpointer), incl. a pending confirmation."""
    snapshot = request.app.state.graph.get_state(_config(request, user, conversation_id))
    messages = [{"role": "user" if m.type == "human" else "assistant", "content": m.text}
                for m in snapshot.values.get("messages", []) if m.type in ("human", "ai")]
    pending = snapshot.interrupts[0].value if snapshot.interrupts else None
    if pending:
        messages.append({"role": "assistant", "content": pending.get("message", "")})
    return {"messages": messages, "pending_confirmation": pending}
