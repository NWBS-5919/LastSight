import type { WorkerStatus } from "../types";

const EVENT_LABEL: Record<string, string> = {
  inside_observed: "관측중",
  prolonged_presence: "장기체류경고",
  tracking_lost: "관측안됨",
  camera_failure: "카메라확인불가",
};

interface Props {
  worker: WorkerStatus;
  onClick?: () => void;
}

export function WorkerCard({ worker, onClick }: Props) {
  return (
    <button className={`worker-card worker-card--${worker.event}`} onClick={onClick}>
      <div className="worker-card__header">
        <span className="worker-card__id">{worker.track_id}</span>
        <span className={`badge badge--${worker.event}`}>{EVENT_LABEL[worker.event] ?? worker.event}</span>
      </div>
      <div className="worker-card__body">
        <div>마지막 위치: {worker.last_zone ?? "정보 없음"}</div>
        <div>마지막 확인: {worker.last_seen_at ? new Date(worker.last_seen_at).toLocaleTimeString("ko-KR") : "정보 없음"}</div>
        {worker.confidence != null && <div>탐지 신뢰도: {(worker.confidence * 100).toFixed(0)}%</div>}
      </div>
      {(worker.event === "prolonged_presence" || worker.event === "tracking_lost") && (
        <div className="worker-card__disclaimer">추정 정보 — 확정 아님</div>
      )}
    </button>
  );
}
