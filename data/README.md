# Knowledge base data

## Local files (your PDFs) — `data/raw/`

Drop PDFs, TXT, or MD **directly in `data/raw/`** (no subfolders required).

Your current files are supported:

| File | Detected ticker | Detected type |
|------|-----------------|---------------|
| `jpmc-corp-10k-2025.pdf` | JPM | 10-K |
| `MS_10k1225.pdf` | MS | 10-K |
| `Raymond James Financial 2025 Annual Report.pdf` | RJF | ANNUAL_REPORT |

Then run:

```bash
make ingest
```

Or ingest **only** local PDFs (skip SEC download):

```bash
make ingest-local
```

## Automatic SEC (optional)

`make ingest` also fetches latest **10-K + 10-Q** from EDGAR for tickers in `SEC_TICKERS` (see `.env`).

Requires valid `OPENAI_API_KEY` and `SEC_USER_AGENT`.

## Optional subfolders

If you recreate them, these still work:

- `earnings_transcripts/`
- `investor_presentations/`
- `annual_reports/`

## Manifest

See [knowledge_base.json](knowledge_base.json).
