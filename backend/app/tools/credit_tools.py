"""Tools for the Credit/Loan Agent. Eligibility and EMI come from services/loan_rules.py."""
from ..services import banking, loan_rules
from .common import in_session, make_tool


def make_credit_tools(customer_id: int) -> list:
    def get_credit_score() -> dict:
        """Get the customer's credit bureau report: score (300-900, None = no history), band,
        recent enquiries, missed payments and credit utilisation."""
        return in_session(banking.credit_report)(customer_id)

    def get_existing_loans() -> list:
        """List the customer's loans with type, outstanding amount, interest rate, EMI and status."""
        return in_session(banking.list_loans)(customer_id)

    def check_loan_eligibility(loan_type: str, amount: float, tenure_months: int) -> dict:
        """Run the bank's loan eligibility rules. loan_type: PERSONAL, CAR, HOME or EDUCATION.
        amount: requested principal in INR (e.g. 5 lakh = 500000). tenure_months: e.g. 3 years = 36.
        Returns decision (APPROVED / CONDITIONAL / DECLINED), interest rate, EMI, FOIR after the loan,
        maximum eligible amount and the reasons."""
        return in_session(banking.assess_loan)(customer_id, loan_type, amount, tenure_months)

    def calculate_emi(amount: float, annual_interest_rate: float, tenure_months: int) -> dict:
        """Calculate the monthly EMI for any amount, annual interest rate (%) and tenure in months.
        Use this for what-if questions (e.g. 'what if I take it for 5 years?')."""
        emi = loan_rules.calculate_emi(amount, annual_interest_rate, tenure_months)
        return {"emi": emi, "total_payable": round(emi * tenure_months, 2),
                "total_interest": round(emi * tenure_months - amount, 2)}

    def apply_for_loan(loan_type: str, amount: float, tenure_months: int) -> dict:
        """Submit a loan application. Only possible when check_loan_eligibility returned APPROVED.
        SENSITIVE ACTION: the customer must confirm in the app before it executes."""
        return in_session(banking.apply_for_loan)(customer_id, loan_type, amount, tenure_months)

    return [
        make_tool(get_credit_score),
        make_tool(get_existing_loans),
        make_tool(check_loan_eligibility),
        make_tool(calculate_emi),
        make_tool(apply_for_loan, requires_confirmation=True),
    ]
