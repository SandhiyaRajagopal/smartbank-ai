"""RAG tests run in BM25-only mode (no API key in tests), which also proves the graceful fallback."""
from backend.app.config import settings
from backend.app.rag.ingest import load_chunks
from backend.app.rag.retriever import PolicyIndex
from backend.app.tools.compliance_tools import make_compliance_tools


def test_policies_are_chunked_by_section():
    chunks = load_chunks(settings.policies_dir)
    assert len(chunks) >= 25
    assert {c.source for c in chunks} == {"loan_policy.md", "kyc_aml_policy.md", "fees_charges.md",
                                          "card_fraud_dispute.md", "account_terms.md"}
    assert all(c.text.startswith(c.title) for c in chunks)


def test_keyword_retrieval_finds_the_right_sections(tmp_path):
    index = PolicyIndex(settings.policies_dir, str(tmp_path))
    top = index.search("foreclosure charges personal loan")[0]
    assert top["section"] == "Prepayment and foreclosure"
    assert index.mode == "bm25_only"

    assert index.search("which documents are accepted for KYC")[0]["section"] == "Accepted documents"
    assert index.search("liability for unauthorised transaction")[0]["source"] == "card_fraud_dispute.md"


def test_compliance_tool_returns_citations():
    search = make_compliance_tools(1)[0]
    import json
    results = json.loads(search.invoke({"query": "minimum average monthly balance savings"}))
    assert results and "›" in results[0]["citation"]
    assert "Fees and Charges" in results[0]["citation"]
