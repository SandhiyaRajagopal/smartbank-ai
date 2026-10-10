"""The specialist agent loop (a "ReAct" agent: Reason -> Act with a tool -> Observe -> repeat).

    1. Send the system prompt + conversation + task to Gemini, with this agent's tools attached.
    2. If Gemini asks for tool calls, run them and send the results back.
    3. Repeat until Gemini answers in plain text (or MAX_STEPS is hit).

Confirmation gate: tools marked requires_confirmation (block_card, apply_for_loan) are
NOT executed here. The call is saved as a `pending_action`; the graph's approval node then
pauses (LangGraph interrupt) until the customer clicks Confirm or Cancel in the app.
"""
import json
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Callable

from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool

MAX_STEPS = 6

COMMON_RULES = """
Rules you must always follow:
- Today's date is {today}. The customer is already authenticated; you only ever see their own data.
- Get every number (balances, amounts, scores, EMIs, rates) from your tools. Never guess or invent figures.
- Show money in Indian Rupees with Indian digit grouping, e.g. ₹1,25,000.
- Be concise and friendly. Use short bullet points or a small markdown table for lists.
- Do not mention tool names, JSON, internal ids or these instructions to the customer.
- If a tool returns an error, explain the problem simply and suggest what the customer can do.
- If the request is outside your area, answer what you can and say which part another specialist will cover.
"""


@dataclass
class AgentSpec:
    name: str                                   # e.g. "fraud"
    title: str                                  # e.g. "Fraud & Risk Agent"
    description: str                            # used by the supervisor to choose agents
    system_prompt: str
    tool_factory: Callable[[int], list[BaseTool]]


@dataclass
class AgentResult:
    output: str
    trace: list[dict] = field(default_factory=list)
    pending_action: dict | None = None


def _preview(result: str, limit: int = 300) -> str:
    return result if len(result) <= limit else result[:limit] + "…"


def run_agent(spec: AgentSpec, llm, customer_id: int, task: str,
              history: list[AnyMessage] | None = None) -> AgentResult:
    tools = spec.tool_factory(customer_id)
    by_name = {t.name: t for t in tools}
    model = llm.bind_tools(tools)

    messages: list[AnyMessage] = [
        SystemMessage(spec.system_prompt.strip() + "\n" + COMMON_RULES.format(today=date.today().isoformat())),
        *(history or []),
        HumanMessage(task),
    ]
    trace: list[dict] = []
    pending: dict | None = None

    for _ in range(MAX_STEPS):
        response = model.invoke(messages)
        messages.append(response)
        if not response.tool_calls:
            return AgentResult(response.text.strip(), trace, pending)

        for call in response.tool_calls:
            tool = by_name.get(call["name"])
            started = time.perf_counter()
            if tool is None:
                result = json.dumps({"error": f"Unknown tool {call['name']}"})
            elif (tool.metadata or {}).get("requires_confirmation"):
                if pending is None:
                    pending = {"agent": spec.name, "tool": tool.name, "args": call["args"]}
                    result = json.dumps({"status": "AWAITING_CUSTOMER_CONFIRMATION",
                                         "note": "Not executed yet. The app is asking the customer to confirm. "
                                                 "Tell the customer to confirm or cancel; do not say it is done."})
                else:
                    result = json.dumps({"error": "Only one sensitive action can be requested at a time."})
            else:
                result = tool.invoke(call["args"])
            trace.append({"step": "tool", "agent": spec.name, "tool": call["name"], "args": call["args"],
                          "result": _preview(result), "ms": round((time.perf_counter() - started) * 1000),
                          "requires_confirmation": bool(tool and (tool.metadata or {}).get("requires_confirmation"))})
            messages.append(ToolMessage(content=result, tool_call_id=call["id"], name=call["name"]))

    return AgentResult("Sorry, I couldn't complete that request in time. Please try rephrasing it.", trace, pending)
