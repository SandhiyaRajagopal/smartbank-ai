"""Tools for the Fraud/Risk Agent. Risk scores come from services/fraud_rules.py, never from the LLM."""
from ..services import banking
from .common import in_session, make_tool


def make_fraud_tools(customer_id: int) -> list:
    def scan_suspicious_transactions(days: int = 30) -> dict:
        """Scan the customer's transactions from the last N days and return every MEDIUM or HIGH risk
        transaction with its rule-based risk score (0-100) and the reasons it was flagged.
        Also returns the customer's cards and their status (ACTIVE/BLOCKED)."""
        return in_session(banking.fraud_scan)(customer_id, days=days)

    def get_transaction_details(transaction_id: int) -> dict:
        """Get full details of one transaction by id, including risk score, risk level and risk reasons."""
        return in_session(banking.get_transaction)(customer_id, transaction_id)

    def list_cards() -> list:
        """List the customer's debit/credit cards with ids, masked numbers and status."""
        return in_session(banking.list_cards)(customer_id)

    def block_card(card_id: int, reason: str) -> dict:
        """Block (freeze) one of the customer's cards to stop further transactions.
        SENSITIVE ACTION: the customer must confirm in the app before it executes.
        card_id: id from list_cards / scan results. reason: short reason, e.g. 'suspected fraud'."""
        return in_session(banking.block_card)(customer_id, card_id, reason)

    return [
        make_tool(scan_suspicious_transactions),
        make_tool(get_transaction_details),
        make_tool(list_cards),
        make_tool(block_card, requires_confirmation=True),
    ]
