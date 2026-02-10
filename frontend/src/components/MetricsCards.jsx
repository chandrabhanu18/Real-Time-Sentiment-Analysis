export default function MetricsCards({ metrics }) {
  const items = [
    { label: "Total", value: metrics.total, tone: "accent" },
    { label: "Positive", value: metrics.positive, tone: "positive" },
    { label: "Negative", value: metrics.negative, tone: "negative" },
    { label: "Neutral", value: metrics.neutral, tone: "neutral" },
  ];

  return (
    <div className="metrics">
      {items.map((item) => (
        <div key={item.label} className={`metric-card ${item.tone}`}>
          <span>{item.label}</span>
          <strong>{item.value}</strong>
        </div>
      ))}
    </div>
  );
}
