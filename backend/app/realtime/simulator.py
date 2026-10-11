"""Real-time transaction simulator - stands in for the bank's payment switch.

Every SIMULATOR_INTERVAL seconds it creates a transaction for a customer who is online
(mostly everyday spends, sometimes a suspicious one), sends it through the same
record_transaction() pipeline as everything else (card check -> fraud scoring -> alert),
and pushes the result to the customer's browser over WebSocket.
"""
import asyncio
import logging
import random
import time
from datetime import datetime

from ..config import settings
from ..db.seed import SPEND
from ..db.session import db_session
from ..services import banking
from .hub import hub

log = logging.getLogger("smartbank.simulator")

# Each scenario scores HIGH (>= 60) for every demo customer: foreign + (huge amount or high-risk category).
SUSPICIOUS_SCENARIOS = [
    dict(amount=1_85_000, merchant="Marina Bay Electronics", category="SHOPPING", channel="CARD",
         city="Singapore", country="SG"),
    dict(amount=24_999, merchant="GiftCardHub Online", category="GIFT_CARDS", channel="CARD",
         city="Dubai", country="AE"),
    dict(amount=75_000, merchant="CoinSwift Exchange", category="CRYPTO", channel="CARD",
         city="London", country="GB"),
]
# Automatic fraud stays occasional so a tab left open overnight still looks like a normal account;
# the "Suspicious transaction" demo button injects one on demand regardless.
SUSPICIOUS_PROBABILITY = 0.04
SUSPICIOUS_COOLDOWN_SECONDS = 600
LOW_BALANCE = 5_000
INCOMING = [("UPI from Family", "TRANSFER"), ("Amazon Refund", "REFUND"), ("Cashback Credit", "REFUND")]
_last_suspicious: dict[int, float] = {}


def _random_normal_txn(rng: random.Random, city: str) -> dict:
    category = rng.choice(list(SPEND))
    merchants, lo, hi, channel = SPEND[category]
    return dict(amount=round(rng.uniform(lo, hi), 2), merchant=rng.choice(merchants), category=category,
                channel=channel, city=city, country="IN")


def _incoming_txn(rng: random.Random, city: str) -> dict:
    merchant, category = rng.choice(INCOMING)
    return dict(amount=float(rng.randrange(2_000, 15_001, 500)), merchant=merchant, category=category,
                channel="UPI", city=city, country="IN", direction="CREDIT")


def simulate_transaction(customer_id: int, suspicious: bool = False, rng: random.Random | None = None,
                         ts: datetime | None = None) -> dict:
    """Create one live transaction and return the events to push to the customer's browser."""
    rng = rng or random.Random()
    with db_session() as db:
        city = banking.get_customer(db, customer_id).city
        if suspicious:
            spec = rng.choice(SUSPICIOUS_SCENARIOS)
        elif sum(a["balance"] for a in banking.list_accounts(db, customer_id)) < LOW_BALANCE:
            spec = _incoming_txn(rng, city)  # keep long-running demo accounts from draining to zero
        else:
            spec = _random_normal_txn(rng, city)
        txn, alert = banking.record_transaction(db, customer_id, ts=ts, **spec)
        db.flush()
        events = [{"type": "transaction", "data": banking.txn_to_dict(txn)},
                  {"type": "accounts", "data": banking.list_accounts(db, customer_id)}]
        if alert:
            events.append({"type": "alert", "data": banking.alert_to_dict(alert)})
    return {"events": events}


async def push(customer_id: int, result: dict) -> None:
    for event in result["events"]:
        await hub.publish(customer_id, event)


async def run_simulator() -> None:
    rng = random.Random()
    log.info("transaction simulator started (every %ss)", settings.simulator_interval)
    while True:
        await asyncio.sleep(settings.simulator_interval)
        try:
            for customer_id in hub.online_customers():
                now = time.monotonic()
                suspicious = (rng.random() < SUSPICIOUS_PROBABILITY
                              and now - _last_suspicious.get(customer_id, -1e9) > SUSPICIOUS_COOLDOWN_SECONDS)
                if suspicious:
                    _last_suspicious[customer_id] = now
                result = await asyncio.to_thread(simulate_transaction, customer_id, suspicious, rng)
                await push(customer_id, result)
        except Exception:
            log.exception("simulator tick failed")
