import { frameUrl } from "../api";
import { categoryColor, STAY_CATEGORY } from "../situationUtils";
import { X } from "lucide-react";
import type { SituationCheckEntry } from "../types";

export function SituationDetailModal({
  entry,
  frameWidth,
  frameHeight,
  rangeStartAt,
  sampleCount,
  fireTriggeredAt,
  onClose,
  onAskBriefing,
}: {
  entry: SituationCheckEntry;
  frameWidth: number;
  frameHeight: number;
  rangeStartAt?: string;
  sampleCount?: number;
  fireTriggeredAt?: string | null;
  onClose: () => void;
  onAskBriefing?: () => void;
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
  const elapsedOf = (at: string) =>
    fireTriggeredAt ? Math.max(0, Math.round((new Date(at).getTime() - new Date(fireTriggeredAt).getTime()) / 1000)) : null;
  const startElapsed = elapsedOf(rangeStartAt ?? entry.at);
  const endElapsed = elapsedOf(entry.at);
  const rangeLabel =
    startElapsed == null || endElapsed == null
      ? new Date(entry.at).toLocaleTimeString("ko-KR")
      : startElapsed === endElapsed
        ? `화재 발생 후 ${endElapsed}초`
        : `화재 발생 후 ${startElapsed}초~${endElapsed}초`;
  const fallenCount = entry.zones.reduce((sum, zone) => sum + Object.entries(zone.breakdown).reduce((zoneSum, [category, count]) => zoneSum + (category.includes("쓰러") ? count : 0), 0), 0);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal briefing-card briefing-card--detail briefing-card--situation" onClick={(e) => e.stopPropagation()}>
        <header className="modal-detail-header">
          <div><h2>2차 확인 상세</h2><span>DETAIL STATE</span></div>
          <button type="button" onClick={onClose} aria-label="2차 확인 상세 닫기"><X size={16} /></button>
        </header>
        <div className="modal-detail-body">
          <div className="modal-detail-media">
            {entry.frame_path ? <div className="briefing-card__image-frame">
              <img className="briefing-card__image" src={frameUrl(entry.frame_path)} alt="2차 확인 프레임" />
              <svg className="briefing-card__image-overlay" viewBox={`0 0 ${frameWidth} ${frameHeight}`} preserveAspectRatio="none">
                {boxes.map((b, i) => {
                  const [x1, y1, x2, y2] = b.bbox_xyxy;
                  const color = categoryColor(b.category);
                  return <g key={i}><rect x={x1} y={y1} width={Math.max(0, x2 - x1)} height={Math.max(0, y2 - y1)} fill="none" stroke={color} strokeWidth={Math.max(2, frameWidth / 250)} />{b.category !== STAY_CATEGORY && <text x={x1} y={Math.max(0, y1 - 6)} fill={color} fontSize={frameWidth / 70} fontWeight={700} fontFamily="Pretendard, sans-serif">{b.category}</text>}</g>;
                })}
              </svg>
            </div> : <span className="modal-detail-placeholder">CCTV 참고 프레임</span>}
          </div>
          <div className="modal-detail-panel">
            <div className="briefing-card__disclaimer">추정 정보 · 확정 아님</div>
            <div className="briefing-card__id">{rangeLabel}</div>
            <div className="modal-detail-facts">
              {entry.zones.map((zone) => <div key={zone.zone_id}><span>{zone.zone_id}</span><strong>{zone.total}명</strong></div>)}
              <div><span>쓰러진 사람</span><strong>{fallenCount}명</strong></div>
              <div><span>원본 확인</span><strong>{sampleCount ?? 1}회 동일 집계</strong></div>
            </div>
            <p className="modal-detail-summary">{breakdownText}</p>
          </div>
        </div>
        <footer className="modal-detail-actions">
          <button type="button" className="modal__close" onClick={onClose}>닫기</button>
          {onAskBriefing && <button type="button" className="modal-detail-primary modal-detail-primary--danger" onClick={onAskBriefing}>구조 브리핑 질문</button>}
        </footer>
      </div>
    </div>
  );
}
