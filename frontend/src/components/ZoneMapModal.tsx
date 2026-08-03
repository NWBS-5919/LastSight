import { useEffect, useRef, useState } from "react";
import { fetchZoneMap, frameUrl, saveZoneMap } from "../api";
import type { ZoneDef, ZoneMapConfig } from "../types";

const FIRST_FRAME_PATH = "/demo-frames/frames/0000.jpg";

// 처음 대시보드를 보는 사람은 "A구역"·"B구역"이라는 이름만으로는 실제 화면의 어디를
// 가리키는지 알 수 없다 — 그래서 첫 프레임 위에 구역 폴리곤을 색으로 칠해 보여준다.
// 편집 모드에서는 같은 화면에서 폴리곤을 직접 그리고 이름을 붙여 구역을 새로 정의할 수
// 있다 — 백엔드(app/rules/zone.py which_zone)는 이미 임의 개수·모양의 폴리곤을 그대로
// 처리하도록 만들어져 있어(고정 좌/우 절반 분할은 데모용 초기값일 뿐), 프론트엔드
// 에디터만 있으면 된다.
const ZONE_COLORS = ["#4ade80", "#60a5fa", "#f59e0b", "#f472b6", "#a78bfa", "#f87171"];

interface Props {
  cameraId: string;
  frameWidth: number;
  frameHeight: number;
  onClose: () => void;
  onSaved?: () => void;
}

function polygonCenter(polygon: [number, number][]): [number, number] {
  const [sx, sy] = polygon.reduce(([ax, ay], [x, y]) => [ax + x, ay + y], [0, 0]);
  return [sx / polygon.length, sy / polygon.length];
}

function clientToImagePoint(svg: SVGSVGElement, clientX: number, clientY: number): [number, number] {
  const pt = svg.createSVGPoint();
  pt.x = clientX;
  pt.y = clientY;
  const ctm = svg.getScreenCTM();
  if (!ctm) return [0, 0];
  const p = pt.matrixTransform(ctm.inverse());
  return [Math.round(p.x), Math.round(p.y)];
}

export function ZoneMapModal({ cameraId, frameWidth, frameHeight, onClose, onSaved }: Props) {
  const [zoneMap, setZoneMap] = useState<ZoneMapConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<"view" | "edit">("view");
  const [saving, setSaving] = useState(false);

  const [draftZones, setDraftZones] = useState<ZoneDef[]>([]);
  const [drafting, setDrafting] = useState(false);
  const [drawingPoints, setDrawingPoints] = useState<[number, number][]>([]);
  const [namingOpen, setNamingOpen] = useState(false);
  const [nameInput, setNameInput] = useState("");
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    fetchZoneMap(cameraId)
      .then(setZoneMap)
      .catch(() => setError("구역 정보를 불러오지 못했습니다."));
  }, [cameraId]);

  const displayZones = mode === "edit" ? draftZones : (zoneMap?.zones ?? []);

  const startEdit = () => {
    // zoneMap을 아직 못 불러온 상태에서 편집을 시작하면 draftZones가 빈 배열로 초기화돼,
    // 그대로 저장하면 기존 구역이 전부 지워진다(실측) — 로딩 전에는 편집 진입 자체를 막는다.
    if (!zoneMap) return;
    setDraftZones(zoneMap.zones);
    setMode("edit");
    setError(null);
  };

  const cancelEdit = () => {
    setMode("view");
    setDrafting(false);
    setDrawingPoints([]);
    setNamingOpen(false);
    setError(null);
  };

  const startDrawing = () => {
    setDrafting(true);
    setNamingOpen(false);
    setDrawingPoints([]);
    setError(null);
  };

  const cancelDrawing = () => {
    setDrafting(false);
    setNamingOpen(false);
    setDrawingPoints([]);
  };

  const handleSvgClick = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!drafting || !svgRef.current) return;
    const point = clientToImagePoint(svgRef.current, e.clientX, e.clientY);
    setDrawingPoints((prev) => [...prev, point]);
  };

  const undoLastPoint = () => setDrawingPoints((prev) => prev.slice(0, -1));

  const finishDrawing = () => {
    if (drawingPoints.length < 3) {
      setError("점을 3개 이상 찍어야 구역을 만들 수 있습니다.");
      return;
    }
    setDrafting(false);
    setNamingOpen(true);
    setNameInput("");
    setError(null);
  };

  const confirmName = () => {
    const trimmed = nameInput.trim();
    if (!trimmed) {
      setError("구역 이름을 입력해주세요.");
      return;
    }
    if (draftZones.some((z) => z.zone_id === trimmed)) {
      setError("이미 같은 이름의 구역이 있습니다. 다른 이름을 입력해주세요.");
      return;
    }
    setDraftZones((prev) => [...prev, { zone_id: trimmed, polygon: drawingPoints }]);
    setNamingOpen(false);
    setDrawingPoints([]);
    setNameInput("");
    setError(null);
  };

  const cancelNaming = () => {
    setNamingOpen(false);
    setDrawingPoints([]);
  };

  const deleteZone = (zoneId: string) => {
    setDraftZones((prev) => prev.filter((z) => z.zone_id !== zoneId));
  };

  const save = async () => {
    if (!zoneMap) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await saveZoneMap({ ...zoneMap, zones: draftZones });
      setZoneMap(updated);
      setMode("view");
      onSaved?.();
    } catch {
      setError("구역 정보를 저장하지 못했습니다.");
    } finally {
      setSaving(false);
    }
  };

  const busy = drafting || namingOpen;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal zone-map-modal" onClick={(e) => e.stopPropagation()}>
        <div className="briefing-card__header">구역 {mode === "edit" ? "편집" : "안내"}</div>
        <p className="zone-map-modal__hint">
          {mode === "view"
            ? "카메라 화면에서 각 구역이 어디까지인지 보여줍니다. 대시보드의 구역별 인원수는 아래 색상 기준으로 집계됩니다."
            : drafting
              ? "화면을 클릭해 구역 경계를 순서대로 찍어주세요. 점 3개 이상이면 완료할 수 있습니다."
              : namingOpen
                ? "새로 그린 구역의 이름을 입력해주세요."
                : "구역을 추가하거나 기존 구역을 삭제한 뒤 저장하세요."}
        </p>
        <div className="briefing-card__image-frame">
          <img className="briefing-card__image" src={frameUrl(FIRST_FRAME_PATH)} alt="카메라 첫 프레임" />
          <svg
            ref={svgRef}
            className={`briefing-card__image-overlay ${drafting ? "zone-map-modal__svg--drafting" : ""}`}
            viewBox={`0 0 ${frameWidth} ${frameHeight}`}
            preserveAspectRatio="none"
            onClick={handleSvgClick}
          >
            {displayZones.map((zone, i) => {
              const color = ZONE_COLORS[i % ZONE_COLORS.length];
              const points = zone.polygon.map(([x, y]) => `${x},${y}`).join(" ");
              const [cx, cy] = polygonCenter(zone.polygon);
              return (
                <g key={zone.zone_id}>
                  <polygon points={points} fill={color} fillOpacity={0.2} stroke={color} strokeWidth={Math.max(2, frameWidth / 300)} />
                  <text
                    x={cx}
                    y={cy}
                    fill={color}
                    fontSize={frameWidth / 22}
                    fontWeight={800}
                    textAnchor="middle"
                    fontFamily="ui-monospace, monospace"
                  >
                    {zone.zone_id}
                  </text>
                </g>
              );
            })}

            {(drafting || namingOpen) && drawingPoints.length > 0 && (
              <g>
                <polyline
                  points={drawingPoints.map(([x, y]) => `${x},${y}`).join(" ")}
                  fill="none"
                  stroke="var(--accent)"
                  strokeWidth={Math.max(2, frameWidth / 300)}
                />
                {drawingPoints.length >= 3 && (
                  <line
                    x1={drawingPoints[drawingPoints.length - 1][0]}
                    y1={drawingPoints[drawingPoints.length - 1][1]}
                    x2={drawingPoints[0][0]}
                    y2={drawingPoints[0][1]}
                    stroke="var(--accent)"
                    strokeDasharray="8 6"
                    strokeWidth={Math.max(2, frameWidth / 300)}
                  />
                )}
                {drawingPoints.map(([x, y], i) => (
                  <circle key={i} cx={x} cy={y} r={Math.max(4, frameWidth / 220)} fill="var(--accent)" />
                ))}
              </g>
            )}
          </svg>
        </div>

        {mode === "edit" && drafting && (
          <div className="zone-map-modal__toolbar">
            <span className="zone-map-modal__point-count">{drawingPoints.length}개 점</span>
            <button onClick={undoLastPoint} disabled={drawingPoints.length === 0} className="zone-map-modal__btn">
              마지막 점 취소
            </button>
            <button onClick={finishDrawing} disabled={drawingPoints.length < 3} className="zone-map-modal__btn zone-map-modal__btn--primary">
              완료
            </button>
            <button onClick={cancelDrawing} className="zone-map-modal__btn">
              그리기 취소
            </button>
          </div>
        )}

        {mode === "edit" && namingOpen && (
          <div className="zone-map-modal__toolbar">
            <input
              className="zone-map-modal__name-input"
              value={nameInput}
              onChange={(e) => setNameInput(e.target.value)}
              placeholder="구역 이름 (예: 적재구역)"
              autoFocus
              onKeyDown={(e) => e.key === "Enter" && confirmName()}
            />
            <button onClick={confirmName} className="zone-map-modal__btn zone-map-modal__btn--primary">
              구역 추가
            </button>
            <button onClick={cancelNaming} className="zone-map-modal__btn">
              취소
            </button>
          </div>
        )}

        {mode === "edit" && !busy && (
          <div className="zone-map-modal__zone-list">
            {draftZones.length === 0 && <p className="zone-map-modal__empty">등록된 구역이 없습니다.</p>}
            {draftZones.map((zone, i) => (
              <div key={zone.zone_id} className="zone-map-modal__zone-item">
                <span className="zone-map-modal__zone-swatch" style={{ background: ZONE_COLORS[i % ZONE_COLORS.length] }} />
                <span className="zone-map-modal__zone-name">{zone.zone_id}</span>
                <span className="zone-map-modal__zone-points">{zone.polygon.length}개 점</span>
                <button className="zone-map-modal__zone-delete" onClick={() => deleteZone(zone.zone_id)}>
                  삭제
                </button>
              </div>
            ))}
            <button onClick={startDrawing} className="zone-map-modal__btn">
              + 새 구역 그리기
            </button>
          </div>
        )}

        {error && <p className="zone-map-modal__error">{error}</p>}

        <div className="zone-map-modal__actions">
          {mode === "view" ? (
            <>
              <button onClick={startEdit} className="zone-map-modal__btn" disabled={!zoneMap}>
                편집
              </button>
              <button className="modal__close" onClick={onClose}>
                닫기
              </button>
            </>
          ) : (
            <>
              <button onClick={cancelEdit} className="zone-map-modal__btn" disabled={saving}>
                취소
              </button>
              <button onClick={save} disabled={saving || busy} className="zone-map-modal__btn zone-map-modal__btn--primary">
                {saving ? "저장 중..." : "저장"}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
