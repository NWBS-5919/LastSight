import type { PpeViolationEntry } from "../types";

interface Props {
  entry: PpeViolationEntry;
  onClick?: () => void;
}

const STATE_LABEL: Record<string, string> = { worn: "착용", not_worn: "미착용", unknown: "미상" };

function effectiveHelmet(entry: PpeViolationEntry) {
  return entry.reviewed_helmet ?? entry.helmet_state;
}
function effectiveVest(entry: PpeViolationEntry) {
  return entry.reviewed_vest ?? entry.vest_state;
}

export function PpeViolationCard({ entry, onClick }: Props) {
  const helmet = effectiveHelmet(entry);
  const vest = effectiveVest(entry);
  const stillViolation = helmet === "not_worn" || vest === "not_worn";
  const reviewed = entry.reviewed_at != null;

  return (
    <button className={`worker-card ${stillViolation ? "worker-card--prolonged_presence" : ""}`} onClick={onClick}>
      <div className="worker-card__header">
        <span className="worker-card__id">{new Date(entry.at).toLocaleTimeString("ko-KR")}</span>
        <span className={`badge ${stillViolation ? "badge--prolonged_presence" : ""}`}>
          {reviewed ? "검토 완료" : stillViolation ? "미착용" : "정정됨"}
        </span>
      </div>
      <div className="worker-card__body">
        <div>구역: {entry.zone ?? "정보 없음"}</div>
        <div>안전모: {STATE_LABEL[helmet ?? "unknown"]}</div>
        <div>안전조끼: {STATE_LABEL[vest ?? "unknown"]}</div>
      </div>
      <div className="worker-card__disclaimer">{reviewed ? "관리자 검토 완료" : "추정 정보 — 확정 아님, 클릭해서 검토"}</div>
    </button>
  );
}
