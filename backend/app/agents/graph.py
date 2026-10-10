"""The multi-agent workflow as a LangGraph state machine.

    START -> guardrail --(blocked)--------------------------------------> aggregate -> END
                 |
                 v
             supervisor --> [dispatch] --> customer / fraud / credit --> [dispatch] ... --> aggregate -> END
                                                    |
                                          (sensitive tool requested)
                                                    v
                                                approval  <- pauses with interrupt() until the
                                                    |        customer clicks Confirm / Cancel
                                                    v
                                               [dispatch]

[dispatch] is a conditional edge: it sends the state to the next agent in the supervisor's
queue, or to the aggregator when the queue is empty.

A checkpointer saves the state after every node, keyed by thread_id. That gives us
(1) conversation memory across messages and (2) the ability to pause at interrupt()
and resume later - even after a server restart.
"""
import json
import time
from typing import Callable

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from .. import guardrails
from ..audit import audit
from ..db.session import db_session
from ..services import banking
from .base import run_agent
from .specialists import SPECIALISTS
from .state import BankState
from .supervisor import route

HISTORY_MESSAGES = 8  # how many past messages agents see (keeps prompts small and cheap)


def _ms(start: float) -> int:
    return round((time.perf_counter() - start) * 1000)


def _history(state: BankState) -> list[AnyMessage]:
    """Past conversation turns (excluding the current question), text only."""
    msgs = [m for m in state.get("messages", []) if isinstance(m, (HumanMessage, AIMessage))]
    return msgs[:-1][-HISTORY_MESSAGES:]


def describe_action(customer_id: int, action: dict) -> str:
    """Human-readable summary shown in the confirmation dialog."""
    args = action["args"]
    if action["tool"] == "block_card":
        with db_session() as db:
            card = next((c for c in banking.list_cards(db, customer_id) if c["id"] == args.get("card_id")), None)
        label = f"{card['network']} {card['type'].lower()} card {card['number']}" if card else f"card #{args.get('card_id')}"
        return f"Block your {label}. Reason: {args.get('reason', 'not given')}."
    if action["tool"] == "apply_for_loan":
        return (f"Submit a {str(args.get('loan_type', '')).title()} loan application for "
                f"₹{float(args.get('amount', 0)):,.0f} over {args.get('tenure_months')} months.")
    return f"Run {action['tool']} with {args}"


def build_graph(llm_factory: Callable, checkpointer=None):
    # ---------------- nodes ----------------
    def guardrail_node(state: BankState) -> dict:
        start = time.perf_counter()
        last = state["messages"][-1]
        result = guardrails.check_input(last.text)
        step = {"step": "guardrail", "allowed": result.allowed, "reason": result.reason,
                "pii_masked": result.pii_found, "ms": _ms(start)}
        update: dict = {"trace": [*state.get("trace", []), step]}
        if result.pii_found:
            # same message id -> add_messages *replaces* it, so raw PII never reaches the LLM or memory
            update["messages"] = [HumanMessage(result.text, id=last.id)]
            audit(state.get("trace_id"), "pii_masked", {"types": result.pii_found})
        if not result.allowed:
            update.update(blocked=True, final=guardrails.REFUSAL)
            audit(state.get("trace_id"), "guardrail_block", {"reason": result.reason})
        return update

    def supervisor_node(state: BankState) -> dict:
        start = time.perf_counter()
        decision, fallback = route(llm_factory(), _history(state) + [state["messages"][-1]])
        plan = decision.model_dump()
        audit(state.get("trace_id"), "routing", {**plan, "fallback": fallback})
        step = {"step": "supervisor", "intent": decision.intent, "route": [s.agent for s in decision.steps],
                "tasks": [s.task for s in decision.steps], "reasoning": decision.reasoning,
                "fallback": fallback, "ms": _ms(start)}
        update = {"plan": plan, "queue": [s.model_dump() for s in decision.steps],
                  "trace": [*state.get("trace", []), step]}
        if not decision.steps:
            update["final"] = decision.direct_response or ""
        return update

    def make_agent_node(name: str):
        spec = SPECIALISTS[name]

        def agent_node(state: BankState) -> dict:
            start = time.perf_counter()
            step, *rest = state["queue"]
            result = run_agent(spec, llm_factory(), state["customer_id"], step["task"], _history(state))
            outputs = {**state.get("agent_outputs", {}), name: result.output}
            trace = [*state.get("trace", []), *result.trace,
                     {"step": "agent", "agent": name, "title": spec.title, "task": step["task"],
                      "tools_used": [t["tool"] for t in result.trace], "ms": _ms(start)}]
            update = {"queue": rest, "agent_outputs": outputs, "trace": trace}
            if result.pending_action:
                update["pending_action"] = {
                    **result.pending_action,
                    "summary": describe_action(state["customer_id"], result.pending_action),
                }
            return update

        return agent_node

    def approval_node(state: BankState) -> dict:
        """Human-in-the-loop. interrupt() saves the state and stops the graph; the API returns
        the payload to the UI. When the customer answers, the graph is resumed with
        Command(resume={"approved": True/False}) and interrupt() returns that value."""
        action = state["pending_action"]
        decision = interrupt({"type": "confirmation_required", **action,
                              "message": state["agent_outputs"].get(action["agent"], "")})
        approved = bool(decision.get("approved")) if isinstance(decision, dict) else bool(decision)

        start = time.perf_counter()
        if approved:
            tool = next(t for t in SPECIALISTS[action["agent"]].tool_factory(state["customer_id"])
                        if t.name == action["tool"])
            result = json.loads(tool.invoke(action["args"]))
            if "error" in result:
                note = f"⚠️ The action could not be completed: {result['error']}"
            elif action["tool"] == "block_card":
                note = f"✅ Done - your card {result['number']} is now **blocked**. A replacement will be sent in 5-7 working days."
            elif action["tool"] == "apply_for_loan":
                note = (f"✅ Your loan application **{result['application_id']}** has been submitted "
                        f"(EMI ₹{result['emi']:,.0f} at {result['interest_rate']}% p.a.).")
            else:
                note = "✅ Done."
        else:
            result, note = {"status": "CANCELLED"}, "❎ Okay, I've cancelled that - nothing was changed."

        audit(state.get("trace_id"), "sensitive_action",
              {"tool": action["tool"], "args": action["args"], "approved": approved, "result": result})
        outputs = dict(state["agent_outputs"])
        outputs[action["agent"]] = f"{outputs.get(action['agent'], '')}\n\n{note}".strip()
        step = {"step": "approval", "agent": action["agent"], "tool": action["tool"], "approved": approved,
                "summary": action["summary"], "ms": _ms(start)}
        return {"pending_action": None, "agent_outputs": outputs, "trace": [*state["trace"], step]}

    def aggregate_node(state: BankState) -> dict:
        """Result aggregation: one agent -> pass its answer through unchanged (no extra LLM call);
        several agents -> ask Gemini to merge them into one reply without adding new facts."""
        start = time.perf_counter()
        outputs = state.get("agent_outputs") or {}
        if state.get("final") and not outputs:
            final, mode = state["final"], "direct"
        elif len(outputs) == 1:
            final, mode = next(iter(outputs.values())), "passthrough"
        elif outputs:
            sections = "\n\n".join(f"### {SPECIALISTS[k].title}\n{v}" for k, v in outputs.items())
            try:
                final = llm_factory().invoke([
                    SystemMessage("You combine answers from SmartBank specialist agents into ONE clear, friendly "
                                  "reply to the customer. Keep every number, decision, and status message "
                                  "(lines starting with ✅/❎/⚠️) exactly as given. Do not add new facts. Use short "
                                  "sections or bullets. Do not mention 'agents'."),
                    HumanMessage(f"Customer asked: {state['messages'][-1].text}\n\nSpecialist answers:\n{sections}"),
                ]).text.strip()
                mode = "llm_merge"
            except Exception:
                final, mode = sections, "concatenate"
        else:
            final, mode = "Sorry, I couldn't work out how to help with that. Could you rephrase?", "empty"

        step = {"step": "aggregate", "mode": mode, "agents": list(outputs), "ms": _ms(start)}
        audit(state.get("trace_id"), "response", {"mode": mode, "agents": list(outputs)})
        return {"final": final, "messages": [AIMessage(final)], "trace": [*state.get("trace", []), step]}

    # ---------------- edges ----------------
    def after_guardrail(state: BankState) -> str:
        return "aggregate" if state.get("blocked") else "supervisor"

    def dispatch(state: BankState) -> str:
        queue = state.get("queue") or []
        return queue[0]["agent"] if queue else "aggregate"

    def after_agent(state: BankState) -> str:
        return "approval" if state.get("pending_action") else dispatch(state)

    g = StateGraph(BankState)
    g.add_node("guardrail", guardrail_node)
    g.add_node("supervisor", supervisor_node)
    for name in SPECIALISTS:
        g.add_node(name, make_agent_node(name))
    g.add_node("approval", approval_node)
    g.add_node("aggregate", aggregate_node)

    agent_targets = {name: name for name in SPECIALISTS} | {"aggregate": "aggregate"}
    g.add_edge(START, "guardrail")
    g.add_conditional_edges("guardrail", after_guardrail, ["supervisor", "aggregate"])
    g.add_conditional_edges("supervisor", dispatch, agent_targets)
    for name in SPECIALISTS:
        g.add_conditional_edges(name, after_agent, agent_targets | {"approval": "approval"})
    g.add_conditional_edges("approval", dispatch, agent_targets)
    g.add_edge("aggregate", END)
    return g.compile(checkpointer=checkpointer)


def new_turn_input(message: str, customer_id: int, trace_id: str) -> dict:
    """Input for a new user message: appends it to memory and resets all per-turn fields."""
    return {"messages": [HumanMessage(message)], "customer_id": customer_id, "trace_id": trace_id,
            "blocked": False, "plan": {}, "queue": [], "agent_outputs": {}, "pending_action": None,
            "trace": [], "final": ""}
