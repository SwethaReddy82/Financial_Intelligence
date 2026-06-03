-- Optional: speed up metadata ticker filters (run after ingest)
CREATE INDEX IF NOT EXISTS idx_chunks_metadata_ticker
  ON document_chunks ((metadata->>'ticker'));
