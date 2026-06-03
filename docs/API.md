# API reference

Interactive Swagger UI: **http://localhost:8000/docs**

Canonical documentation: **[GUIDE.md §8](GUIDE.md#8-api-documentation)**

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Redirect to `/docs` |
| `GET` | `/api` | Service index |
| `GET` | `/api/health` | Liveness check |
| `GET` | `/api/documents/stats` | Document/chunk counts |
| `POST` | `/api/chat` | Agentic Q&A with citations |

## Frontend proxy

Vite dev server proxies `/api` → `http://localhost:8000` (see `frontend/vite.config.ts`).
