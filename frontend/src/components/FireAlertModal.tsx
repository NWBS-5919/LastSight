import type { FireAlert } from "../types";

interface Props {
  alert: FireAlert;
  onClose: () => void;
}

export function FireAlertModal({ alert, onClose }: Props) {
  const triggeredAt = new Date(alert.triggered_at);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal briefing-card" onClick={(e) => e.stopPropagation()}>
        <div className="briefing-card__header">화재 발생 상세</div>
        <div className="briefing-card__id">{triggeredAt.toLocaleString("ko-KR")}</div>
        <div className="briefing-card__meta">
          <span>트리거: {alert.source === "auto_detection" ? "자동탐지" : "수동"}</span>
          {alert.confidence != null && <span>신뢰도 {(alert.confidence * 100).toFixed(0)}%</span>}
          <span>구역: {alert.zone_id ?? "정보 없음"}</span>
        </div>
        <p className="situation-summary__headline">
          {alert.source === "auto_detection"
            ? "화재/연기 탐지 모델이 연속 감지를 확정해 자동으로 경보가 발생했습니다."
            : "관리자가 수동으로 화재경보를 발생시켰습니다."}
        </p>
        <button className="modal__close" onClick={onClose}>
          닫기
        </button>
      </div>
    </div>
  );
}
