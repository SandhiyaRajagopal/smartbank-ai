"""API tests: auth, dashboard data, streaming chat with confirmation, user isolation and WebSocket push."""
import json

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

from backend.app.agents.graph import build_graph
from backend.app.agents.supervisor import RouteDecision, RouteStep
from backend.app.config import settings
from backend.app.db.seed import DEMO_PASSWORD
from backend.app.main import app
from tests.conftest import FakeLLM


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def login(client, who="arjun"):
    r = client.post("/api/auth/login", json={"email": f"{who}@smartbank.demo", "password": DEMO_PASSWORD})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def sse_events(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


@pytest.fixture
def llm_ready(monkeypatch):
    monkeypatch.setattr(settings, "google_api_key", "test-key")


def use_fake_llm(llm):
    app.state.graph = build_graph(lambda: llm, checkpointer=InMemorySaver())


def test_health(client):
    r = client.get("/api/health")
    assert r.json()["status"] == "ok"
    assert r.headers["X-Trace-Id"]


def test_login_rejects_wrong_password(client):
    r = client.post("/api/auth/login", json={"email": "priya@smartbank.demo", "password": "wrong"})
    assert r.status_code == 401


def test_endpoints_require_login(client):
    assert client.get("/api/overview").status_code == 401
    assert client.get("/api/overview", headers={"Authorization": "Bearer junk"}).status_code == 401


def test_overview_returns_only_own_data(client):
    data = client.get("/api/overview", headers=login(client, "priya")).json()
    assert data["profile"]["name"] == "Priya Sharma"
    assert data["credit"]["score"] == 792
    assert data["accounts"][0]["account_number"].startswith("XXXX")


def test_demo_accounts_listed(client):
    assert len(client.get("/api/auth/demo-accounts").json()) == 4


def test_chat_without_llm_key_gives_clear_error(client):
    r = client.post("/api/chat", json={"message": "hi"}, headers=login(client))
    assert r.status_code == 503 and "GOOGLE_API_KEY" in r.json()["detail"]


def test_chat_streams_trace_and_final_answer(client, llm_ready):
    use_fake_llm(FakeLLM(
        route=RouteDecision(intent="balance", reasoning="r", steps=[RouteStep(agent="customer", task="balance")]),
        responses=[AIMessage("You have ₹7,54,960.")]))
    r = client.post("/api/chat", json={"message": "balance?", "conversation_id": "c1"}, headers=login(client))
    events = sse_events(r.text)
    names = [e for e, _ in events]
    assert names[:3] == ["trace", "trace", "trace"] and names[-2:] == ["final", "done"]
    assert events[-2][1]["reply"] == "You have ₹7,54,960."


def test_confirmation_flow_over_api(client, llm_ready):
    headers = login(client)
    cards = client.get("/api/overview", headers=headers).json()["cards"]
    debit = next(c for c in cards if c["type"] == "DEBIT")
    use_fake_llm(FakeLLM(
        route=RouteDecision(intent="fraud", reasoning="r", steps=[RouteStep(agent="fraud", task="block card")]),
        responses=[AIMessage("", tool_calls=[{"name": "block_card", "id": "1",
                                              "args": {"card_id": debit["id"], "reason": "fraud"}}]),
                   AIMessage("Please confirm blocking your card.")]))

    events = sse_events(client.post("/api/chat", json={"message": "block my card", "conversation_id": "c2"},
                                    headers=headers).text)
    confirmation = next(d for e, d in events if e == "confirmation")
    assert confirmation["tool"] == "block_card"

    # pending action survives a page reload, and a new message is refused until it's answered
    assert client.get("/api/chat/history?conversation_id=c2", headers=headers).json()["pending_confirmation"]
    assert client.post("/api/chat", json={"message": "hi", "conversation_id": "c2"}, headers=headers).status_code == 409

    events = sse_events(client.post("/api/chat/confirm", json={"conversation_id": "c2", "approved": True},
                                    headers=headers).text)
    assert "blocked" in next(d for e, d in events if e == "final")["reply"]
    assert [e for e, d in events if e == "trace"] == ["trace", "trace"]  # only the new steps: approval + aggregate
    cards = client.get("/api/overview", headers=headers).json()["cards"]
    assert next(c for c in cards if c["id"] == debit["id"])["status"] == "BLOCKED"

    client.post("/api/demo/reset-cards", headers=headers)


def test_conversations_are_isolated_per_user(client, llm_ready):
    use_fake_llm(FakeLLM(route=RouteDecision(intent="g", reasoning="r", steps=[], direct_response="Hello!")))
    client.post("/api/chat", json={"message": "secret question", "conversation_id": "shared"},
                headers=login(client, "arjun"))
    other = client.get("/api/chat/history?conversation_id=shared", headers=login(client, "priya")).json()
    assert other["messages"] == []


def test_invalid_conversation_id_rejected(client, llm_ready):
    r = client.post("/api/chat", json={"message": "hi", "conversation_id": "../../x"}, headers=login(client))
    assert r.status_code == 422


def test_websocket_pushes_live_suspicious_transaction(client):
    headers = login(client, "priya")
    token = headers["Authorization"].split()[1]
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"token": token})
        assert ws.receive_json()["type"] == "ready"
        txn = client.post("/api/demo/simulate", json={"suspicious": True}, headers=headers).json()
        assert txn["risk_level"] == "HIGH"
        received = [ws.receive_json()["type"] for _ in range(3)]
        assert received == ["transaction", "accounts", "alert"]


def test_websocket_rejects_bad_token(client):
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect) as closed:
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"token": "bad"})
            ws.receive_json()
    assert closed.value.code == 4401
