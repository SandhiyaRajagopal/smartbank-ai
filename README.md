# SmartBank AI: Multi-Agent Banking Assistant

A simulated real-time banking application in which a **team of AI agents** works together:
a **Supervisor** understands each request and routes it to **specialist agents** (Customer,
Fraud & Risk, Credit & Loan, Compliance & Policy). The agents call **simulated core-banking
APIs** for real data. Fraud alerts stream to the browser **in real time**, and sensitive
actions such as blocking a card wait for the customer's **explicit confirmation**.

Built for the Wrench Wise AI/ML Intern technical assignment *"Simulated Real-Time Banking
Architecture with Multi-Agent Automation using Experimental Models"*.

> All customers, data and policy documents are fictional.

---

## Features

| Area | What it does |
|---|---|
| **Supervisor agent** | Gemini zero-shot intent classification with structured output; decomposes multi-part requests into ordered steps; keyword fallback if the LLM is unavailable |
| **Customer Agent** | Profile, KYC status, balances, cards, transaction history, spending insights |
| **Fraud & Risk Agent** | Explains rule-based risk scores, scans for suspicious activity, proposes card blocking (confirmation required) |
| **Credit & Loan Agent** | Credit score, existing loans, eligibility (FOIR, score bands), EMI what-ifs, loan applications (confirmation required) |
| **Compliance & Policy Agent** | RAG over the bank's policy documents (hybrid vector + BM25 search) with cited answers |
| **Human-in-the-loop** | LangGraph `interrupt()` pauses the workflow until the customer clicks Confirm or Cancel |
| **Real-time simulation** | Live transactions are scored for fraud and pushed over WebSocket, with instant alert toasts |
| **Guardrails** | PII masking (card/Aadhaar/PAN/phone/OTP) before the LLM sees anything; prompt-injection blocking |
| **Memory** | Conversation state persisted per user via the LangGraph SQLite checkpointer |
| **Observability** | In-app Agent Trace panel, LangSmith tracing, audit log table, correlation ids |

## Demo use cases

| # | Try saying… | Agents involved |
|---|---|---|
| 1 | "What's my account balance?" | Customer |
| 2 | "Where did I spend the most this month?" | Customer |
| 3 | "Is there any suspicious activity on my account?" → **Confirm** the card block | Fraud → approval |
| 4 | "Am I eligible for a ₹5 lakh personal loan for 3 years?" then "What about 5 years?" | Credit (with memory) |
| 5 | "What documents do I need for KYC?" / "What are the foreclosure charges on a personal loan?" | Compliance (RAG) |
| 6 | "Check my account for fraud, then tell me if I can get an ₹8 lakh car loan" | Fraud → Credit → merged |

**Demo customers** (password for all: `SmartBank@2026`). Click one on the login page:

| Login | Scenario |
|---|---|
| `priya@smartbank.demo` | Clean account, excellent credit: loans **approved** |
| `arjun@smartbank.demo` | Suspicious Dubai / gift-card transactions: **fraud demo** |
| `rahul@smartbank.demo` | High existing EMIs: loan only **conditionally** eligible (FOIR 61%) |
| `ananya@smartbank.demo` | KYC pending, no credit history: **complete KYC first** |

---

## Quick start

### 1. Choose how to reach Gemini
- **Option A, AI Studio key (simplest):** free key from https://aistudio.google.com/apikey → `GOOGLE_API_KEY`
- **Option B, Vertex AI (used in production):** `gcloud auth application-default login`, then set
  `USE_VERTEXAI=true` and `GCP_PROJECT=<your project>` (no API key needed)
- **LangSmith** (optional, for tracing): https://smith.langchain.com → Settings → API Keys → `LANGSMITH_API_KEY`

### 2. Configure
```bash
cp .env.example .env
```
Then open `.env` and fill in the option you chose. `.env` is gitignored.

### 3a. Run with Docker (recommended)
```bash
docker compose up --build
```
Open **http://localhost:8000**.

### 3b. Run without Docker (development)
Requires Python 3.10+ and Node 20+.
```bash
python -m venv .venv
.venv\Scripts\activate            # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements-dev.txt
uvicorn backend.app.main:app --reload
```
In a second terminal:
```bash
cd frontend
npm install
npm run dev
```
Open **http://localhost:5173**. Vite forwards `/api` and `/ws` to the backend on port 8000.

### 3c. Deploy to Google Cloud Run
```powershell
.\deploy\deploy.ps1
```
Builds the Dockerfile with Cloud Build and runs it on Cloud Run with Gemini on Vertex AI. See **[DEPLOY.md](DEPLOY.md)** for the one-time setup (service accounts, secrets, budget).

### Run the tests
```bash
pytest
```
The tests use a scripted fake LLM, so they need no API key. They cover the business rules, guardrails,
routing, the full LangGraph workflow (including confirm/cancel), RAG, API, WebSocket and the simulator.

### Reset the demo data
```bash
python -m backend.app.db.seed --reset
```

---

## Architecture (summary)

```
React UI ──REST (JWT) / SSE / WebSocket──► FastAPI
                                             │
                     Guardrails ─► Supervisor (Gemini, structured output)
                                             │  routes to 1-3 agents
             ┌──────────────┬────────────────┼──────────────────┐
        Customer        Fraud & Risk     Credit & Loan    Compliance (RAG)
             │              │                │                  │
             └──── per-agent tools ──► simulated banking services ◄── Chroma + BM25
                                             │
                     SQLite (core banking, alerts, audit) · LangGraph checkpointer
```

See **[ARCHITECTURE.md](ARCHITECTURE.md)** for the full design, the decisions behind it and the trade-offs.

## Tech stack
**LLM:** Google Gemini (`gemini-3.8-flash`, embeddings `gemini-embedding-001`) ·
**Agents:** LangGraph 1.x + LangChain · **Tracing:** LangSmith ·
**Backend:** FastAPI, SQLAlchemy, SQLite · **RAG:** Chroma + rank-bm25 ·
**Frontend:** React 19, Vite, Tailwind CSS 4 · **Packaging:** Docker (multi-stage) ·
**Cloud:** Google Cloud Run, Vertex AI, Cloud Build, Secret Manager

## Project layout
```
backend/app/
  agents/      supervisor, specialists, agent loop, LangGraph workflow, state
  tools/       per-agent tool sets (customer, fraud, credit, compliance)
  services/    simulated core banking + deterministic fraud & loan rules
  rag/         policy chunking + hybrid retriever
  realtime/    WebSocket hub + live transaction simulator
  api/         auth, dashboard, streaming chat, WebSocket routes
  guardrails.py, audit.py, config.py, llm.py, main.py
docs/policies/ fictional SmartBank policy documents used by RAG
frontend/      React app
tests/         pytest suite
```
