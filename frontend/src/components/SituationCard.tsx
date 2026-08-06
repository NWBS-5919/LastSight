import { combinedBreakdown, STAY_CATEGORY, type SituationInterval } from "../situationUtils";

interface Props {
  interval: SituationInterval;
  fireTriggeredAt: string | null;
  onClick?: () => void;
}

export function SituationCard({ interval, fireTriggeredAt, onClick }: Props) {
  const { start, end, sampleCount } = interval;
  const startElapsed = fireTriggeredAt
    ? Math.max(0, Math.round((new Date(start.at).getTime() - new Date(fireTriggeredAt).getTime()) / 1000))
    : null;
  const endElapsed = fireTriggeredAt
    ? Math.max(0, Math.round((new Date(end.at).getTime() - new Date(fireTriggeredAt).getTime()) / 1000))
    : null;
  const elapsedLabel =
    startElapsed == null || endElapsed == null
      ? "2차 확인"
      : startElapsed === endElapsed
        ? `화재 발생 후 ${startElapsed}초`
        : `화재 발생 후 ${startElapsed}초~${endElapsed}초`;
  const breakdown = combinedBreakdown(end);
  const total = Object.values(breakdown).reduce((a, b) => a + b, 0);
  const concerning = Object.entries(breakdown).some(([category, count]) => category !== STAY_CATEGORY && count > 0);
  const summary =
    Object.entries(breakdown)
      .filter(([, count]) => count > 0)
      .map(([category, count]) => `${category} ${count}명`)
      .join(", ") || "감지된 사람 없음";

  return (
    <button className={`worker-card ${concerning ? "worker-card--prolonged_presence" : ""}`} onClick={onClick}>
      <div className="worker-card__header">
        <span className="worker-card__id">{elapsedLabel}</span>
        <span className={`badge ${concerning ? "badge--prolonged_presence" : ""}`}>{concerning ? "확인 필요" : "이상 없음"}</span>
      </div>
      <div className="worker-card__body">
        <div>총 {total}명 감지</div>
        <div>{summary}</div>
      </div>
      <div className="worker-card__disclaimer">{sampleCount}회 동일 집계 · 추정 정보 — 확정 아님</div>
    </button>
  );
}
