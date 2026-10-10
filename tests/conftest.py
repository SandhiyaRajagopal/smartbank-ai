"""Test setup: an isolated, freshly seeded SQLite database and LangSmith tracing off.

Environment variables are set *before* the app is imported, because config.py
reads them at import time (and load_dotenv never overrides existing variables).
"""
import os
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="smartbank_test_"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_tmp / 'test.db').as_posix()}"
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["GOOGLE_API_KEY"] = ""

import pytest  # noqa: E402

from backend.app.db.seed import seed  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def seeded_db():
    seed(reset=True)
    yield


class FakeLLM:
    """Stands in for Gemini. Returns a preset routing decision for the supervisor and
    a scripted sequence of AIMessages (text or tool calls) for agents/aggregator."""

    def __init__(self, route=None, responses=(), fail_routing=False):
        self.route = route
        self.responses = list(responses)
        self.fail_routing = fail_routing
        self.invocations = 0

    def with_structured_output(self, schema):
        llm = self

        class _Router:
            def invoke(self, messages):
                if llm.fail_routing:
                    raise ConnectionError("simulated outage")
                return llm.route

        return _Router()

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        self.invocations += 1
        if not self.responses:
            raise AssertionError("FakeLLM ran out of scripted responses")
        return self.responses.pop(0)
