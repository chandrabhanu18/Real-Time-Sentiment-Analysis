import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

const formatTime = (iso) => {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
};

export default function SentimentChart({ data }) {
  if (!data || data.length === 0) {
    return (
      <div className="chart-card">
        <div className="panel-title">
          <h2>Sentiment Trend</h2>
          <p>Last 24 hours</p>
        </div>
        <div className="empty-state">No trend data yet.</div>
      </div>
    );
  }

  return (
    <div className="chart-card">
      <div className="panel-title">
        <h2>Sentiment Trend</h2>
        <p>Last 24 hours</p>
      </div>
      <div className="chart-wrap">
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
            <XAxis dataKey="timestamp" tickFormatter={formatTime} stroke="#cbd5f5" />
            <YAxis stroke="#cbd5f5" />
            <Tooltip labelFormatter={formatTime} />
            <Legend />
            <Line type="monotone" dataKey="positive_count" stroke="#10b981" strokeWidth={2} />
            <Line type="monotone" dataKey="negative_count" stroke="#ef4444" strokeWidth={2} />
            <Line type="monotone" dataKey="neutral_count" stroke="#6b7280" strokeWidth={2} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
