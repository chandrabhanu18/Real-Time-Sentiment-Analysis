import { useEffect, useMemo, useState } from "react";
import DistributionChart from "./DistributionChart.jsx";
import SentimentChart from "./SentimentChart.jsx";
import LiveFeed from "./LiveFeed.jsx";
import MetricsCards from "./MetricsCards.jsx";
import {
  connectWebSocket,
  fetchAggregateData,
  fetchDistribution,
  fetchPosts,
} from "../services/api.js";

const emptyDistribution = { positive: 0, negative: 0, neutral: 0 };

export default function Dashboard() {
  const [distributionData, setDistributionData] = useState(emptyDistribution);
  const [trendData, setTrendData] = useState([]);
  const [recentPosts, setRecentPosts] = useState([]);
  const [metrics, setMetrics] = useState({ total: 0, positive: 0, negative: 0, neutral: 0 });
  const [connectionStatus, setConnectionStatus] = useState("connecting");
  const [lastUpdate, setLastUpdate] = useState(null);

  const metricsLabel = useMemo(() => {
    if (!lastUpdate) return "-";
    return new Date(lastUpdate).toLocaleTimeString();
  }, [lastUpdate]);

  useEffect(() => {
    let ws;
    let mounted = true;
    let refreshTimer;

    async function loadAggregates() {
      const [dist, trend] = await Promise.all([
        fetchDistribution(24),
        fetchAggregateData("hour"),
      ]);

      if (!mounted) return;
      setDistributionData(dist.distribution || emptyDistribution);
      setMetrics({
        total: dist.total || 0,
        positive: dist.distribution?.positive || 0,
        negative: dist.distribution?.negative || 0,
        neutral: dist.distribution?.neutral || 0,
      });
      setTrendData(trend.data || []);
      setLastUpdate(Date.now());
    }

    async function loadInitial() {
      const posts = await fetchPosts(40, 0);
      if (!mounted) return;
      setRecentPosts(posts.posts || []);
      await loadAggregates();
    }

    loadInitial().catch(() => undefined);
    refreshTimer = setInterval(() => {
      loadAggregates().catch(() => undefined);
    }, 30000);

    ws = connectWebSocket(
      (message) => {
        if (!mounted) return;
        if (message.type === "connected") {
          setConnectionStatus("connected");
        }
        if (message.type === "new_post") {
          setRecentPosts((prev) => [message.data, ...prev].slice(0, 60));
        }
        if (message.type === "metrics_update") {
          const metricsData = message.data?.last_hour || message.data?.last_24_hours;
          if (metricsData) {
            setMetrics({
              total: metricsData.total,
              positive: metricsData.positive,
              negative: metricsData.negative,
              neutral: metricsData.neutral,
            });
          }
        }
        setLastUpdate(Date.now());
      },
      () => setConnectionStatus("disconnected"),
      () => setConnectionStatus("disconnected")
    );

    return () => {
      mounted = false;
      if (refreshTimer) {
        clearInterval(refreshTimer);
      }
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.close();
      }
    };
  }, []);

  return (
    <div className="page">
      <header className="header">
        <div>
          <p className="eyebrow">Real-Time Sentiment Analysis Dashboard</p>
          <h1>Pulse of the Crowd</h1>
        </div>
        <div className="status">
          <span className={`dot ${connectionStatus}`} />
          <div>
            <div className="status-label">Status: {connectionStatus}</div>
            <div className="status-sub">Last update: {metricsLabel}</div>
          </div>
        </div>
      </header>

      <main className="grid">
        <section className="panel span-2">
          <DistributionChart data={distributionData} metrics={metrics} />
        </section>
        <section className="panel span-2">
          <LiveFeed posts={recentPosts} />
        </section>

        <section className="panel span-4">
          <SentimentChart data={trendData} />
        </section>

        <section className="panel span-4">
          <MetricsCards metrics={metrics} />
        </section>
      </main>
    </div>
  );
}
