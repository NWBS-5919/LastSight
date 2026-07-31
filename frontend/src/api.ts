import type { BriefingCard, ScenarioSnapshot } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export function frameUrl(path: string): string {
  // scenario_runner가 넘겨주는 frame_image_url은 "/demo-frames/frames/xxxx.jpg" 형태.
  return path.startsWith("http") ? path : `${API_BASE}${path}`;
}

export async function startScenario(speed = 1.0): Promise<void> {
  await fetch(`${API_BASE}/scenario/start?speed=${speed}`, { method: "POST" });
}

export async function resetScenario(): Promise<void> {
  await fetch(`${API_BASE}/scenario/reset`, { method: "POST" });
}

export async function fetchState(): Promise<ScenarioSnapshot> {
  const res = await fetch(`${API_BASE}/scenario/state`);
  return res.json();
}

export async function fetchBriefing(trackId: string): Promise<BriefingCard> {
  const res = await fetch(`${API_BASE}/briefing/${trackId}`);
  return res.json();
}

export function connectLiveSocket(onMessage: (snapshot: ScenarioSnapshot) => void): WebSocket {
  const wsBase = API_BASE.replace(/^http/, "ws");
  const ws = new WebSocket(`${wsBase}/ws/live`);
  ws.onmessage = (event) => {
    onMessage(JSON.parse(event.data));
  };
  return ws;
}
