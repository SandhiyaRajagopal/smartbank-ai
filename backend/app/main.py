"""FastAPI application entry point.

Run locally:   uvicorn backend.app.main:app --reload
Startup: create tables + seed demo data -> open the LangGraph checkpointer -> build the graph
-> start the live transaction simulator -> build the RAG index in the background.
"""
import asyncio
import logging
import sqlite3
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from langgraph.checkpoint.sqlite import SqliteSaver

from .agents.graph import build_graph
from .api import auth, banking_routes, chat, ws
from .config import settings
from .db.seed import seed
from .llm import get_llm
from .rag.retriever import get_index
from .realtime.hub import hub
from .realtime.simulator import run_simulator

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("smartbank")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if seed():
        log.info("seeded demo database")
    # Checkpointer: saves graph state after every node -> conversation memory + resumable interrupts
    conn = sqlite3.connect(settings.checkpoint_db, check_same_thread=False)
    app.state.graph = build_graph(get_llm, checkpointer=SqliteSaver(conn))
    hub.loop = asyncio.get_running_loop()

    tasks = [asyncio.create_task(asyncio.to_thread(get_index().build))]
    if settings.simulator_enabled:
        tasks.append(asyncio.create_task(run_simulator()))
    log.info("SmartBank AI ready (model=%s, llm_configured=%s)", settings.gemini_model, settings.llm_configured)
    yield
    for t in tasks:
        t.cancel()
    conn.close()


app = FastAPI(title="SmartBank AI", version="1.0.0", lifespan=lifespan)

# Vite dev server runs on :5173 during development; in Docker the UI is served by this app (same origin).
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def add_trace_id(request: Request, call_next):
    """Correlation id: one id ties together the HTTP request, audit log rows and LangSmith trace."""
    request.state.trace_id = request.headers.get("X-Trace-Id") or uuid.uuid4().hex[:16]
    response = await call_next(request)
    response.headers["X-Trace-Id"] = request.state.trace_id
    return response


app.include_router(auth.router)
app.include_router(banking_routes.router)
app.include_router(chat.router)
app.include_router(ws.router)


@app.get("/api/health")
def health():
    index = get_index()
    return {"status": "ok", "llm_configured": settings.llm_configured, "model": settings.gemini_model,
            "rag_mode": index.mode, "policy_chunks": len(index.chunks)}


# ---- serve the built React app (production / Docker) ----
_dist = Path(settings.frontend_dist)
if (_dist / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        file = _dist / full_path
        if full_path and file.is_file() and _dist in file.resolve().parents:
            return FileResponse(file)
        return FileResponse(_dist / "index.html")  # client-side routing fallback
