import type { ChatMessage, ChatReply, ComplianceState, PpeViolationEntry, ScenarioSnapshot, ZoneMapConfig } from "./types";

// 배포(Render 등)에서는 백엔드가 프론트엔드 빌드를 그대로 서빙해 같은 오리진이므로
// 상대 경로("")면 충분하다 — 로컬 개발(vite dev server, 5173)만 별도 오리진(8000)의
// 백엔드를 가리켜야 한다. VITE_API_BASE_URL을 명시하면 항상 그 값이 우선한다.
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? (import.meta.env.DEV ? "http://localhost:8000" : "");

export function frameUrl(path: string): string {
  // scenario_runner가 넘겨주는 frame_image_url은 "/demo-frames/frames/xxxx.jpg" 형태.
  return path.startsWith("http") ? path : `${API_BASE}${path}`;
}

// 사전계산 정지 이미지(초당 1장) 대신 원본 영상을 그대로 재생해 매끄럽게 보여주기 위한 경로.
// 2026-08-04: 처음엔 백엔드가 영상(211MB)을 직접 스트리밍했는데, Render 무료 티어(RAM
// 512MB·CPU 0.1코어)에서 웹소켓 실시간 갱신과 동시에 돌리니 간헐적으로 503이 났다(실측).
// GitHub Release 에셋 URL로 브라우저가 직접 요청하게 하면 Render 서버는 영상을 전혀
// 안 거치므로 이 문제가 사라진다 — Range 요청(탐색)도 GitHub 쪽에서 지원 확인함.
export const DEMO_VIDEO_URL =
  import.meta.env.VITE_DEMO_VIDEO_URL ?? "https://github.com/NWBS-5919/LastSight/releases/download/demo-assets-v1/LastSight_Demo.mp4";

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

export async function sendChatMessage(messages: ChatMessage[]): Promise<ChatReply> {
  const res = await fetch(`${API_BASE}/situation-chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(messages.map((m) => ({ role: m.role, content: m.content }))),
  });
  if (!res.ok) throw new Error("답변을 생성하지 못했습니다.");
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
  // API_BASE가 상대 경로("")일 수 있어(같은 오리진 배포) http를 ws로 바꿔치기하는
  // 방식이 안 통한다 — 그럴 땐 현재 페이지의 origin에서 직접 ws(s) URL을 만든다.
  const wsBase = API_BASE ? API_BASE.replace(/^http/, "ws") : `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}`;
  const ws = new WebSocket(`${wsBase}/ws/live`);
  ws.onmessage = (event) => {
    onMessage(JSON.parse(event.data));
  };
  return ws;
}
