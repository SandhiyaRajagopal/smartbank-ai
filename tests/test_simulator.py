import random
from datetime import datetime

import pytest

from backend.app.db.session import db_session
from backend.app.realtime.simulator import SUSPICIOUS_SCENARIOS, simulate_transaction
from backend.app.services import banking


@pytest.mark.parametrize("customer_id", [1, 3, 4])  # Arjun (2) is excluded: other tests block his card
@pytest.mark.parametrize("scenario", range(len(SUSPICIOUS_SCENARIOS)))
def test_every_suspicious_scenario_is_high_risk_for_every_customer(customer_id, scenario, monkeypatch):
    rng = random.Random()
    monkeypatch.setattr(rng, "choice", lambda seq: seq[scenario] if seq is SUSPICIOUS_SCENARIOS else seq[0])
    result = simulate_transaction(customer_id, suspicious=True, rng=rng)
    txn = result["events"][0]["data"]
    assert txn["risk_level"] == "HIGH", txn
    assert result["events"][-1]["type"] == "alert"


def test_normal_transactions_are_low_risk():
    # fixed daytime timestamp: at night the "unusual hour" rule (correctly) adds risk
    result = simulate_transaction(1, suspicious=False, rng=random.Random(7), ts=datetime.now().replace(hour=14))
    assert result["events"][0]["data"]["risk_level"] == "LOW"


def test_blocked_card_declines_live_card_transactions():
    with db_session() as db:
        card = next(c for c in banking.list_cards(db, 4) if c["type"] == "DEBIT")
        banking.block_card(db, 4, card["id"], "test")
    try:
        txn = simulate_transaction(4, suspicious=True)["events"][0]["data"]
        assert txn["status"] == "DECLINED"
    finally:
        with db_session() as db:
            banking.unblock_card(db, 4, card["id"])
