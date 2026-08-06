import { useState } from "react";
import { frameUrl, reviewPpeViolation } from "../api";
import type { ComplianceState, PpeViolationEntry } from "../types";

const BOX_COLOR: Record<string, string> = { worn: "var(--ok)", not_worn: "var(--danger)", unknown: "var(--overlay-neutral)" };

function effectiveHelmet(entry: PpeViolationEntry): ComplianceState {
  return entry.reviewed_helmet ?? entry.helmet_state ?? "unknown";
}
function effectiveVest(entry: PpeViolationEntry): ComplianceState {
  return entry.reviewed_vest ?? entry.vest_state ?? "unknown";
}

export function PpeViolationEditModal({
  entry,
  cameraId,
  frameWidth,
  frameHeight,
  onClose,
  onSaved,
}: {
  entry: PpeViolationEntry;
  cameraId: string;
  frameWidth: number;
  frameHeight: number;
  onClose: () => void;
  onSaved: (updated: PpeViolationEntry) => void;
}) {
  const [helmet, setHelmet] = useState<ComplianceState>(effectiveHelmet(entry));
  const [vest, setVest] = useState<ComplianceState>(effectiveVest(entry));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const boxColor = helmet === "not_worn" || vest === "not_worn" ? BOX_COLOR.not_worn : BOX_COLOR.worn;

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const updated = await reviewPpeViolation(cameraId, entry.id, { helmet, vest });
      onSaved(updated);
      onClose();
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "저장에 실패했습니다. 다시 시도해주세요.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal briefing-card" onClick={(e) => e.stopPropagation()}>
        <div className="briefing-card__header">PPE 판정 검토</div>
        <div className="briefing-card__disclaimer">AI 판정 — 관리자가 최종 확정</div>
        <div className="briefing-card__id">
          {entry.zone ?? "구역 미상"} · {new Date(entry.at).toLocaleTimeString("ko-KR")}
        </div>
        {entry.frame_path && (
          <div className="briefing-card__image-frame">
            <img className="briefing-card__image" src={frameUrl(entry.frame_path)} alt="PPE 위반 감지 프레임" />
            {entry.bbox_xyxy && (
              <svg className="briefing-card__image-overlay" viewBox={`0 0 ${frameWidth} ${frameHeight}`} preserveAspectRatio="none">
                <rect
                  x={entry.bbox_xyxy[0]}
                  y={entry.bbox_xyxy[1]}
                  width={Math.max(0, entry.bbox_xyxy[2] - entry.bbox_xyxy[0])}
                  height={Math.max(0, entry.bbox_xyxy[3] - entry.bbox_xyxy[1])}
                  fill="none"
                  stroke={boxColor}
                  strokeWidth={Math.max(2, frameWidth / 250)}
                />
              </svg>
            )}
          </div>
        )}

        <div className="ppe-review-field">
          <span className="ppe-review-field__label">안전모</span>
          <div className="ppe-review-field__options">
            <button className={`ppe-review-option ${helmet === "worn" ? "ppe-review-option--active-ok" : ""}`} onClick={() => setHelmet("worn")}>
              착용
            </button>
            <button
              className={`ppe-review-option ${helmet === "not_worn" ? "ppe-review-option--active-danger" : ""}`}
              onClick={() => setHelmet("not_worn")}
            >
              미착용
            </button>
          </div>
        </div>

        <div className="ppe-review-field">
          <span className="ppe-review-field__label">안전조끼</span>
          <div className="ppe-review-field__options">
            <button className={`ppe-review-option ${vest === "worn" ? "ppe-review-option--active-ok" : ""}`} onClick={() => setVest("worn")}>
              착용
            </button>
            <button
              className={`ppe-review-option ${vest === "not_worn" ? "ppe-review-option--active-danger" : ""}`}
              onClick={() => setVest("not_worn")}
            >
              미착용
            </button>
          </div>
        </div>

        {entry.reviewed_at && (
          <p className="briefing-card__meta">
            <span>마지막 검토: {new Date(entry.reviewed_at).toLocaleTimeString("ko-KR")}</span>
          </p>
        )}
        {error && <p style={{ color: "var(--danger)" }}>{error}</p>}

        <div className="app__controls" style={{ marginTop: 12 }}>
          <button onClick={handleSave} disabled={saving}>
            {saving ? "저장 중..." : "검토 확정 저장"}
          </button>
          <button className="app__controls-reset" onClick={onClose}>
            닫기
          </button>
        </div>
      </div>
    </div>
  );
}
