# Backend

FastAPI application with ingestion, RAG, and LangGraph agent modules.

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Load `.env` from the repo root (see `app/core/config.py`).
