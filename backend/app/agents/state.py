"""The shared state that flows through the LangGraph workflow.

Every node receives this dict and returns only the keys it wants to change.
`messages` uses the add_messages reducer, so new messages are *appended* (that's
the conversation memory kept by the checkpointer); every other key is simply
overwritten. The API resets the per-turn keys at the start of each new message.
"""
from typing import Annotated, Any, Optional, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class BankState(TypedDict, total=False):
    # conversation memory (persisted across turns by the checkpointer)
    messages: Annotated[list[AnyMessage], add_messages]
    # who is asking - always taken from the login session, never from the LLM
    customer_id: int
    trace_id: str

    # ---- per-turn working state ----
    blocked: bool                      # guardrail refused the message
    plan: dict[str, Any]               # the supervisor's routing decision
    queue: list[dict[str, str]]        # remaining {agent, task} steps to run
    agent_outputs: dict[str, str]      # agent name -> its answer
    pending_action: Optional[dict]     # sensitive tool call awaiting customer confirmation
    trace: list[dict[str, Any]]        # step-by-step log shown in the UI's Agent Trace panel
    final: str                         # the reply sent back to the customer
