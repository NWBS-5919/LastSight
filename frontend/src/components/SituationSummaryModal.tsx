import type { SituationSummary } from "../types";

interface Props {
  summary: SituationSummary;
  onClose: () => void;
}

export function SituationSummaryModal({ summary, onClose }: Props) {
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal briefing-card" onClick={(e) => e.stopPropagation()}>
        <div className="briefing-card__header">요약 브리핑</div>
        <div className="briefing-card__disclaimer">{summary.disclaimer}</div>
        <div className="briefing-card__id">{new Date(summary.generated_at).toLocaleTimeString("ko-KR")} 기준</div>
        <p className="situation-summary__headline">{summary.headline}</p>
        <ul className="situation-summary__points">
          {summary.points.map((point, i) => (
            <li key={i}>{point}</li>
          ))}
        </ul>
        <button className="modal__close" onClick={onClose}>
          닫기
        </button>
      </div>
    </div>
  );
}
