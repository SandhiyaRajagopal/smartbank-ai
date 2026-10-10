"""Tools for the Customer Agent: profile, balances, transactions, spending insights."""
from typing import Optional

from ..services import banking
from .common import in_session, make_tool


def make_customer_tools(customer_id: int) -> list:
    def get_customer_profile() -> dict:
        """Get the customer's profile: name, city, segment, employment, KYC status, customer since."""
        return in_session(banking.customer_profile)(customer_id)

    def get_account_balances() -> dict:
        """Get all bank accounts of the customer with masked account numbers and current balances (INR),
        plus their debit/credit cards and card status."""
        accounts = in_session(banking.list_accounts)(customer_id)
        cards = in_session(banking.list_cards)(customer_id)
        return {"accounts": accounts, "total_balance": round(sum(a["balance"] for a in accounts), 2),
                "cards": cards}

    def get_recent_transactions(limit: int = 10, days: Optional[int] = None,
                                category: Optional[str] = None) -> list:
        """Get the customer's most recent transactions, newest first.
        limit: how many (max 50). days: only the last N days. category: filter, one of
        SALARY, RENT, EMI, UTILITIES, GROCERIES, FOOD, FUEL, SHOPPING, ENTERTAINMENT, TRANSPORT, HEALTH, GIFT_CARDS."""
        return in_session(banking.list_transactions)(customer_id, limit=min(limit, 50), days=days,
                                                     category=category)

    def get_spending_summary(days: int = 30) -> dict:
        """Summarise spending by category over the last N days: total spent, total received,
        net cash flow and each category's amount and share of spend."""
        return in_session(banking.spending_summary)(customer_id, days=days)

    return [make_tool(f) for f in
            (get_customer_profile, get_account_balances, get_recent_transactions, get_spending_summary)]
