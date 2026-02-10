const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export async function fetchPosts(limit = 50, offset = 0, filters = {}) {
  const params = new URLSearchParams({ limit, offset, ...filters });
  const res = await fetch(`${API_BASE}/api/posts?${params.toString()}`);
  return res.json();
}

export async function fetchDistribution(hours = 24) {
  const res = await fetch(`${API_BASE}/api/sentiment/distribution?hours=${hours}`);
  return res.json();
}

export async function fetchAggregateData(period, startDate, endDate) {
  const params = new URLSearchParams({ period });
  if (startDate) params.set("start_date", startDate);
  if (endDate) params.set("end_date", endDate);
  const res = await fetch(`${API_BASE}/api/sentiment/aggregate?${params.toString()}`);
  return res.json();
}

export function connectWebSocket(onMessage, onError, onClose) {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${protocol}://${window.location.hostname}:8000/ws/sentiment`);
  ws.onmessage = (evt) => onMessage(JSON.parse(evt.data));
  ws.onerror = onError;
  ws.onclose = onClose;
  return ws;
}
