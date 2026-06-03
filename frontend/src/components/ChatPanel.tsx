import { FormEvent, useState } from "react";
import type { ChatResponse } from "../types";
import { sendChat } from "../api/client";
import { CitationPanel } from "./CitationPanel";
import { RetrievalDetails } from "./RetrievalDetails";
import { UserAnswerView } from "./UserAnswerView";

export function ChatPanel() {
  const [message, setMessage] = useState("");
  const [ticker, setTicker] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ChatResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!message.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const data = await sendChat(message.trim(), ticker.trim() || undefined);
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="chat-panel">
      <form onSubmit={onSubmit} className="chat-form">
        <label>
          Ticker (optional)
          <input
            value={ticker}
            onChange={(e) => setTicker(e.target.value.toUpperCase())}
            placeholder="RJF"
            maxLength={8}
          />
        </label>
        <label>
          Question
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="How does Raymond James describe its wealth management business?"
            rows={3}
            required
          />
        </label>
        <button type="submit" disabled={loading}>
          {loading ? "Thinking…" : "Ask copilot"}
        </button>
      </form>

      {error && <p className="error">{error}</p>}

      {result && (
        <div className="answer-block">
          <h2>Answer</h2>
          {result.debug_info?.retrieval_skipped &&
            result.debug_info?.detected_domain === "out_of_domain" && (
              <div className="out-of-domain-card">
                <h3>Out-of-domain query</h3>
                <p>
                  This assistant specializes in financial filings, annual reports,
                  and company analysis. Please ask a finance-related question.
                </p>
              </div>
            )}
          {!(result.debug_info?.retrieval_skipped &&
            result.debug_info?.detected_domain === "out_of_domain") &&
          (result.user_answer?.answer?.trim() ||
          result.user_answer?.text?.trim() ||
          result.answer?.trim()) ? (
          <UserAnswerView
            userAnswer={
              result.user_answer?.answer
                ? result.user_answer
                : {
                    answer: result.answer_body || result.answer || "",
                    key_details: [],
                    relevant_metrics: [],
                    sources: [],
                    confidence: "Medium",
                    text: result.answer || "",
                  }
            }
          />
          ) : (
            <p className="validation-notes">
              No answer was returned. Check Retrieval Details below or restart
              the backend.
            </p>
          )}
          <CitationPanel sources={result.sources} />
          {result.debug_info && (
            <RetrievalDetails debug={result.debug_info} />
          )}
        </div>
      )}
    </section>
  );
}
