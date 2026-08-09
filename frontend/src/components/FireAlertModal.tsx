import type { FireAlert } from "../types";
import { Flame, X } from "lucide-react";

interface Props {
  alert: FireAlert;
  onClose: () => void;
  onOpenEmergency?: () => void;
}

export function FireAlertModal({ alert, onClose, onOpenEmergency }: Props) {
  const triggeredAt = new Date(alert.triggered_at);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal briefing-card briefing-card--detail briefing-card--fire" onClick={(e) => e.stopPropagation()}>
        <header className="modal-detail-header">
          <div><h2>화재 경보 상세</h2><span>DETAIL STATE</span></div>
          <button type="button" onClick={onClose} aria-label="화재 경보 상세 닫기"><X size={16} /></button>
        </header>
        <div className="fire-detail-content">
          <div className="fire-detail-alert">
            <span><Flame size={21} fill="currentColor" /></span>
            <div><small>FIRE ALERT · {alert.source === "auto_detection" ? "자동 탐지" : "수동 경보"}</small><strong>{alert.zone_id ?? "구역 미확인"} 화재 경보</strong><p>{triggeredAt.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", second: "2-digit" })} 발생 · 신뢰도 {alert.confidence != null ? `${(alert.confidence * 100).toFixed(0)}%` : "확인 중"}</p></div>
          </div>
          <div className="fire-detail-metrics">
            <div><span>관측 인원</span><strong>4명</strong><small>현재 프레임</small></div>
            <div><span>시야 확보</span><strong>제한</strong><small>연기 감지</small></div>
            <div><span>최근 확인</span><strong>14초</strong><small>{alert.zone_id ?? "A구역"} 2명</small></div>
            <div><span>경보 상태</span><strong>대응 중</strong><small>전 탭 동기화</small></div>
          </div>
        </div>
        <footer className="modal-detail-actions">
          <button type="button" className="modal__close" onClick={onClose}>닫기</button>
          {onOpenEmergency && <button type="button" className="modal-detail-primary modal-detail-primary--danger" onClick={onOpenEmergency}>비상 대응 화면 열기</button>}
        </footer>
      </div>
    </div>
  );
}
