import type { ComplianceState, PpeViolationEntry, ScenarioSnapshot, SituationSummary, ZoneMapConfig } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export function frameUrl(path: string): string {
  // scenario_runner가 넘겨주는 frame_image_url은 "/demo-frames/frames/xxxx.jpg" 형태.
  return path.startsWith("http") ? path : `${API_BASE}${path}`;
}

// 사전계산 정지 이미지(초당 1장) 대신 원본 영상을 그대로 재생해 매끄럽게 보여주기 위한 경로.
export const DEMO_VIDEO_URL = `${API_BASE}/demo-video/source.mp4`;

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

export async function fetchZoneMap(cameraId: string): Promise<ZoneMapConfig> {
  const res = await fetch(`${API_BASE}/zone-maps/${cameraId}`);
  if (!res.ok) throw new Error("구역 정보를 불러오지 못했습니다.");
  return res.json();
}

export async function fetchSituationSummary(): Promise<SituationSummary> {
  const res = await fetch(`${API_BASE}/situation-summary`, { method: "POST" });
  if (!res.ok) throw new Error("브리핑 요약을 생성하지 못했습니다.");
  return res.json();
}

export async function saveZoneMap(config: ZoneMapConfig): Promise<ZoneMapConfig> {
  const res = await fetch(`${API_BASE}/zone-maps/${config.camera_id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  });
  if (!res.ok) throw new Error("구역 정보를 저장하지 못했습니다.");
  return res.json();
}

export async function reviewPpeViolation(
  cameraId: string,
  entryId: string,
  review: { helmet: ComplianceState; vest: ComplianceState },
): Promise<PpeViolationEntry> {
  const res = await fetch(`${API_BASE}/ppe-violations/${cameraId}/${entryId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(review),
  });
  if (!res.ok) throw new Error("검토 내용을 저장하지 못했습니다.");
  return res.json();
}

export async function mergePpeViolations(cameraId: string, idA: string, idB: string): Promise<PpeViolationEntry> {
  const res = await fetch(`${API_BASE}/ppe-violations/${cameraId}/merge`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id_a: idA, id_b: idB }),
  });
  if (!res.ok) throw new Error("두 항목을 합치지 못했습니다.");
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
