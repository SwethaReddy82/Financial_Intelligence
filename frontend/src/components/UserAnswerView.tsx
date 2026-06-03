import type { UserAnswer } from "../types";

interface Props {
  userAnswer: UserAnswer;
}

function confidenceClass(display: string): string {
  if (display.startsWith("High")) return "confidence-high";
  if (display.startsWith("Medium")) return "confidence-medium";
  return "confidence-low";
}

export function UserAnswerView({ userAnswer }: Props) {
  const confDisplay =
    userAnswer.confidence_display ||
    `${userAnswer.confidence} (${userAnswer.confidence_percent ?? 0}%)`;

  return (
    <div className="user-answer">
      <section className="user-answer-section">
        <p className="answer-lead">{userAnswer.answer}</p>
      </section>

      {userAnswer.key_details.length > 0 && (
        <section className="user-answer-section">
          <h3>Key Details</h3>
          <ul>
            {userAnswer.key_details.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        </section>
      )}

      {userAnswer.relevant_metrics.length > 0 && (
        <section className="user-answer-section">
          <h3>Relevant Metrics</h3>
          <ul>
            {userAnswer.relevant_metrics.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        </section>
      )}

      {userAnswer.sources.length > 0 && (
        <section className="user-answer-section">
          <h3>Sources</h3>
          <ul className="source-titles">
            {userAnswer.sources.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        </section>
      )}

      <section className="user-answer-confidence">
        <span className="confidence-label">Confidence</span>
        <span className={`confidence-badge ${confidenceClass(confDisplay)}`}>
          {confDisplay}
        </span>
      </section>
    </div>
  );
}
