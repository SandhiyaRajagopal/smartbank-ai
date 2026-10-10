"""Seeds the simulated bank with 4 fictional customers whose profiles are designed
to produce *different* outcomes in the demo:

  1. Priya Sharma  - salaried, excellent credit        -> loans approved, clean account
  2. Arjun Mehta   - business owner, active home loan  -> suspicious Dubai / gift-card activity (fraud demo)
  3. Rahul Verma   - high existing EMIs, ok credit     -> loan only conditionally eligible (FOIR too high)
  4. Ananya Iyer   - student, KYC pending, no bureau   -> "complete KYC first" path

All names and data are fictional. Transactions are generated with a fixed random
seed so every fresh install looks the same. Run:  python -m backend.app.db.seed --reset
"""
import argparse
import random
from datetime import datetime, timedelta

from sqlalchemy import select

from ..auth.security import hash_password
from ..services.banking import record_transaction
from .models import Account, Base, Card, CreditReport, Customer, Loan, User
from .session import db_session, engine, init_db

# Local demo logins (fictional test accounts, documented in the README).
DEMO_PASSWORD = "SmartBank@2026"

CUSTOMERS = [
    dict(key="priya", name="Priya Sharma", city="Chennai", segment="Salaried", employment="Software Engineer, salaried",
         monthly_income=125_000, kyc_status="VERIFIED", phone="+919840012345", since_days=6 * 365,
         balance=180_000, credit=dict(score=792, enquiries_6m=1, missed_payments_12m=0, credit_utilisation=0.18),
         credit_card_limit=200_000, loans=[], salary_from="Infosys Payroll"),
    dict(key="arjun", name="Arjun Mehta", city="Mumbai", segment="Business", employment="Owner, Mehta Traders",
         monthly_income=210_000, kyc_status="VERIFIED", phone="+919820054321", since_days=9 * 365,
         balance=420_000, credit=dict(score=738, enquiries_6m=2, missed_payments_12m=0, credit_utilisation=0.35),
         credit_card_limit=400_000, salary_from="Mehta Traders Settlements",
         loans=[dict(type="HOME", principal=4_500_000, outstanding=3_620_000, interest_rate=8.6, tenure_months=240)]),
    dict(key="rahul", name="Rahul Verma", city="Bengaluru", segment="Salaried", employment="Sales Executive, salaried",
         monthly_income=60_000, kyc_status="VERIFIED", phone="+919900067890", since_days=3 * 365,
         balance=22_000, credit=dict(score=702, enquiries_6m=5, missed_payments_12m=1, credit_utilisation=0.72),
         credit_card_limit=75_000, salary_from="RetailCo Payroll",
         loans=[dict(type="PERSONAL", principal=500_000, outstanding=310_000, interest_rate=14.0, tenure_months=48),
                dict(type="CAR", principal=600_000, outstanding=420_000, interest_rate=10.5, tenure_months=60)]),
    dict(key="ananya", name="Ananya Iyer", city="Coimbatore", segment="Student", employment="Final-year student / intern",
         monthly_income=18_000, kyc_status="PENDING", phone="+919787011223", since_days=40,
         balance=9_500, credit=dict(score=None, enquiries_6m=0, missed_payments_12m=0, credit_utilisation=0.0),
         credit_card_limit=None, loans=[], salary_from="Internship Stipend"),
]

# category -> (merchants, min amount, max amount, channel)
SPEND = {
    "GROCERIES": (["FreshMart", "Nilgiris", "BigBasket"], 400, 3_500, "UPI"),
    "FOOD": (["Swiggy", "Zomato", "Saravana Bhavan", "Cafe Coffee Day"], 150, 1_800, "UPI"),
    "FUEL": (["Indian Oil", "HP Petrol"], 800, 3_000, "CARD"),
    "SHOPPING": (["Amazon", "Myntra", "Croma", "Reliance Trends"], 500, 9_000, "CARD"),
    "ENTERTAINMENT": (["BookMyShow", "Netflix", "PVR Cinemas"], 199, 1_200, "CARD"),
    "TRANSPORT": (["Uber", "Ola", "Chennai Metro"], 60, 600, "UPI"),
    "HEALTH": (["Apollo Pharmacy", "MedPlus"], 200, 2_500, "UPI"),
}
# how many card/UPI spends per month, by profile
SPEND_PER_MONTH = {"priya": 22, "arjun": 28, "rahul": 18, "ananya": 10}
RENT = {"priya": 28_000, "arjun": 0, "rahul": 15_000, "ananya": 6_000}


def _emi(principal, rate, months):
    from ..services.loan_rules import calculate_emi
    return calculate_emi(principal, rate, months)


def _seed_customer(db, idx: int, spec: dict, rng: random.Random, now: datetime) -> None:
    c = Customer(id=idx, name=spec["name"], email=f"{spec['key']}@smartbank.demo", phone=spec["phone"],
                 city=spec["city"], segment=spec["segment"], employment=spec["employment"],
                 monthly_income=spec["monthly_income"], kyc_status=spec["kyc_status"],
                 customer_since=now - timedelta(days=spec["since_days"]))
    db.add(c)
    db.flush()
    db.add(User(email=c.email, password_hash=hash_password(DEMO_PASSWORD), customer_id=c.id))

    acct = Account(customer_id=c.id, account_number=f"5010{idx:02d}{rng.randint(10**7, 10**8 - 1)}",
                   type="CURRENT" if spec["segment"] == "Business" else "SAVINGS", balance=spec["balance"])
    db.add(acct)
    db.flush()
    db.add(Card(customer_id=c.id, account_id=acct.id, masked_number=f"XXXX XXXX XXXX {rng.randint(1000, 9999)}",
                type="DEBIT", network="RuPay" if idx % 2 else "Visa"))
    if spec["credit_card_limit"]:
        db.add(Card(customer_id=c.id, account_id=acct.id, masked_number=f"XXXX XXXX XXXX {rng.randint(1000, 9999)}",
                    type="CREDIT", network="Mastercard", credit_limit=spec["credit_card_limit"]))
    db.add(CreditReport(customer_id=c.id, updated_at=now - timedelta(days=12), **spec["credit"]))
    for l in spec["loans"]:
        db.add(Loan(customer_id=c.id, status="ACTIVE", emi=_emi(l["principal"], l["interest_rate"], l["tenure_months"]),
                    created_at=now - timedelta(days=500), **l))
    db.flush()

    # --- 60 days of history, posted in time order through the real transaction pipeline ---
    events = []
    for month_ago in (2, 1, 0):
        pay_day = (now - timedelta(days=30 * month_ago)).replace(day=1, hour=9, minute=5)
        if pay_day <= now:
            events.append(dict(ts=pay_day, amount=spec["monthly_income"], merchant=spec["salary_from"],
                               category="SALARY", channel="NEFT", direction="CREDIT", trusted=True))
            if RENT[spec["key"]]:
                events.append(dict(ts=pay_day + timedelta(days=2, hours=1), amount=RENT[spec["key"]],
                                   merchant="Rent - Standing Instruction", category="RENT", channel="NETBANKING",
                                   trusted=True))
            for l in spec["loans"]:
                events.append(dict(ts=pay_day + timedelta(days=4), amount=_emi(l["principal"], l["interest_rate"],
                                                                               l["tenure_months"]),
                                   merchant=f"{l['type'].title()} Loan EMI", category="EMI", channel="NACH",
                                   trusted=True))
            events.append(dict(ts=pay_day + timedelta(days=6, hours=3), amount=rng.randint(900, 2_800),
                               merchant="TNEB / BESCOM Electricity", category="UTILITIES", channel="UPI", trusted=True))
    for _ in range(SPEND_PER_MONTH[spec["key"]] * 2):
        cat = rng.choice(list(SPEND))
        merchants, lo, hi, channel = SPEND[cat]
        ts = now - timedelta(days=rng.uniform(0.5, 60))
        ts = ts.replace(hour=rng.randint(8, 22), minute=rng.randint(0, 59))
        scale = 0.5 if spec["key"] == "ananya" else 1.0
        events.append(dict(ts=ts, amount=round(rng.uniform(lo, hi) * scale, 2), merchant=rng.choice(merchants),
                           category=cat, channel=channel))

    if spec["key"] == "arjun":
        # Fraud scenario: midnight card spend in Dubai + rapid gift-card purchases (card-testing pattern)
        base = (now - timedelta(days=1)).replace(hour=2, minute=14)
        events += [
            dict(ts=base, amount=48_500, merchant="Gulf Electronics LLC", category="SHOPPING", channel="CARD",
                 city="Dubai", country="AE"),
            dict(ts=base + timedelta(minutes=3), amount=9_999, merchant="GiftCardHub Online", category="GIFT_CARDS",
                 channel="CARD", city="Dubai", country="AE"),
            dict(ts=base + timedelta(minutes=5), amount=9_999, merchant="GiftCardHub Online", category="GIFT_CARDS",
                 channel="CARD", city="Dubai", country="AE"),
            dict(ts=base + timedelta(minutes=7), amount=9_999, merchant="GiftCardHub Online", category="GIFT_CARDS",
                 channel="CARD", city="Dubai", country="AE"),
        ]

    for e in sorted(events, key=lambda e: e["ts"]):
        record_transaction(db, c.id, city=e.pop("city", spec["city"]), **e)


def seed(reset: bool = False) -> bool:
    """Create tables and demo data. Returns True if data was inserted."""
    if reset:
        Base.metadata.drop_all(engine)
    init_db()
    with db_session() as db:
        if db.scalars(select(User)).first():
            return False
        rng = random.Random(42)
        now = datetime.now().replace(second=0, microsecond=0)
        for idx, spec in enumerate(CUSTOMERS, start=1):
            _seed_customer(db, idx, spec, rng, now)
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed the SmartBank demo database")
    parser.add_argument("--reset", action="store_true", help="drop all tables first")
    args = parser.parse_args()
    print("Seeded demo data." if seed(reset=args.reset) else "Database already has data (use --reset).")
