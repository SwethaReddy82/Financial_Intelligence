interface Props {
  confidence: number;
  route: string;
}

function label(route: string, confidence: number): string {
  if (route === "refuse") return "Low confidence — refused to speculate";
  if (route === "cautious") return `Cautious answer (${Math.round(confidence * 100)}%)`;
  return `High confidence (${Math.round(confidence * 100)}%)`;
}

export function ConfidenceBadge({ confidence, route }: Props) {
  const level =
    route === "refuse" ? "low" : route === "cautious" ? "medium" : "high";

  return (
    <span className={`confidence-badge confidence-${level}`}>
      {label(route, confidence)}
    </span>
  );
}
