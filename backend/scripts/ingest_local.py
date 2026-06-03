"""Ingest only files in data/raw/ (no SEC download). Usage: make ingest-local"""

import asyncio
import sys

from app.core.config import settings
from app.db.session import async_session_factory
from app.ingestion.local_documents import ingest_local_raw_files, infer_form_type, infer_ticker


async def main() -> None:
    if not settings.openai_configured:
        print("Set a valid OPENAI_API_KEY in .env before ingesting.", file=sys.stderr)
        sys.exit(1)

    raw = settings.data_raw_dir
    print(f"Ingesting local files from: {raw}")

    async with async_session_factory() as db:
        results = await ingest_local_raw_files(db)
        if not results:
            print("No PDF/TXT/MD files found in data/raw/", file=sys.stderr)
            sys.exit(1)
        for key, count in results.items():
            name = key.split(":", 1)[-1]
            print(
                f"  {name} → ticker={infer_ticker(name)}, "
                f"type={infer_form_type(name)}, {count} chunks"
            )


if __name__ == "__main__":
    asyncio.run(main())
