# Database

Canonical documentation: **[GUIDE.md §9](GUIDE.md#9-database-schema-explanation)**

## Setup

```bash
make db-up
psql postgresql://wealth:wealth@localhost:5432/wealth_copilot
```

Init scripts run from `database/init/` on first container start.

## Schema files

| File | Purpose |
|------|---------|
| `001_extensions.sql` | `CREATE EXTENSION vector` |
| `002_schema.sql` | `documents`, `document_chunks`, indexes |

## ORM

SQLAlchemy models: `backend/app/db/models.py`
