import type { ChatMessage, ChatReply, ComplianceState, PpeViolationEntry, ScenarioSnapshot, ZoneMapConfig } from "./types";

// 개발 서버에서는 Vite가 API와 WebSocket을 Render로 프록시하므로 브라우저 관점에서는
// 항상 같은 origin이다. 이 방식이면 localhost/127.0.0.1 차이로 PATCH·POST preflight가
// 막히지 않는다. 로컬 백엔드를 직접 쓸 때만 VITE_API_BASE_URL=http://localhost:8000으로
// 덮어쓸 수 있다. 배포본도 백엔드가 같은 origin에서 정적 파일을 서빙한다.
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

async function responseError(res: Response, fallback: string): Promise<Error> {
  let detail = "";
  try {
    const body = (await res.json()) as { detail?: unknown };
    if (typeof body.detail === "string") detail = ` · ${body.detail}`;
  } catch {
    // 오류 본문이 JSON이 아니면 상태 코드만 표시한다.
  }
  return new Error(`${fallback} (${res.status})${detail}`);
}

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
  const res = await fetch(`${API_BASE}/scenario/start?speed=${speed}`, { method: "POST" });
  if (!res.ok) throw new Error(`시나리오 시작 요청에 실패했습니다. (${res.status})`);
}

export async function resetScenario(): Promise<void> {
  const res = await fetch(`${API_BASE}/scenario/reset`, { method: "POST" });
  if (!res.ok) throw new Error(`시나리오 초기화 요청에 실패했습니다. (${res.status})`);
}

export async function fetchState(): Promise<ScenarioSnapshot> {
  const res = await fetch(`${API_BASE}/scenario/state`);
  if (!res.ok) throw new Error(`시나리오 상태를 불러오지 못했습니다. (${res.status})`);
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

export async function reviewPpeViolation(
  cameraId: string,
  entryId: string,
  review: { helmet: ComplianceState; vest: ComplianceState },
): Promise<PpeViolationEntry> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/ppe-violations/${cameraId}/${entryId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(review),
    });
  } catch {
    throw new Error("백엔드에 연결하지 못했습니다. 네트워크 또는 접속 주소를 확인해주세요.");
  }
  if (!res.ok) throw await responseError(res, "검토 내용을 저장하지 못했습니다.");
  return res.json();
}

export async function mergePpeViolations(cameraId: string, idA: string, idB: string): Promise<PpeViolationEntry> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/ppe-violations/${cameraId}/merge`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_a: idA, id_b: idB }),
    });
  } catch {
    throw new Error("백엔드에 연결하지 못했습니다. 네트워크 또는 접속 주소를 확인해주세요.");
  }
  if (!res.ok) throw await responseError(res, "두 항목을 합치지 못했습니다.");
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
