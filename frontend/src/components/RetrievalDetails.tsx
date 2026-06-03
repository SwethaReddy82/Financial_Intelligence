import type { DebugInfo } from "../types";

interface Props {
  debug: DebugInfo;
}

export function RetrievalDetails({ debug }: Props) {
  const hasContent =
    (debug.detected_companies?.length ?? 0) > 0 ||
    Object.keys(debug.applied_filters ?? {}).length > 0 ||
    (debug.retrieved_chunks?.length ?? 0) > 0 ||
    debug.groundedness_score != null;

  if (!hasContent) return null;

  return (
    <details className="retrieval-details">
      <summary>Retrieval Details</summary>
      <div className="retrieval-details-body">
        {debug.detected_companies && debug.detected_companies.length > 0 && (
          <div className="debug-row">
            <h4>Detected companies</h4>
            <ul>
              {debug.detected_companies.map((c) => (
                <li key={c.ticker}>
                  {c.company_name} ({c.ticker})
                </li>
              ))}
            </ul>
          </div>
        )}

        {debug.applied_filters &&
          Object.keys(debug.applied_filters).length > 0 && (
            <div className="debug-row">
              <h4>Filters applied</h4>
              <ul>
                {debug.applied_filters.companies && (
                  <li>
                    Companies:{" "}
                    {(debug.applied_filters.companies as string[]).join(", ")}
                  </li>
                )}
                {debug.applied_filters.mode && (
                  <li>Mode: {String(debug.applied_filters.mode)}</li>
                )}
              </ul>
            </div>
          )}

        {debug.additional_sources && debug.additional_sources.length > 0 && (
          <div className="debug-row">
            <h4>Additional sources</h4>
            <ul>
              {debug.additional_sources.map((s, i) => (
                <li key={i}>{s}</li>
              ))}
            </ul>
          </div>
        )}

        {debug.retrieved_chunks && debug.retrieved_chunks.length > 0 && (
          <div className="debug-row">
            <h4>Retrieved chunks</h4>
            <ul className="chunk-debug-list">
              {debug.retrieved_chunks.map((c) => (
                <li key={c.chunk_id}>
                  <code className="chunk-id">{c.chunk_id.slice(0, 8)}…</code>
                  {c.ticker && <span> · {c.ticker}</span>}
                  {c.section_name && <span> · {c.section_name}</span>}
                  {c.relevance_score != null && (
                    <span> · score {c.relevance_score.toFixed(2)}</span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="debug-row debug-scores">
          <h4>Quality scores</h4>
          <ul>
            {debug.groundedness_score != null && (
              <li>Groundedness: {debug.groundedness_score.toFixed(2)}</li>
            )}
            {debug.citation_coverage != null && (
              <li>Citation coverage: {debug.citation_coverage.toFixed(2)}</li>
            )}
            {debug.hallucination_risk != null && (
              <li>Hallucination risk: {debug.hallucination_risk.toFixed(2)}</li>
            )}
            <li>Route: {debug.route || "—"}</li>
            {debug.confidence_display && (
              <li>Confidence: {debug.confidence_display}</li>
            )}
            <li>
              Internal score: {(debug.confidence_score ?? 0).toFixed(2)}
            </li>
          </ul>
        </div>

        {debug.company_coverage && debug.company_coverage.length > 0 && (
          <div className="debug-row">
            <h4>Company coverage</h4>
            <ul>
              {debug.company_coverage.map((c) => (
                <li key={c.ticker}>
                  {c.display_name}: {c.status}
                </li>
              ))}
            </ul>
          </div>
        )}

        {debug.validation_notes && (
          <p className="debug-notes">{debug.validation_notes}</p>
        )}
      </div>
    </details>
  );
}
