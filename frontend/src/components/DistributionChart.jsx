import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

const COLORS = {
  positive: "#10b981",
  negative: "#ef4444",
  neutral: "#6b7280",
};

export default function DistributionChart({ data, metrics }) {
  const chartData = [
    { name: "Positive", value: data.positive || 0, key: "positive" },
    { name: "Negative", value: data.negative || 0, key: "negative" },
    { name: "Neutral", value: data.neutral || 0, key: "neutral" },
  ].filter((entry) => entry.value > 0);

  return (
    <div className="chart-card">
      <div className="panel-title">
        <h2>Sentiment Distribution</h2>
        <p>Snapshot of the last 24 hours</p>
      </div>
      {chartData.length === 0 ? (
        <div className="empty-state">No sentiment data yet.</div>
      ) : (
        <div className="chart-wrap">
          <ResponsiveContainer width="100%" height={300}>
            <PieChart>
              <Pie
                data={chartData}
                dataKey="value"
                nameKey="name"
                innerRadius={90}
                outerRadius={130}
                paddingAngle={2}
              >
                {chartData.map((entry) => (
                  <Cell key={entry.key} fill={COLORS[entry.key]} />
                ))}
              </Pie>
              <Tooltip />
              <Legend verticalAlign="bottom" height={36} />
            </PieChart>
          </ResponsiveContainer>
          <div className="distribution-metrics">
            <div>
              <span>Total</span>
              <strong>{metrics.total}</strong>
            </div>
            <div>
              <span>Positive</span>
              <strong>{metrics.positive}</strong>
            </div>
            <div>
              <span>Negative</span>
              <strong>{metrics.negative}</strong>
            </div>
            <div>
              <span>Neutral</span>
              <strong>{metrics.neutral}</strong>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
