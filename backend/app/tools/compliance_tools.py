"""Tools for the Compliance & Policy Agent: retrieval over the bank's policy documents (RAG)."""
from ..rag.retriever import get_index
from ..services import banking
from .common import in_session, make_tool


def make_compliance_tools(customer_id: int) -> list:
    def search_policies(query: str) -> list:
        """Search SmartBank's official policy documents (loan policy, KYC/AML policy, fees and charges,
        card fraud and dispute policy, account terms). Returns the most relevant sections with their
        source document and section name. Use a specific query, e.g. 'personal loan foreclosure charges'."""
        return [{"citation": f"{r['title']} › {r['section']}", "text": r["text"]}
                for r in get_index().search(query, k=4)]

    def get_my_kyc_status() -> dict:
        """Get the customer's current KYC status, segment and whether a travel notice is on file."""
        p = in_session(banking.customer_profile)(customer_id)
        return {"kyc_status": p["kyc_status"], "segment": p["segment"], "travel_notice": p["travel_notice"]}

    return [make_tool(search_policies), make_tool(get_my_kyc_status)]
