import { frameUrl } from "../api";
import { categoryColor, STAY_CATEGORY } from "../situationUtils";
import type { SituationCheckEntry } from "../types";

export function SituationDetailModal({
  entry,
  frameWidth,
  frameHeight,
  onClose,
}: {
  entry: SituationCheckEntry;
  frameWidth: number;
  frameHeight: number;
  onClose: () => void;
}) {
  const boxes = entry.zones.flatMap((z) => z.boxes);
  const breakdownText = entry.zones
    .map((z) => {
      const parts = Object.entries(z.breakdown)
        .filter(([, count]) => count > 0)
        .map(([category, count]) => `${category} ${count}명`)
        .join(", ");
      return `${z.zone_id} 총 ${z.total}명(${parts})`;
    })
    .join(" / ");

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal briefing-card" onClick={(e) => e.stopPropagation()}>
        <div className="briefing-card__header">2차 확인 상세</div>
        <div className="briefing-card__disclaimer">추정 정보 — 확정 아님</div>
        <div className="briefing-card__id">{new Date(entry.at).toLocaleTimeString("ko-KR")}</div>
        {entry.frame_path && (
          <div className="briefing-card__image-frame">
            <img className="briefing-card__image" src={frameUrl(entry.frame_path)} alt="2차 확인 프레임" />
            <svg className="briefing-card__image-overlay" viewBox={`0 0 ${frameWidth} ${frameHeight}`} preserveAspectRatio="none">
              {boxes.map((b, i) => {
                const [x1, y1, x2, y2] = b.bbox_xyxy;
                const color = categoryColor(b.category);
                return (
                  <g key={i}>
                    <rect
                      x={x1}
                      y={y1}
                      width={Math.max(0, x2 - x1)}
                      height={Math.max(0, y2 - y1)}
                      fill="none"
                      stroke={color}
                      strokeWidth={Math.max(2, frameWidth / 250)}
                    />
                    {b.category !== STAY_CATEGORY && (
                      <text x={x1} y={Math.max(0, y1 - 6)} fill={color} fontSize={frameWidth / 70} fontWeight={700} fontFamily="ui-monospace, monospace">
                        {b.category}
                      </text>
                    )}
                  </g>
                );
              })}
            </svg>
          </div>
        )}
        <p>{breakdownText}</p>
        <button className="modal__close" onClick={onClose}>
          닫기
        </button>
      </div>
    </div>
  );
}
