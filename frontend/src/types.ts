// backend/app/models/schemas.py 와 동기화 유지 — 이벤트/상태 값 이름을 임의로 바꾸지 말 것.

export interface FireAlert {
  camera_id: string;
  zone_id: string | null;
  triggered_at: string;
  source: "auto_detection" | "manual";
  confidence: number | null;
}

export interface EventFeedEntry {
  at: string;
  text: string;
}

export interface Detection {
  object_class: string;
  confidence: number;
  bbox_xyxy: [number, number, number, number];
}

export type ComplianceState = "worn" | "not_worn" | "unknown";

export interface PersonComplianceBox {
  bbox_xyxy: [number, number, number, number];
  zone: string | null;
  helmet: ComplianceState;
  vest: ComplianceState;
  confidence: number | null;
}

// 2026-08-03: 화재 이후 추적 기반 개인별 카드를 없애고, 화재 발생 후 1초마다 그 순간
// 프레임을 ZERO로 2차 확인한 결과 하나하나를 카드로 쌓는 방식으로 바꿨다. category는
// "체류중"(우려 없음)/"쓰러진 사람"/"연기에 둘러싸인 사람" 등 situation_probe.py의 카테고리.
export interface SituationBox {
  category: string;
  bbox_xyxy: [number, number, number, number];
}

export interface SituationZoneEntry {
  zone_id: string;
  total: number;
  breakdown: Record<string, number>;
  boxes: SituationBox[];
}

export interface SituationCheckEntry {
  camera_id: string;
  at: string;
  zones: SituationZoneEntry[];
  frame_path: string | null;
}

// 2026-08-03: 관리자가 카드를 열어 AI 판정(helmet_state/vest_state)을 직접 검토·수정할 수
// 있다 — reviewed_*는 사람이 최종 확정한 값(None이면 미검토, AI 판정 그대로). AI 원판정은
// 절대 안 지운다(둘 다 착용으로 정정해도 "AI가 원래 뭐라고 봤는지"는 감사 기록으로 남음).
export interface PpeViolationEntry {
  id: string;
  violations: string[];
  zone: string | null;
  at: string;
  frame_path: string | null;
  bbox_xyxy: [number, number, number, number] | null;
  confidence: number | null;
  helmet_state: ComplianceState | null;
  vest_state: ComplianceState | null;
  reviewed_at: string | null;
  reviewed_helmet: ComplianceState | null;
  reviewed_vest: ComplianceState | null;
}

export interface ZoneDef {
  zone_id: string;
  polygon: [number, number][];
}

export interface ZoneMapConfig {
  camera_id: string;
  image_width: number | null;
  image_height: number | null;
  zones: ZoneDef[];
}

// 2026-08-05: 한 번 누르면 끝나는 "요약 브리핑" 버튼을 챗봇으로 대체했다 — 첫 메시지가
// 예전 요약 역할을 그대로 하고, 후속 질문("74초쯤엔 뭐였어?" 등)까지 받을 수 있다.
export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  frame_path?: string | null; // assistant 메시지가 참고한 프레임(있으면 썸네일로 보여줌)
}

export interface ChatReply {
  reply: string;
  frame_path: string | null;
  generated_at: string;
  disclaimer: string;
}

export interface ScenarioSnapshot {
  running: boolean;
  frame_idx: number;
  frame_t: number | null;
  frame_image_url: string | null;
  frame_width: number;
  frame_height: number;
  fire_alert: FireAlert | null;
  event_feed: EventFeedEntry[];
  ppe_violations_today: number;
  zone_person_counts: Record<string, number>;
  current_detections: Detection[];
  current_person_compliance: PersonComplianceBox[];
  situation_checks: SituationCheckEntry[];
  scenario_started_at: string | null;
  ppe_violation_events: PpeViolationEntry[];
}
