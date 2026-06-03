import { useState } from "react";
import type { SourceCitation } from "../types";

interface Props {
  sources: SourceCitation[];
}

const TOP_EXCERPTS = 3;

export function CitationPanel({ sources }: Props) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  if (!sources.length) return null;

  const sorted = [...sources].sort(
    (a, b) => (b.score ?? 0) - (a.score ?? 0)
  );
  const top = sorted.slice(0, TOP_EXCERPTS);
  const extra = sorted.length - top.length;

  return (
    <details className="citations-expandable">
      <summary>
        View source excerpts ({top.length}
        {extra > 0 ? ` of ${sources.length}` : ""})
      </summary>
      <ul className="citations-list">
        {top.map((s, i) => {
          const title =
            s.title ||
            [s.company_name ?? s.ticker, s.filing_year, s.filing_type ?? s.form_type]
              .filter(Boolean)
              .join(" ");
          const open = expandedId === s.chunk_id;

          return (
            <li key={s.chunk_id} className="citation-item">
              <button
                type="button"
                className="citation-toggle"
                onClick={() =>
                  setExpandedId(open ? null : s.chunk_id)
                }
                aria-expanded={open}
              >
                <span className="citation-title">
                  [{i + 1}] {title}
                </span>
                <span className="citation-hint">
                  {open ? "Hide excerpt" : "Show excerpt"}
                </span>
              </button>
              {open && (
                <div className="citation-excerpt">
                  <p>{s.excerpt}</p>
                  {s.source_url && (
                    <a href={s.source_url} target="_blank" rel="noreferrer">
                      Open filing
                    </a>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </details>
  );
}
