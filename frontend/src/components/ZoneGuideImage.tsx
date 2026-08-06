import { frameUrl } from "../api";
import type { ZoneDef } from "../types";

const FIRST_FRAME_PATH = "/demo-frames/frames/0000.jpg";
const ZONE_COLORS = ["#35d477", "#5b9cff", "#f4a63a", "#b78cff", "#ff7096", "#48c7c7"];

interface Props {
  zones: ZoneDef[];
  personCounts: Record<string, number>;
  frameWidth: number;
  frameHeight: number;
}

function polygonCenter(polygon: [number, number][]): [number, number] {
  if (polygon.length === 0) return [0, 0];
  const [x, y] = polygon.reduce(([sumX, sumY], [pointX, pointY]) => [sumX + pointX, sumY + pointY], [0, 0]);
  return [x / polygon.length, y / polygon.length];
}

export function ZoneGuideImage({ zones, personCounts, frameWidth, frameHeight }: Props) {
  const width = frameWidth > 0 ? frameWidth : 1920;
  const height = frameHeight > 0 ? frameHeight : 1080;

  return (
    <figure className="zone-guide">
      <div className="zone-guide__canvas">
        <img src={frameUrl(FIRST_FRAME_PATH)} alt="카메라 기준 화면" />
        <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-label="카메라 화면의 구역 경계">
          {zones.map((zone, index) => {
            const color = ZONE_COLORS[index % ZONE_COLORS.length];
            const [labelX, labelY] = polygonCenter(zone.polygon);
            return (
              <g key={zone.zone_id}>
                <polygon
                  points={zone.polygon.map(([x, y]) => `${x},${y}`).join(" ")}
                  fill={color}
                  fillOpacity="0.2"
                  stroke={color}
                  strokeWidth="5"
                  vectorEffect="non-scaling-stroke"
                />
                <text x={labelX} y={labelY} fill={color} textAnchor="middle" dominantBaseline="middle">
                  {zone.zone_id}
                </text>
              </g>
            );
          })}
        </svg>
        {zones.length === 0 && <span className="zone-guide__empty">등록된 구역 정보가 없습니다.</span>}
      </div>
      <figcaption>
        {zones.length > 0
          ? `색상 경계는 현재 인원 집계 범위입니다 · 총 ${Object.values(personCounts).reduce((sum, count) => sum + count, 0)}명`
          : "백엔드에 저장된 구역이 표시됩니다."}
      </figcaption>
    </figure>
  );
}
