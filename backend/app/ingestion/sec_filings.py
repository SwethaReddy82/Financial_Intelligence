"""Fetch company metadata and recent filings from SEC EDGAR."""

from dataclasses import dataclass

import httpx

from app.core.config import settings

SEC_BASE = "https://data.sec.gov"
TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"


@dataclass
class FilingRef:
    ticker: str
    cik: str
    form_type: str
    filed_at: str
    accession_number: str
    primary_document: str

    @property
    def filing_url(self) -> str:
        accession_no_dashes = self.accession_number.replace("-", "")
        return (
            f"https://www.sec.gov/Archives/edgar/data/"
            f"{int(self.cik)}/{accession_no_dashes}/{self.primary_document}"
        )


def _headers() -> dict[str, str]:
    return {
        "User-Agent": settings.sec_user_agent,
        "Accept-Encoding": "gzip, deflate",
    }


async def resolve_cik(ticker: str) -> str | None:
    """Map ticker symbol to zero-padded CIK using SEC company_tickers.json."""
    async with httpx.AsyncClient(headers=_headers(), timeout=30.0) as client:
        resp = await client.get(TICKER_MAP_URL)
        resp.raise_for_status()
        data = resp.json()

    target = ticker.upper()
    for entry in data.values():
        if entry.get("ticker", "").upper() == target:
            return str(entry["cik_str"]).zfill(10)
    return None


async def list_recent_filings(
    ticker: str,
    form_types: tuple[str, ...] = ("10-K", "10-Q"),
    limit: int = 3,
) -> list[FilingRef]:
    """List recent SEC filings (newest first), up to `limit` matches."""
    cik = await resolve_cik(ticker)
    if not cik:
        return []

    url = f"{SEC_BASE}/submissions/CIK{cik}.json"
    async with httpx.AsyncClient(headers=_headers(), timeout=30.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        payload = resp.json()

    recent = payload.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])
    primaries = recent.get("primaryDocument", [])

    refs: list[FilingRef] = []
    for form, filed, acc, doc in zip(forms, dates, accessions, primaries, strict=False):
        if form not in form_types:
            continue
        refs.append(
            FilingRef(
                ticker=ticker.upper(),
                cik=cik,
                form_type=form,
                filed_at=filed,
                accession_number=acc,
                primary_document=doc,
            )
        )
        if len(refs) >= limit:
            break
    return refs


async def list_latest_filings_per_form(
    ticker: str,
    form_types: tuple[str, ...] = ("10-K", "10-Q"),
    per_form_limit: int = 1,
) -> list[FilingRef]:
    """
    Latest filing for each form type (e.g. one 10-K + one 10-Q for Apple).
    SEC 'recent' arrays are newest-first, so the first match per form is the latest.
    """
    cik = await resolve_cik(ticker)
    if not cik:
        return []

    url = f"{SEC_BASE}/submissions/CIK{cik}.json"
    async with httpx.AsyncClient(headers=_headers(), timeout=30.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        payload = resp.json()

    recent = payload.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])
    primaries = recent.get("primaryDocument", [])

    counts: dict[str, int] = {f: 0 for f in form_types}
    refs: list[FilingRef] = []

    for form, filed, acc, doc in zip(forms, dates, accessions, primaries, strict=False):
        if form not in form_types:
            continue
        if counts[form] >= per_form_limit:
            continue
        counts[form] += 1
        refs.append(
            FilingRef(
                ticker=ticker.upper(),
                cik=cik,
                form_type=form,
                filed_at=filed,
                accession_number=acc,
                primary_document=doc,
            )
        )
        if all(counts[f] >= per_form_limit for f in form_types):
            break

    return refs


async def download_filing_text(filing: FilingRef) -> str:
    """Download primary filing document as plain text/HTML."""
    async with httpx.AsyncClient(headers=_headers(), timeout=60.0) as client:
        resp = await client.get(filing.filing_url)
        resp.raise_for_status()
        return resp.text
