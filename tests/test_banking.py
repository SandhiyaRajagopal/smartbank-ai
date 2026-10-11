"""Core-banking behaviour that keeps long-running demo accounts realistic."""
import random

from sqlalchemy import select

from backend.app.db.models import Account
from backend.app.db.session import db_session
from backend.app.realtime.simulator import simulate_transaction
from backend.app.services import banking

PRIYA, ARJUN, ANANYA = 1, 2, 4


def _set_balance(customer_id: int, value: float) -> float:
    with db_session() as db:
        acct = db.scalars(select(Account).where(Account.customer_id == customer_id)).first()
        old, acct.balance = acct.balance, value
    return old


def test_purchase_larger_than_balance_is_declined_and_still_alerts():
    old = _set_balance(ANANYA, 10_000)
    try:
        with db_session() as db:
            txn, alert = banking.record_transaction(db, ANANYA, amount=75_000, merchant="CoinSwift Exchange",
                                                    category="CRYPTO", channel="CARD", city="London", country="GB")
            assert txn.status == "DECLINED"
            assert "Insufficient funds" in txn.risk_reasons
            assert txn.risk_level == "HIGH" and alert is not None  # a fraud attempt is still reported
        with db_session() as db:
            assert banking.list_accounts(db, ANANYA)[0]["balance"] == 10_000  # no money moved
    finally:
        _set_balance(ANANYA, old)


def test_low_balance_account_receives_money_instead_of_spending():
    old = _set_balance(PRIYA, 1_000)
    try:
        txn = simulate_transaction(PRIYA, suspicious=False, rng=random.Random(3))["events"][0]["data"]
        assert txn["direction"] == "CREDIT" and txn["amount"] >= 2_000
    finally:
        _set_balance(PRIYA, old)


def test_balance_never_goes_negative_under_a_long_session():
    rng = random.Random(11)
    for _ in range(120):  # ~40 minutes of live simulation at one transaction every 20 seconds
        simulate_transaction(ANANYA, suspicious=rng.random() < 0.2, rng=rng)
    with db_session() as db:
        assert banking.list_accounts(db, ANANYA)[0]["balance"] >= 0


def test_spending_summary_excludes_flagged_fraud():
    with db_session() as db:
        summary = banking.spending_summary(db, ARJUN, days=30)
    assert summary["flagged_transactions_excluded"] >= 4
    assert "GIFT_CARDS" not in {c["category"] for c in summary["by_category"]}
