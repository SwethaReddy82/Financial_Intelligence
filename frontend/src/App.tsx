import { useEffect, useState } from "react";
import { fetchDocumentStats } from "./api/client";
import { ChatPanel } from "./components/ChatPanel";
import "./App.css";

export default function App() {
  const [stats, setStats] = useState<{ documents: number; chunks: number } | null>(
    null
  );

  useEffect(() => {
    fetchDocumentStats()
      .then(setStats)
      .catch(() => setStats(null));
  }, []);

  return (
    <div className="app">
      <header>
        <h1>Wealth Intelligence Copilot</h1>
        <p className="subtitle">
          Evidence-backed answers from SEC filings and annual reports — with citations,
          confidence scoring, and retrieval transparency for wealth management research.
        </p>
        {stats && (
          <p className="stats">
            {stats.db_ok === false ? (
              <>Database offline — {stats.hint ?? "run make db-up"}</>
            ) : (
              <>
                Indexed: {stats.documents} documents · {stats.chunks} chunks
              </>
            )}
          </p>
        )}
      </header>
      <ChatPanel />
    </div>
  );
}
