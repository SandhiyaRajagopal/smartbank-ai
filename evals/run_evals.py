"""Measure the Supervisor's routing accuracy against a labelled dataset.

    python -m evals.run_evals            # local run, prints accuracy + mistakes
    python -m evals.run_evals --langsmith  # also uploads the dataset and records an experiment in LangSmith

This is how we *evaluate* (not train) the zero-shot router: change a prompt or model,
re-run, and compare the score. A routing is correct when the agents match exactly
(set comparison, since order can legitimately differ for independent parts).
"""
import argparse
import json
import time
from pathlib import Path

from langchain_core.messages import HumanMessage

from backend.app.agents.supervisor import route
from backend.app.config import settings
from backend.app.llm import get_llm

DATASET = Path(__file__).with_name("routing_dataset.json")
LANGSMITH_DATASET = "smartbank-routing"


def predict(question: str) -> dict:
    decision, fallback = route(get_llm(), [HumanMessage(question)])
    return {"agents": [s.agent for s in decision.steps], "intent": decision.intent, "fallback": fallback}


def correct(predicted: list[str], expected: list[str]) -> bool:
    return set(predicted) == set(expected)


def run_local(examples: list[dict]) -> None:
    hits, mistakes, fallbacks = 0, [], 0
    for ex in examples:
        pred = predict(ex["question"])
        fallbacks += pred["fallback"]
        if correct(pred["agents"], ex["agents"]):
            hits += 1
        else:
            mistakes.append((ex["question"], ex["agents"], pred["agents"]))
        time.sleep(0.5)  # stay well inside free-tier rate limits
    print(f"\nRouting accuracy: {hits}/{len(examples)} = {hits / len(examples):.0%}  "
          f"(model={settings.gemini_model}, keyword fallbacks used={fallbacks})")
    for q, exp, got in mistakes:
        print(f"  ✗ {q!r}\n      expected {exp}, got {got}")


def run_langsmith(examples: list[dict]) -> None:
    from langsmith import Client, evaluate

    client = Client()
    if not client.has_dataset(dataset_name=LANGSMITH_DATASET):
        ds = client.create_dataset(LANGSMITH_DATASET, description="SmartBank supervisor routing labels")
        client.create_examples(dataset_id=ds.id, examples=[
            {"inputs": {"question": e["question"]}, "outputs": {"agents": e["agents"]}} for e in examples])

    def routing_correct(outputs: dict, reference_outputs: dict) -> bool:
        return correct(outputs["agents"], reference_outputs["agents"])

    evaluate(lambda inputs: predict(inputs["question"]), data=LANGSMITH_DATASET,
             evaluators=[routing_correct], experiment_prefix=f"routing-{settings.gemini_model}",
             max_concurrency=2)
    print("Experiment recorded - open the 'smartbank-routing' dataset in LangSmith to compare runs.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--langsmith", action="store_true", help="record the run as a LangSmith experiment")
    args = parser.parse_args()
    if not settings.llm_configured:
        raise SystemExit("Set GOOGLE_API_KEY in .env first.")
    data = json.loads(DATASET.read_text(encoding="utf-8"))
    run_langsmith(data) if args.langsmith else run_local(data)
