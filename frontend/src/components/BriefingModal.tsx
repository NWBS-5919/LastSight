import { useEffect, useState } from "react";
import { fetchBriefing, frameUrl } from "../api";
import type { BriefingCard } from "../types";

export function BriefingModal({ trackId, onClose }: { trackId: string; onClose: () => void }) {
  const [card, setCard] = useState<BriefingCard | null>(null);

  useEffect(() => {
    fetchBriefing(trackId).then(setCard);
  }, [trackId]);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal briefing-card" onClick={(e) => e.stopPropagation()}>
        {card ? (
          <>
            <div className="briefing-card__disclaimer">{card.disclaimer}</div>
            <h2>{card.track_id}</h2>
            {card.last_frame_path && (
              <img className="briefing-card__image" src={frameUrl(card.last_frame_path)} alt={`${card.track_id} 마지막 관측 프레임`} />
            )}
            <p>{card.summary}</p>
            <div className="briefing-card__meta">
              {card.confidence != null && <span>탐지 신뢰도 {(card.confidence * 100).toFixed(0)}%</span>}
              {card.visibility && <span>시야: {card.visibility}</span>}
            </div>
          </>
        ) : (
          <p>불러오는 중...</p>
        )}
        <button className="modal__close" onClick={onClose}>
          닫기
        </button>
      </div>
    </div>
  );
}
