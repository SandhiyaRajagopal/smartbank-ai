from langchain_core.messages import HumanMessage

from backend.app.agents.supervisor import RouteDecision, RouteStep, keyword_route, route
from tests.conftest import FakeLLM


def agents(decision):
    return [s.agent for s in decision.steps]


def test_keyword_router_basic_intents():
    assert agents(keyword_route("What's my account balance?")) == ["customer"]
    assert agents(keyword_route("I see a suspicious charge, please block my card")) == ["fraud"]
    assert agents(keyword_route("Am I eligible for a car loan?")) == ["credit"]


def test_keyword_router_multi_intent():
    assert agents(keyword_route("Any fraud on my account? Then check my loan eligibility")) == ["fraud", "credit"]


def test_keyword_router_policy_questions_go_to_compliance():
    assert agents(keyword_route("What are the foreclosure charges on a personal loan?")) == ["compliance"]
    assert agents(keyword_route("Which documents do I need for KYC?")) == ["compliance"]
    assert agents(keyword_route("There's a suspicious charge on my card")) == ["fraud"]


def test_keyword_router_out_of_scope_gives_direct_response():
    d = keyword_route("What's the weather in Chennai?")
    assert d.steps == [] and d.direct_response


def test_llm_route_is_used_when_available():
    llm = FakeLLM(route=RouteDecision(intent="loan_eligibility", reasoning="loan question",
                                      steps=[RouteStep(agent="credit", task="Check 5 lakh personal loan")]))
    decision, fallback = route(llm, [HumanMessage("can I borrow 5 lakh?")])
    assert not fallback
    assert agents(decision) == ["credit"]


def test_llm_failure_falls_back_to_keywords():
    decision, fallback = route(FakeLLM(fail_routing=True), [HumanMessage("show my recent transactions")])
    assert fallback
    assert agents(decision) == ["customer"]


def test_duplicate_steps_are_merged_and_capped():
    steps = [RouteStep(agent=a, task="t") for a in ["fraud", "fraud", "credit", "customer", "fraud"]]
    llm = FakeLLM(route=RouteDecision(intent="x", reasoning="r", steps=steps))
    decision, _ = route(llm, [HumanMessage("everything")])
    assert agents(decision) == ["fraud", "credit", "customer"]


def test_empty_llm_decision_falls_back():
    llm = FakeLLM(route=RouteDecision(intent="x", reasoning="r", steps=[], direct_response=None))
    decision, fallback = route(llm, [HumanMessage("what is my balance")])
    assert fallback and agents(decision) == ["customer"]
