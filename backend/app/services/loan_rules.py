"""Deterministic loan eligibility engine (the simulated "Loan Origination System").

Indian retail lending basics used here:
- EMI formula:  EMI = P * r * (1+r)^n / ((1+r)^n - 1),  r = monthly rate, n = months
- FOIR (Fixed Obligation to Income Ratio) = all EMIs / monthly income; banks usually cap it at 50%
- Credit score (CIBIL-like, 300-900) decides minimum eligibility and the interest rate band
"""
from dataclasses import dataclass, field

# loan type -> (base annual rate %, max tenure months, max amount as multiple of monthly income, min score)
PRODUCTS = {
    "PERSONAL": (11.0, 60, 20, 700),
    "CAR": (9.0, 84, 30, 680),
    "HOME": (8.5, 360, 80, 700),
    "EDUCATION": (9.5, 120, 40, 650),
}
MAX_FOIR = 0.50


@dataclass
class LoanDecision:
    decision: str  # APPROVED / CONDITIONAL / DECLINED
    loan_type: str
    requested_amount: float
    tenure_months: int
    interest_rate: float | None = None
    emi: float | None = None
    foir_after_loan: float | None = None
    max_eligible_amount: float = 0.0
    reasons: list[str] = field(default_factory=list)


def calculate_emi(principal: float, annual_rate: float, months: int) -> float:
    if months <= 0:
        raise ValueError("tenure must be positive")
    r = annual_rate / 12 / 100
    if r == 0:
        return round(principal / months, 2)
    factor = (1 + r) ** months
    return round(principal * r * factor / (factor - 1), 2)


def principal_for_emi(emi: float, annual_rate: float, months: int) -> float:
    """Inverse of calculate_emi: largest loan a given EMI can repay."""
    r = annual_rate / 12 / 100
    factor = (1 + r) ** months
    return emi * (factor - 1) / (r * factor)


def rate_for_score(loan_type: str, score: int) -> float:
    base = PRODUCTS[loan_type][0]
    if score >= 780:
        return base
    if score >= 740:
        return base + 0.75
    if score >= 700:
        return base + 1.5
    return base + 2.5


def assess_loan(
    loan_type: str,
    amount: float,
    tenure_months: int,
    monthly_income: float,
    existing_emis: float,
    credit_score: int | None,
    kyc_status: str = "VERIFIED",
    missed_payments_12m: int = 0,
) -> LoanDecision:
    loan_type = loan_type.upper()
    if loan_type not in PRODUCTS:
        raise ValueError(f"Unknown loan type {loan_type}. Choose one of {list(PRODUCTS)}")
    base_rate, max_tenure, income_multiple, min_score = PRODUCTS[loan_type]
    d = LoanDecision("DECLINED", loan_type, amount, tenure_months)

    if tenure_months > max_tenure:
        d.reasons.append(f"Tenure capped at {max_tenure} months for {loan_type} loans; assessed at {max_tenure}.")
        tenure_months = d.tenure_months = max_tenure

    # Hard stops
    if kyc_status != "VERIFIED":
        d.reasons.append("KYC is not verified - complete KYC before applying.")
        return d
    if credit_score is None:
        d.reasons.append("No credit history found with the bureau (new-to-credit customer).")
        return d
    if credit_score < min_score:
        d.reasons.append(f"Credit score {credit_score} is below the minimum {min_score} for {loan_type} loans.")
        return d
    if missed_payments_12m >= 2:
        d.reasons.append(f"{missed_payments_12m} missed payments in the last 12 months.")
        return d

    rate = rate_for_score(loan_type, credit_score)
    emi = calculate_emi(amount, rate, tenure_months)
    foir = (existing_emis + emi) / monthly_income
    d.interest_rate, d.emi, d.foir_after_loan = rate, emi, round(foir, 3)

    # Max amount = limited by income multiple AND by the EMI room left under the FOIR cap
    emi_room = max(0.0, MAX_FOIR * monthly_income - existing_emis)
    d.max_eligible_amount = round(
        min(income_multiple * monthly_income, principal_for_emi(emi_room, rate, tenure_months)), -3
    )

    if foir <= MAX_FOIR and amount <= income_multiple * monthly_income:
        d.decision = "APPROVED"
        d.reasons.append(f"Credit score {credit_score} qualifies for {rate:.2f}% p.a.")
        d.reasons.append(f"Total EMIs would be {foir:.0%} of income (limit {MAX_FOIR:.0%}).")
    elif d.max_eligible_amount >= 50_000:
        d.decision = "CONDITIONAL"
        d.reasons.append(
            f"Requested amount is too high for current income/obligations (EMI burden {foir:.0%}); "
            f"eligible up to Rs {d.max_eligible_amount:,.0f}."
        )
    else:
        d.reasons.append(
            f"Existing EMIs already use {existing_emis / monthly_income:.0%} of income; "
            f"no room for a new EMI under the {MAX_FOIR:.0%} FOIR limit."
        )
    return d
