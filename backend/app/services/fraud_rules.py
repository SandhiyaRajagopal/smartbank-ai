"""Rule-based fraud risk scoring.

Why rules and not the LLM? Fraud decisions must be consistent, explainable and
auditable - the same transaction must always get the same score. The LLM's job
is to *explain* this score to the customer in plain language, not to invent it.
(In a real bank this would be an ML model, e.g. gradient boosting trained on
labelled fraud data; the interface - features in, score + reasons out - stays the same.)
"""
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class TxnFeatures:
    amount: float
    country: str
    timestamp: datetime
    category: str
    channel: str
    home_country: str = "IN"
    travel_notice: bool = False
    avg_debit_amount: float = 0.0           # customer's typical spend
    known_categories: set = field(default_factory=set)
    txns_last_10_min: int = 0


@dataclass
class RiskResult:
    score: int
    level: str
    reasons: list[str]


HIGH_RISK_CATEGORIES = {"CRYPTO", "GAMBLING", "GIFT_CARDS", "WIRE_TRANSFER"}


def score_transaction(f: TxnFeatures) -> RiskResult:
    score = 0
    reasons: list[str] = []

    # 1. Amount far above what this customer normally spends
    if f.avg_debit_amount > 0:
        ratio = f.amount / f.avg_debit_amount
        if ratio >= 10:
            score += 35
            reasons.append(f"Amount is {ratio:.0f}x the customer's average spend")
        elif ratio >= 5:
            score += 20
            reasons.append(f"Amount is {ratio:.0f}x the customer's average spend")
    elif f.amount >= 50_000:
        score += 20
        reasons.append("Large amount with no spending history")

    # 2. Foreign transaction without a travel notice
    if f.country != f.home_country and not f.travel_notice:
        score += 25
        reasons.append(f"International transaction ({f.country}) with no travel notice on file")

    # 3. Unusual hour (midnight to 5 AM)
    if 0 <= f.timestamp.hour < 5:
        score += 15
        reasons.append(f"Made at an unusual hour ({f.timestamp:%H:%M})")

    # 4. High-risk merchant category
    if f.category in HIGH_RISK_CATEGORIES:
        score += 20
        reasons.append(f"High-risk merchant category ({f.category})")
    elif f.known_categories and f.category not in f.known_categories:
        score += 5
        reasons.append(f"First purchase in category {f.category}")

    # 5. Velocity - many transactions in a short window (card testing pattern)
    if f.txns_last_10_min >= 3:
        score += 20
        reasons.append(f"{f.txns_last_10_min} transactions in the last 10 minutes")

    score = min(score, 100)
    level = "HIGH" if score >= 60 else "MEDIUM" if score >= 30 else "LOW"
    return RiskResult(score=score, level=level, reasons=reasons)
