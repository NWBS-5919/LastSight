import type { PersonComplianceBox } from "../types";

interface Detection {
  object_class: string;
  confidence: number;
  bbox_xyxy: [number, number, number, number];
}

// fire/smoke는 원본 탐지 색을 그대로 쓴다. person 원본 박스는 평상시엔 안 그린다 —
// 대신 complianceBoxes로 사람마다 "착용 상태"만 깔끔하게 표시한다. 비상시엔 개인별 상태
// 구분 없이 감지된 사람 전원을 초록 박스로만 표시한다(2026-08-03 재설계 — 추적 기반 개인별
// 상태 표시를 없앴다. development_log.md 참고).
const FIRE_COLOR: Record<string, string> = { fire: "var(--danger)", smoke: "var(--smoke)" };

const NORMAL_COLOR = "var(--overlay-neutral)"; // 정상 착용(또는 아직 판단 보류)
const VIOLATION_COLOR = "var(--danger)"; // 미착용 확정
const OBSERVED_COLOR = "var(--ok)"; // 비상시 감지된 사람

interface Props {
  detections: Detection[];
  frameWidth: number;
  frameHeight: number;
  complianceBoxes?: PersonComplianceBox[]; // 평상시: 사람별 헬멧/조끼 착용 판정
  emergencyMode?: boolean; // 비상시: 감지된 사람 전원 초록 박스
}

function Box({
  bbox,
  color,
  label,
  dashed,
  frameWidth,
}: {
  bbox: [number, number, number, number];
  color: string;
  label: string | null;
  dashed: boolean;
  frameWidth: number;
}) {
  const [x1, y1, x2, y2] = bbox;
  const width = Math.max(0, x2 - x1);
  const height = Math.max(0, y2 - y1);
  return (
    <g>
      <rect
        x={x1}
        y={y1}
        width={width}
        height={height}
        fill="none"
        stroke={color}
        strokeWidth={Math.max(2, frameWidth / 350)}
        strokeDasharray={dashed ? "10 6" : undefined}
      />
      {label && (
        <text
          x={x1}
          y={Math.max(0, y2 + frameWidth / 45)}
          fill={color}
          fontSize={frameWidth / 70}
          fontWeight={700}
          fontFamily="Pretendard Variable, Pretendard, sans-serif"
        >
          {label}
        </text>
      )}
    </g>
  );
}

export function DetectionOverlay({ detections, frameWidth, frameHeight, complianceBoxes = [], emergencyMode = false }: Props) {
  return (
    <svg className="detection-overlay" viewBox={`0 0 ${frameWidth} ${frameHeight}`} preserveAspectRatio="none">
      {detections
        .filter((d) => d.object_class === "fire" || d.object_class === "smoke")
        .map((d, i) => {
          const [x1, y1, x2, y2] = d.bbox_xyxy;
          const color = FIRE_COLOR[d.object_class] ?? "var(--overlay-neutral)";
          return (
            <g key={`fire-${i}`}>
              <rect
                x={x1}
                y={y1}
                width={Math.max(0, x2 - x1)}
                height={Math.max(0, y2 - y1)}
                fill="none"
                stroke={color}
                strokeWidth={Math.max(2, frameWidth / 400)}
              />
              <text x={x1} y={Math.max(0, y1 - 6)} fill={color} fontSize={frameWidth / 80} fontWeight={700} fontFamily="Pretendard Variable, Pretendard, sans-serif">
                {d.object_class} {(d.confidence * 100).toFixed(0)}%
              </text>
            </g>
          );
        })}

      {/* 평상시: 미착용 확정이면 빨간 점선 + 라벨, 그 외(착용/판단 보류)는 흰색 실선만 */}
      {!emergencyMode &&
        complianceBoxes.map((p, i) => {
          const missing = [p.helmet === "not_worn" ? "헬멧" : null, p.vest === "not_worn" ? "조끼" : null].filter(
            (v): v is string => v !== null,
          );
          const violated = missing.length > 0;
          return (
            <Box
              key={`compliance-${i}`}
              bbox={p.bbox_xyxy}
              color={violated ? VIOLATION_COLOR : NORMAL_COLOR}
              label={violated ? `${missing.join("·")} 미착용` : null}
              dashed={violated}
              frameWidth={frameWidth}
            />
          );
        })}

      {/* 비상시: 개인별 상태 구분 없이, 감지된 사람 전원을 초록 박스로만 표시 */}
      {emergencyMode &&
        detections
          .filter((d) => d.object_class === "person")
          .map((d, i) => (
            <Box key={`person-${i}`} bbox={d.bbox_xyxy} color={OBSERVED_COLOR} label={null} dashed={false} frameWidth={frameWidth} />
          ))}
    </svg>
  );
}
