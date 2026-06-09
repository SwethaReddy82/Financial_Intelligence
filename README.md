# Agentic Wealth Intelligence Copilot

Portfolio project: an AI copilot that answers questions about public companies using **SEC filings** and **financial PDFs**, backed by **RAG** and a simple **LangGraph** agent workflow.

## Stack

| Layer | Tech |
|-------|------|
| API | FastAPI |
| UI | React + TypeScript (Vite) |
| DB | PostgreSQL + pgvector |
| AI | OpenAI, LangChain, LangGraph |
| Data | SEC EDGAR, PDF documents |

## Project layout

```
wealth-intelligence-copilot/
├── backend/          # FastAPI app, ingestion, RAG, agents
├── frontend/         # React chat UI
├── database/         # SQL init scripts (pgvector, schema)
├── scripts/          # One-off CLI helpers
└── docs/             # Full documentation (see docs/GUIDE.md)
```

## Quick start

1. **Copy env and set keys**

   ```bash
   cp .env.example .env
   # Edit OPENAI_API_KEY and SEC_USER_AGENT (required by SEC)
   ```

2. **Start PostgreSQL**

   ```bash
   make db-up
   ```

3. **Backend** (one-time setup, then run)

   ```bash
   make setup-backend   # creates backend/.venv and installs deps
   make backend         # uses .venv/bin/uvicorn — no manual activate needed
   ```

   Or manually:

   ```bash
   cd backend
   source .venv/bin/activate
   uvicorn app.main:app --reload
   ```

4. **Frontend**

   ```bash
   cd frontend
   npm install
   npm run dev
   ```

5. **Ingest knowledge base** (SEC 10-K/10-Q + local PDFs/transcripts)

   ```bash
   make ingest
   ```

   See [data/README.md](data/README.md). Drop PDFs in `data/raw/` then `make ingest` or `make ingest-local` (local only).

- API: http://localhost:8000/docs  
- UI: http://localhost:5173  

## Documentation

| Topic | Document |
|-------|----------|
| **Full guide** (architecture, data flow, design, tradeoffs, security, API, schema, interview prep, roadmap) | [docs/GUIDE.md](docs/GUIDE.md) |
| Quick architecture reference | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| API | [docs/API.md](docs/API.md) |
| Database | [docs/DATABASE.md](docs/DATABASE.md) |

