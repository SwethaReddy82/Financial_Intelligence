.PHONY: db-up db-down setup-backend backend frontend ingest ingest-local

VENV := backend/.venv
PY := $(VENV)/bin/python
UVICORN := $(VENV)/bin/uvicorn

db-up:
	docker compose up -d db

db-down:
	docker compose down

setup-backend:
	cd backend && python3 -m venv .venv && $(PY) -m pip install -r requirements.txt

backend:
	@test -x $(UVICORN) || (echo "Run: make setup-backend" && exit 1)
	cd backend && ../$(UVICORN) app.main:app --reload --host 0.0.0.0 --port 8000

frontend:
	cd frontend && npm install && npm run dev

ingest:
	@test -x $(PY) || (echo "Run: make setup-backend" && exit 1)
	cd backend && ../$(PY) -m scripts.ingest_sample

ingest-local:
	@test -x $(PY) || (echo "Run: make setup-backend" && exit 1)
	cd backend && ../$(PY) -m scripts.ingest_local
