"""Supervisor / Orchestrator: understands the request and decides which agents handle it.

No model training is needed. This is *zero-shot* intent classification: Gemini reads
the agent descriptions and returns a RouteDecision that must match the Pydantic schema
below ("structured output"), so we always get valid, machine-readable routing - not free text.

It also does *task decomposition*: "check for fraud, then tell me if I can get a car loan"
becomes two ordered steps for two agents. If the LLM call fails, a transparent keyword
router takes over, so the app degrades gracefully instead of erroring.
"""
import logging
import re
from typing import Literal, Optional

from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from .specialists import SPECIALISTS

log = logging.getLogger("smartbank.supervisor")

AgentName = Literal["customer", "fraud", "credit"]
MAX_STEPS = 3


class RouteStep(BaseModel):
    agent: AgentName
    task: str = Field(description="A self-contained instruction for that agent. Include every relevant detail "
                                  "from the conversation (amounts, loan type, tenure, dates, which transaction).")


class RouteDecision(BaseModel):
    intent: str = Field(description="Short snake_case label, e.g. balance_inquiry, fraud_check, loan_eligibility")
    steps: list[RouteStep] = Field(default_factory=list,
                                   description="Ordered agent steps (1-3). Empty only for greetings/out-of-scope.")
    direct_response: Optional[str] = Field(
        default=None, description="Only when steps is empty: a short reply for greetings, thanks, or "
                                  "out-of-scope requests, explaining what SmartBank Assistant can help with.")
    reasoning: str = Field(description="One sentence explaining the routing choice.")


def _system_prompt() -> str:
    agents = "\n".join(f"- {a.name}: {a.title} - {a.description}" for a in SPECIALISTS.values())
    return f"""You are the Supervisor of SmartBank's AI assistant. You never answer banking questions
yourself; you route them to specialist agents.

Specialist agents:
{agents}

Instructions:
- Pick the minimum set of agents needed. Most requests need exactly one.
- If the request has several parts, create one step per part, in a sensible order
  (e.g. check fraud before discussing a new loan).
- Resolve follow-ups using the conversation (e.g. "what about 5 years?" after a loan discussion
  -> credit agent, with the loan type and amount repeated in the task).
- If the customer says "yes / go ahead / block it" after an agent suggested an action, route it back to
  that same agent with a task that states the action clearly.
- Greetings, thanks, and non-banking questions: no steps, give a short direct_response.
- Requests for other customers' data or to bypass security: no steps, politely refuse in direct_response."""


# ---------- keyword fallback (used only if the LLM call fails) ----------
KEYWORDS = {
    "fraud": r"fraud|suspicious|unrecogni[sz]e|scam|stolen|block|freeze|hack|didn'?t make|not me|dispute|risk",
    "credit": r"loan|emi|credit score|cibil|eligib|borrow|interest rate|mortgage|apply",
    "customer": r"balance|transaction|spend|statement|account|profile|kyc|history|payment|card",
}


def keyword_route(text: str) -> RouteDecision:
    text_l = text.lower()
    steps = [RouteStep(agent=name, task=text) for name, pattern in KEYWORDS.items() if re.search(pattern, text_l)]
    # "card" alone is a customer question unless a fraud word is also present
    if any(s.agent == "fraud" for s in steps):
        steps = [s for s in steps if s.agent != "customer" or re.search(r"balance|spend|statement", text_l)]
    if not steps:
        return RouteDecision(intent="unknown", reasoning="keyword fallback: no banking keywords",
                             direct_response="I can help with your balance, transactions, spending, card "
                                             "security, fraud checks, credit score and loans. What would you like to do?")
    return RouteDecision(intent="keyword_fallback", steps=steps[:MAX_STEPS], reasoning="keyword fallback router")


def route(llm, messages: list[AnyMessage]) -> tuple[RouteDecision, bool]:
    """Returns (decision, used_fallback)."""
    last_user = next((m.text for m in reversed(messages) if isinstance(m, HumanMessage)), "")
    try:
        router = llm.with_structured_output(RouteDecision)
        decision: RouteDecision = router.invoke([SystemMessage(_system_prompt()), *messages])
        if decision is None:
            raise ValueError("empty routing decision")
    except Exception as e:  # network/quota/parsing problems -> deterministic fallback
        log.warning("supervisor LLM routing failed, using keyword fallback: %s", e)
        return keyword_route(last_user), True

    # sanitise: drop duplicate consecutive agents, cap the number of steps
    steps: list[RouteStep] = []
    for s in decision.steps:
        if not steps or steps[-1].agent != s.agent:
            steps.append(s)
    decision.steps = steps[:MAX_STEPS]
    if not decision.steps and not decision.direct_response:
        return keyword_route(last_user), True
    return decision, False
