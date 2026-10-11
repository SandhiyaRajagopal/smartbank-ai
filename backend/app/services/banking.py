"""Simulated core-banking service layer.

Think of these functions as the bank's internal APIs (Account API, Transaction API,
Card API, Loan API, Credit Bureau API in layer 5 of the reference diagram).
The REST endpoints, the AI agents' tools and the real-time simulator all call
these same functions - one source of truth, so the AI can never see data the
app wouldn't show, and the dashboard always matches what the agents say.

Every function takes customer_id from the *authenticated session*, never from
the LLM, so an agent cannot be tricked into reading another customer's data.
"""
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.models import Account, Alert, Card, CreditReport, Customer, Loan, Transaction
from . import fraud_rules, loan_rules


class BankingError(Exception):
    pass


# ---------- Customer / Account API ----------

def get_customer(db: Session, customer_id: int) -> Customer:
    c = db.get(Customer, customer_id)
    if not c:
        raise BankingError("Customer not found")
    return c


def customer_profile(db: Session, customer_id: int) -> dict:
    c = get_customer(db, customer_id)
    return {
        "name": c.name,
        "email": c.email,
        "phone": "******" + c.phone[-4:],
        "city": c.city,
        "segment": c.segment,
        "employment": c.employment,
        "kyc_status": c.kyc_status,
        "customer_since": c.customer_since.date().isoformat(),
        "travel_notice": c.travel_notice,
    }


def list_accounts(db: Session, customer_id: int) -> list[dict]:
    rows = db.scalars(select(Account).where(Account.customer_id == customer_id)).all()
    return [
        {"id": a.id, "account_number": "XXXX" + a.account_number[-4:], "type": a.type,
         "balance": round(a.balance, 2), "currency": a.currency}
        for a in rows
    ]


def list_cards(db: Session, customer_id: int) -> list[dict]:
    rows = db.scalars(select(Card).where(Card.customer_id == customer_id)).all()
    return [
        {"id": c.id, "number": c.masked_number, "type": c.type, "network": c.network,
         "status": c.status, "credit_limit": c.credit_limit}
        for c in rows
    ]


# ---------- Transaction API ----------

def _account_ids(db: Session, customer_id: int) -> list[int]:
    return list(db.scalars(select(Account.id).where(Account.customer_id == customer_id)))


def txn_to_dict(t: Transaction) -> dict:
    return {
        "id": t.id, "timestamp": t.timestamp.isoformat(timespec="minutes"), "amount": round(t.amount, 2),
        "direction": t.direction, "merchant": t.merchant, "category": t.category, "channel": t.channel,
        "city": t.city, "country": t.country, "risk_score": t.risk_score, "risk_level": t.risk_level,
        "risk_reasons": t.risk_reasons or [], "status": t.status,
    }


def list_transactions(db: Session, customer_id: int, limit: int = 20, days: int | None = None,
                      category: str | None = None, min_risk: str | None = None) -> list[dict]:
    q = select(Transaction).where(Transaction.account_id.in_(_account_ids(db, customer_id)))
    if days:
        q = q.where(Transaction.timestamp >= datetime.now() - timedelta(days=days))
    if category:
        q = q.where(Transaction.category == category.upper())
    if min_risk == "MEDIUM":
        q = q.where(Transaction.risk_level.in_(["MEDIUM", "HIGH"]))
    elif min_risk == "HIGH":
        q = q.where(Transaction.risk_level == "HIGH")
    q = q.order_by(Transaction.timestamp.desc()).limit(min(limit, 100))
    return [txn_to_dict(t) for t in db.scalars(q)]


def spending_summary(db: Session, customer_id: int, days: int = 30) -> dict:
    since = datetime.now() - timedelta(days=days)
    in_period = (Transaction.account_id.in_(_account_ids(db, customer_id)), Transaction.timestamp >= since)
    # only completed payments: declined ones never moved money, and flagged (suspected fraud) ones are
    # under review - counting them would make fraud look like the customer's own spending
    rows = db.execute(
        select(Transaction.category, Transaction.direction, func.sum(Transaction.amount), func.count())
        .where(*in_period, Transaction.status == "COMPLETED")
        .group_by(Transaction.category, Transaction.direction)
    ).all()
    flagged = db.scalar(select(func.count()).where(*in_period, Transaction.status == "FLAGGED"))
    spend = {cat: round(total, 2) for cat, direction, total, _ in rows if direction == "DEBIT"}
    income = sum(total for _, direction, total, _ in rows if direction == "CREDIT")
    total_spend = sum(spend.values())
    top = sorted(spend.items(), key=lambda kv: kv[1], reverse=True)
    return {
        "period_days": days,
        "total_spent": round(total_spend, 2),
        "total_received": round(income, 2),
        "net_cashflow": round(income - total_spend, 2),
        "flagged_transactions_excluded": flagged,
        "by_category": [{"category": k, "amount": v, "share": round(v / total_spend, 3) if total_spend else 0}
                        for k, v in top],
    }


# ---------- Fraud / Risk API ----------

def build_features(db: Session, customer: Customer, amount: float, country: str, ts: datetime,
                   category: str, channel: str) -> fraud_rules.TxnFeatures:
    acct_ids = _account_ids(db, customer.id)
    debits = db.scalars(
        select(Transaction).where(Transaction.account_id.in_(acct_ids), Transaction.direction == "DEBIT",
                                  Transaction.timestamp < ts)
    ).all()
    # the "normal behaviour" baseline only learns from low-risk spends, but velocity counts every attempt
    history = [t for t in debits if t.risk_level == "LOW" and t.status != "DECLINED"]
    avg = sum(t.amount for t in history) / len(history) if history else 0.0
    recent = sum(1 for t in debits if t.timestamp >= ts - timedelta(minutes=10))
    return fraud_rules.TxnFeatures(
        amount=amount, country=country, timestamp=ts, category=category, channel=channel,
        home_country=customer.home_country, travel_notice=customer.travel_notice,
        avg_debit_amount=avg, known_categories={t.category for t in history}, txns_last_10_min=recent,
    )


def record_transaction(db: Session, customer_id: int, *, amount: float, merchant: str, category: str,
                       channel: str, city: str, country: str = "IN", direction: str = "DEBIT",
                       ts: datetime | None = None, trusted: bool = False) -> tuple[Transaction, Alert | None]:
    """Process a new transaction like a real-time payment switch would:
    check card status -> score fraud risk -> post it -> raise an alert if risky.

    trusted=True marks standing instructions / registered payees (rent, EMIs, bills),
    which banks don't run through card-fraud scoring."""
    customer = get_customer(db, customer_id)
    account = db.scalars(select(Account).where(Account.customer_id == customer_id)).first()
    card = db.scalars(select(Card).where(Card.account_id == account.id, Card.type == "DEBIT")).first()
    ts = ts or datetime.now()

    txn = Transaction(account_id=account.id, card_id=card.id if channel == "CARD" and card else None,
                      timestamp=ts, amount=amount, direction=direction, merchant=merchant,
                      category=category, channel=channel, city=city, country=country)
    alert = None

    if direction == "DEBIT":
        if channel == "CARD" and card and card.status == "BLOCKED":
            txn.status, txn.risk_level, txn.risk_reasons = "DECLINED", "LOW", ["Card is blocked"]
            db.add(txn)
            db.flush()
            alert = Alert(customer_id=customer_id, transaction_id=txn.id, type="CARD", severity="INFO",
                          title="Transaction declined",
                          message=f"Rs {amount:,.0f} at {merchant} was declined because your card is blocked.")
            db.add(alert)
            return txn, alert

        if not trusted:
            risk = fraud_rules.score_transaction(
                build_features(db, customer, amount, country, ts, category, channel))
            txn.risk_score, txn.risk_level, txn.risk_reasons = risk.score, risk.level, risk.reasons
            if risk.level == "HIGH":
                txn.status = "FLAGGED"
            # a purchase larger than the balance is declined (still risk-scored, so fraud attempts alert)
            if amount > account.balance:
                txn.status = "DECLINED"
                txn.risk_reasons = [*txn.risk_reasons, "Insufficient funds"]
        if txn.status != "DECLINED":
            account.balance -= amount
    else:
        account.balance += amount

    db.add(txn)
    db.flush()
    if txn.risk_level == "HIGH":
        outcome = "was declined (insufficient funds) but" if txn.status == "DECLINED" else "was"
        alert = Alert(customer_id=customer_id, transaction_id=txn.id, type="FRAUD", severity="CRITICAL",
                      title="Suspicious transaction detected",
                      message=f"Rs {amount:,.0f} at {merchant} ({city}, {country}) {outcome} flagged - risk score "
                              f"{txn.risk_score}/100. Ask the assistant about it or block your card.")
        db.add(alert)
    return txn, alert


def fraud_scan(db: Session, customer_id: int, days: int = 30) -> dict:
    flagged = list_transactions(db, customer_id, limit=50, days=days, min_risk="MEDIUM")
    return {
        "period_days": days,
        "suspicious_count": len(flagged),
        "high_risk_count": sum(1 for t in flagged if t["risk_level"] == "HIGH"),
        "transactions": flagged,
        "cards": list_cards(db, customer_id),
    }


def get_transaction(db: Session, customer_id: int, txn_id: int) -> dict:
    t = db.get(Transaction, txn_id)
    if not t or t.account_id not in _account_ids(db, customer_id):
        raise BankingError(f"Transaction {txn_id} not found for this customer")
    return txn_to_dict(t)


def block_card(db: Session, customer_id: int, card_id: int, reason: str) -> dict:
    card = db.get(Card, card_id)
    if not card or card.customer_id != customer_id:
        raise BankingError(f"Card {card_id} not found for this customer")
    card.status = "BLOCKED"
    # flagged transactions on this account are moved to dispute review
    db.add(Alert(customer_id=customer_id, type="CARD", severity="WARNING", title="Card blocked",
                 message=f"Your {card.network} {card.type.lower()} card {card.masked_number} has been blocked. "
                         f"Reason: {reason}. A replacement card will be dispatched in 5-7 working days."))
    return {"card_id": card.id, "number": card.masked_number, "status": card.status}


def unblock_card(db: Session, customer_id: int, card_id: int) -> dict:
    card = db.get(Card, card_id)
    if not card or card.customer_id != customer_id:
        raise BankingError("Card not found")
    card.status = "ACTIVE"
    return {"card_id": card.id, "status": card.status}


# ---------- Credit / Loan API ----------

def credit_report(db: Session, customer_id: int) -> dict:
    r = db.scalars(select(CreditReport).where(CreditReport.customer_id == customer_id)).first()
    if not r:
        return {"score": None, "note": "No bureau record"}
    band = ("No history" if r.score is None else "Excellent" if r.score >= 780 else "Good" if r.score >= 720
            else "Fair" if r.score >= 650 else "Poor")
    return {"score": r.score, "band": band, "enquiries_last_6m": r.enquiries_6m,
            "missed_payments_last_12m": r.missed_payments_12m,
            "credit_utilisation": r.credit_utilisation, "updated": r.updated_at.date().isoformat()}


def list_loans(db: Session, customer_id: int) -> list[dict]:
    rows = db.scalars(select(Loan).where(Loan.customer_id == customer_id)).all()
    return [{"id": l.id, "type": l.type, "principal": l.principal, "outstanding": l.outstanding,
             "interest_rate": l.interest_rate, "emi": l.emi, "tenure_months": l.tenure_months,
             "status": l.status} for l in rows]


def assess_loan(db: Session, customer_id: int, loan_type: str, amount: float, tenure_months: int) -> dict:
    c = get_customer(db, customer_id)
    report = db.scalars(select(CreditReport).where(CreditReport.customer_id == customer_id)).first()
    existing = sum(l["emi"] for l in list_loans(db, customer_id) if l["status"] == "ACTIVE")
    d = loan_rules.assess_loan(
        loan_type, amount, tenure_months, c.monthly_income, existing,
        report.score if report else None, c.kyc_status, report.missed_payments_12m if report else 0,
    )
    return {**d.__dict__, "monthly_income": c.monthly_income, "existing_emis": existing}


def apply_for_loan(db: Session, customer_id: int, loan_type: str, amount: float, tenure_months: int) -> dict:
    result = assess_loan(db, customer_id, loan_type, amount, tenure_months)
    if result["decision"] != "APPROVED":
        raise BankingError("Loan is not pre-approved; cannot submit application. " + " ".join(result["reasons"]))
    loan = Loan(customer_id=customer_id, type=result["loan_type"], principal=amount, outstanding=amount,
                interest_rate=result["interest_rate"], tenure_months=result["tenure_months"],
                emi=result["emi"], status="APPLIED")
    db.add(loan)
    db.flush()
    db.add(Alert(customer_id=customer_id, type="LOAN", severity="INFO", title="Loan application submitted",
                 message=f"{loan.type.title()} loan of Rs {amount:,.0f} for {loan.tenure_months} months "
                         f"(EMI Rs {loan.emi:,.0f}) submitted. Reference SB-LN-{loan.id:05d}."))
    return {"application_id": f"SB-LN-{loan.id:05d}", "status": "APPLIED", "emi": loan.emi,
            "interest_rate": loan.interest_rate}


# ---------- Notifications ----------

def list_alerts(db: Session, customer_id: int, unread_only: bool = False, limit: int = 20) -> list[dict]:
    q = select(Alert).where(Alert.customer_id == customer_id)
    if unread_only:
        q = q.where(Alert.read.is_(False))
    q = q.order_by(Alert.created_at.desc()).limit(limit)
    return [alert_to_dict(a) for a in db.scalars(q)]


def alert_to_dict(a: Alert) -> dict:
    return {"id": a.id, "type": a.type, "severity": a.severity, "title": a.title, "message": a.message,
            "transaction_id": a.transaction_id, "read": a.read,
            "created_at": a.created_at.isoformat(timespec="seconds")}


def create_alert(db: Session, customer_id: int, title: str, message: str, severity: str = "INFO",
                 type_: str = "INFO") -> Alert:
    a = Alert(customer_id=customer_id, type=type_, severity=severity, title=title, message=message)
    db.add(a)
    db.flush()
    return a

