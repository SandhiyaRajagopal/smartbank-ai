"""Helpers shared by all agent tool sets.

How tools work: each tool is a normal Python function. LangChain reads its name,
docstring and type hints and sends them to Gemini as a JSON schema. Gemini replies
with "call tool X with args Y"; our agent loop runs the function and feeds the
result back to the model.

Security: tools are built per request by a factory that *closes over* the logged-in
customer's id. The id is never a tool argument, so the LLM cannot ask for another
customer's data even if a user tries prompt injection.
"""
import json
from typing import Callable

from langchain_core.tools import StructuredTool

from ..db.session import db_session
from ..services.banking import BankingError


def to_json(data) -> str:
    return json.dumps(data, default=str, ensure_ascii=False)


def make_tool(fn: Callable, *, requires_confirmation: bool = False) -> StructuredTool:
    """Wrap fn as a tool. Banking/validation errors are returned to the model as
    {"error": ...} so it can explain or retry instead of crashing the request."""
    def safe(**kwargs):
        try:
            return to_json(fn(**kwargs))
        except (BankingError, ValueError) as e:
            return to_json({"error": str(e)})

    # the argument schema is inferred from fn's signature; `safe` is what actually runs
    return StructuredTool(
        name=fn.__name__,
        description=(fn.__doc__ or "").strip(),
        args_schema=StructuredTool.from_function(fn).args_schema,
        func=safe,
        metadata={"requires_confirmation": requires_confirmation},
    )


def in_session(fn: Callable) -> Callable:
    """Run a service call inside a committed DB session."""
    def wrapper(*args, **kwargs):
        with db_session() as db:
            return fn(db, *args, **kwargs)
    return wrapper
