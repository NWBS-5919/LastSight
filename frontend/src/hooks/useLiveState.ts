import { useEffect, useRef, useState } from "react";
import { connectLiveSocket, fetchState } from "../api";
import type { ScenarioSnapshot } from "../types";

const EMPTY_STATE: ScenarioSnapshot = {
  running: false,
  frame_idx: -1,
  frame_image_url: null,
  frame_width: 1920,
  frame_height: 1080,
  fire_alert: null,
  workers: [],
  event_feed: [],
  ppe_violations_today: 0,
  zone_person_counts: {},
  current_detections: [],
};

export function useLiveState(): ScenarioSnapshot {
  const [snapshot, setSnapshot] = useState<ScenarioSnapshot>(EMPTY_STATE);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    fetchState()
      .then(setSnapshot)
      .catch(() => {
        /* 백엔드가 아직 안 떠 있을 수 있음 — 웹소켓 연결 시 재시도됨 */
      });

    const ws = connectLiveSocket(setSnapshot);
    wsRef.current = ws;
    return () => ws.close();
  }, []);

  return snapshot;
}
