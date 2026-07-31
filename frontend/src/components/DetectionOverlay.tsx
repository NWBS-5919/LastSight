interface Detection {
  object_class: string;
  confidence: number;
  bbox_xyxy: [number, number, number, number];
}

const COLOR: Record<string, string> = {
  person: "#3b82f6",
  helmet: "#22c55e",
  vest: "#eab308",
  no_helmet: "#f97316",
  no_vest: "#f97316",
  head: "#06b6d4",
  fire: "#ef4444",
  smoke: "#a855f7",
};

interface Props {
  detections: Detection[];
  frameWidth: number;
  frameHeight: number;
}

export function DetectionOverlay({ detections, frameWidth, frameHeight }: Props) {
  return (
    <svg className="detection-overlay" viewBox={`0 0 ${frameWidth} ${frameHeight}`} preserveAspectRatio="none">
      {detections.map((d, i) => {
        const [x1, y1, x2, y2] = d.bbox_xyxy;
        const color = COLOR[d.object_class] ?? "#e5e7eb";
        return (
          <g key={i}>
            <rect
              x={x1}
              y={y1}
              width={Math.max(0, x2 - x1)}
              height={Math.max(0, y2 - y1)}
              fill="none"
              stroke={color}
              strokeWidth={Math.max(2, frameWidth / 400)}
            />
            <text x={x1} y={Math.max(0, y1 - 6)} fill={color} fontSize={frameWidth / 80} fontWeight={700}>
              {d.object_class} {(d.confidence * 100).toFixed(0)}%
            </text>
          </g>
        );
      })}
    </svg>
  );
}
