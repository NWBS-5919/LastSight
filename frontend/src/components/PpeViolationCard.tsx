import type { PpeViolationEntry } from "../types";
import { frameUrl } from "../api";

interface Props {
  entry: PpeViolationEntry;
  frameWidth: number;
  frameHeight: number;
  onClick?: () => void;
}

const STATE_LABEL: Record<string, string> = { worn: "착용", not_worn: "미착용", unknown: "미상" };

function effectiveHelmet(entry: PpeViolationEntry) {
  return entry.reviewed_helmet ?? entry.helmet_state;
}
function effectiveVest(entry: PpeViolationEntry) {
  return entry.reviewed_vest ?? entry.vest_state;
}

export function PpeViolationCard({ entry, frameWidth, frameHeight, onClick }: Props) {
  const helmet = effectiveHelmet(entry);
  const vest = effectiveVest(entry);
  const stillViolation = helmet === "not_worn" || vest === "not_worn";
  const reviewed = entry.reviewed_at != null;

  return (
    <button className={`worker-card ${stillViolation ? "worker-card--prolonged_presence" : ""}`} onClick={onClick}>
      <div className="worker-card__media">
        {entry.frame_path ? <img src={frameUrl(entry.frame_path)} alt={`${entry.zone ?? "구역 미상"} PPE 감지 프레임`} /> : <span>CCTV 참고 프레임</span>}
        {entry.bbox_xyxy && (
          <svg className="worker-card__media-overlay" viewBox={`0 0 ${frameWidth} ${frameHeight}`} preserveAspectRatio="xMidYMid meet" aria-hidden="true">
            <rect
              x={entry.bbox_xyxy[0]}
              y={entry.bbox_xyxy[1]}
              width={Math.max(0, entry.bbox_xyxy[2] - entry.bbox_xyxy[0])}
              height={Math.max(0, entry.bbox_xyxy[3] - entry.bbox_xyxy[1])}
              fill="none"
              stroke={stillViolation ? "#f04d45" : "#39b980"}
              strokeWidth={Math.max(2, frameWidth / 250)}
            />
          </svg>
        )}
      </div>
      <div className="worker-card__content">
        <div className="worker-card__header">
          <span className="worker-card__id">{entry.zone ?? "구역 미상"} · {new Date(entry.at).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" })}</span>
          <span className={`badge ${stillViolation ? "badge--prolonged_presence" : ""}`}>
            {reviewed ? "관리자 확인" : stillViolation ? "검토 필요" : "정정됨"}
          </span>
        </div>
        <div className="worker-card__body">
          <div>{helmet === "not_worn" && vest === "not_worn" ? "안전모·조끼 미착용" : helmet === "not_worn" ? "안전모 미착용" : vest === "not_worn" ? "조끼 미착용" : `안전모 ${STATE_LABEL[helmet ?? "unknown"]} · 조끼 ${STATE_LABEL[vest ?? "unknown"]}`}</div>
        </div>
        <div className="worker-card__disclaimer">AI 신뢰도 {entry.confidence != null ? `${Math.round(entry.confidence * 100)}%` : "확인 중"} · 클릭하여 판정 검토</div>
      </div>
    </button>
  );
}
