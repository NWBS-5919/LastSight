// backend/app/models/schemas.py 와 동기화 유지 — 이벤트/상태 값 이름을 임의로 바꾸지 말 것.

export type WorkerEvent = "inside_observed" | "prolonged_presence" | "tracking_lost" | "camera_failure";

export interface WorkerStatus {
  track_id: string;
  event: WorkerEvent;
  last_zone: string | null;
  last_seen_at: string | null;
  last_frame_path: string | null;
  reference_frame_path: string | null;
  helmet_color: string | null;
  vest_color: string | null;
  top_color: string | null;
  visibility: string | null;
  confidence: number | null;
}

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

export interface ScenarioSnapshot {
  running: boolean;
  frame_idx: number;
  frame_image_url: string | null;
  frame_width: number;
  frame_height: number;
  fire_alert: FireAlert | null;
  workers: WorkerStatus[];
  event_feed: EventFeedEntry[];
  ppe_violations_today: number;
  zone_person_counts: Record<string, number>;
  current_detections: Detection[];
}

export interface BriefingCard {
  track_id: string;
  status: WorkerEvent;
  confidence: number | null;
  visibility: string | null;
  disclaimer: string;
  summary: string;
  last_frame_path: string | null;
  reference_frame_path: string | null;
}
