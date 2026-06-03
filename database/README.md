# Database

PostgreSQL 16 with **pgvector** extension.

## Init

Scripts in `init/` run automatically when the Docker container starts for the first time.

## Connect locally

```bash
psql postgresql://wealth:wealth@localhost:5432/wealth_copilot
```

## Tables (overview)

- `documents` — filing or PDF metadata
- `document_chunks` — text chunks + `embedding` vector(1536)

Adjust vector dimensions if you change the embedding model.

**Full schema documentation:** [../docs/GUIDE.md §9](../docs/GUIDE.md#9-database-schema-explanation)
