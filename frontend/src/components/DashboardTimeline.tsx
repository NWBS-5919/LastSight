import { useMemo, useState } from "react";
import { mergePpeViolations } from "../api";
import { categoryColor, combinedBreakdown, STAY_CATEGORY } from "../situationUtils";
import { assignTimelineLayout } from "../timelineLayout";
import type { FireAlert, PpeViolationEntry, SituationCheckEntry } from "../types";

// 2026-08-03: 평상시 타임라인(PPE 위반)과 비상시 타임라인(2차 확인 이정표)을 화재 발생을
// 기점으로 완전히 갈아치웠는데, 그러면 화재가 나는 순간 지금까지의 평상시 기록이 화면에서
// 통째로 사라져 버렸다(실측 — 사용자가 지적). 화재는 "다른 화면으로 전환"이 아니라 "같은
// 하루 안에 일어난 사건"이므로, 시나리오 시작(t=0)을 공통 기준점으로 삼아 평상시 위반
// 이력 → 화재 발생 → 화재 이후 2차 확인 이정표를 한 타임라인에 이어서 그린다.

type NodeAction = { kind: "ppe"; entry: PpeViolationEntry } | { kind: "situation"; entry: SituationCheckEntry } | { kind: "fire"; alert: FireAlert };

interface TimelineNode {
  key: string;
  label: string;
  elapsedSeconds: number;
  color: string;
  action: NodeAction | null;
  absoluteAt?: string; // 라벨 아래에 절대 시각도 같이 보여줘야 하는 노드(화재 발생)에만 채움
}

interface Props {
  cameraId: string;
  scenarioStartedAt: string | null;
  fireAlert: FireAlert | null;
  ppeEvents: PpeViolationEntry[];
  situationChecks: SituationCheckEntry[];
  onSelectPpe: (entry: PpeViolationEntry) => void;
  onSelectSituation: (entry: SituationCheckEntry) => void;
  onSelectFire: (alert: FireAlert) => void;
}

const RED = "var(--danger)";
const GREEN = "var(--ok)";
const MUTED = "var(--muted)";

function effectiveHelmet(entry: PpeViolationEntry) {
  return entry.reviewed_helmet ?? entry.helmet_state;
}
function effectiveVest(entry: PpeViolationEntry) {
  return entry.reviewed_vest ?? entry.vest_state;
}

function isStillViolation(entry: PpeViolationEntry): boolean {
  return effectiveHelmet(entry) === "not_worn" || effectiveVest(entry) === "not_worn";
}

// 2026-08-03 정정: 라벨을 항상 entry.violations(=AI가 원래 감지했을 때의 위반 목록)로만
// 만들었더니, 관리자가 "둘 다 착용"으로 정정해도 타임라인엔 여전히 "헬멧, 조끼 미착용
// (정정됨)"처럼 "미착용" 문구가 그대로 남는 문제가 있었다(실측 — 사용자가 지적). 지금
// 실제로 유효한 상태(reviewed_* ?? 원본)를 기준으로 라벨을 다시 만든다 — 예: 조끼만
// 미착용으로 남았으면 "조끼 미착용"만, 둘 다 착용으로 정정했으면 "착용 확인됨"으로.
function violationLabel(entry: PpeViolationEntry): string {
  const stillViolated = [
    effectiveHelmet(entry) === "not_worn" && "헬멧",
    effectiveVest(entry) === "not_worn" && "조끼",
  ].filter((v): v is string => Boolean(v));
  if (stillViolated.length > 0) return `${stillViolated.join(", ")} 미착용`;
  return "착용 확인됨";
}

function buildNodes(
  scenarioStartedAt: string | null,
  fireAlert: FireAlert | null,
  ppeEvents: PpeViolationEntry[],
  situationChecks: SituationCheckEntry[],
): TimelineNode[] {
  if (!scenarioStartedAt) return [];
  const fireTriggeredAt = fireAlert?.triggered_at ?? null;
  const startMs = new Date(scenarioStartedAt).getTime();
  const elapsedOf = (iso: string) => Math.max(0, Math.round((new Date(iso).getTime() - startMs) / 1000));

  const nodes: TimelineNode[] = [{ key: "start", label: "영상 시작", elapsedSeconds: 0, color: "var(--overlay-neutral)", action: null }];

  for (const entry of ppeEvents) {
    const reviewed = entry.reviewed_at != null;
    const stillViolation = isStillViolation(entry);
    const label = violationLabel(entry);
    nodes.push({
      key: entry.id,
      label: reviewed ? `${label} (정정됨)` : label,
      elapsedSeconds: elapsedOf(entry.at),
      color: stillViolation ? RED : reviewed ? MUTED : GREEN,
      action: { kind: "ppe", entry },
    });
  }

  if (fireTriggeredAt && fireAlert) {
    nodes.push({
      key: "fire",
      label: "화재 발생",
      elapsedSeconds: elapsedOf(fireTriggeredAt),
      color: RED,
      action: { kind: "fire", alert: fireAlert },
      absoluteAt: fireTriggeredAt,
    });

    // 2차 확인 이정표는 "새로운 최고 인원 기록"이 나올 때만 뽑는다 — 매초 쌓이는 카드를
    // 전부 표시하지 않고, 상황이 실제로 악화된 순간만 짚어준다.
    const runningMax: Record<string, number> = {};
    for (const entry of situationChecks) {
      const breakdown = combinedBreakdown(entry);
      const elapsedSeconds = elapsedOf(entry.at);
      for (const [category, count] of Object.entries(breakdown)) {
        if (category === STAY_CATEGORY || count <= 0) continue;
        const prevMax = runningMax[category] ?? 0;
        if (count > prevMax) {
          runningMax[category] = count;
          nodes.push({
            key: `${category}-${count}-${entry.at}`,
            label: `${category} ${count}명 발생`,
            elapsedSeconds,
            color: categoryColor(category),
            action: { kind: "situation", entry },
          });
        }
      }
    }

    const lastEntry = situationChecks[situationChecks.length - 1];
    if (lastEntry) {
      const lastBreakdown = combinedBreakdown(lastEntry);
      nodes.push({
        key: `final-${lastEntry.at}`,
        label: `종료 시점 · 체류중 ${lastBreakdown[STAY_CATEGORY] ?? 0}명`,
        elapsedSeconds: elapsedOf(lastEntry.at),
        color: categoryColor(STAY_CATEGORY),
        action: { kind: "situation", entry: lastEntry },
      });
    }
  }

  return nodes.sort((a, b) => a.elapsedSeconds - b.elapsedSeconds);
}

export function DashboardTimeline({
  cameraId,
  scenarioStartedAt,
  fireAlert,
  ppeEvents,
  situationChecks,
  onSelectPpe,
  onSelectSituation,
  onSelectFire,
}: Props) {
  const nodes = useMemo(
    () => buildNodes(scenarioStartedAt, fireAlert, ppeEvents, situationChecks),
    [scenarioStartedAt, fireAlert, ppeEvents, situationChecks],
  );
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [dragOverId, setDragOverId] = useState<string | null>(null);
  const [mergeError, setMergeError] = useState<string | null>(null);

  if (nodes.length === 0) return null;

  const maxElapsed = Math.max(1, ...nodes.map((n) => n.elapsedSeconds));
  const trackWidth = Math.max(560, nodes.length * 130);
  const layout = assignTimelineLayout(
    nodes.map((n) => ({ elapsedSeconds: n.elapsedSeconds, label: n.label })),
    trackWidth,
    maxElapsed,
  );
  const ROW_HEIGHT = 34;
  const BASE_OFFSET = 14;
  const maxAboveTier = Math.max(0, ...layout.filter((l) => l.side === "above").map((l) => l.tier));
  const maxBelowTier = Math.max(0, ...layout.filter((l) => l.side === "below").map((l) => l.tier));
  // 화재 노드는 절대 시각 줄이 하나 더 붙어(3줄) 다른 노드(2줄)보다 세로로 더 길다 —
  // 잘리지 않게 여유 공간을 더 확보한다.
  const hasAbsoluteTimeLabel = nodes.some((n) => n.absoluteAt);
  const trackHeight = 40 + (maxAboveTier + 1) * ROW_HEIGHT + (maxBelowTier + 1) * ROW_HEIGHT + (hasAbsoluteTimeLabel ? 18 : 0);

  const handleClick = (action: NodeAction | null) => {
    if (!action) return;
    if (action.kind === "ppe") onSelectPpe(action.entry);
    else if (action.kind === "situation") onSelectSituation(action.entry);
    else onSelectFire(action.alert);
  };

  // 2026-08-03: 위치 매칭 실패로 같은 사람의 같은 위반이 노드 두 개로 쪼개지는 경우가
  // 있어(development_log.md 참고), 관리자가 직접 "이 둘은 사실 하나였다"고 확정할 수 있게
  // 드래그로 합치는 기능을 추가했다 — PPE 노드끼리만 합칠 수 있다(화재/2차확인 노드는 대상 아님).
  const handleDrop = async (targetId: string) => {
    const sourceId = draggingId;
    setDraggingId(null);
    setDragOverId(null);
    if (!sourceId || sourceId === targetId) return;
    try {
      await mergePpeViolations(cameraId, sourceId, targetId);
    } catch {
      setMergeError("두 항목을 합치지 못했습니다. 다시 시도해주세요.");
    }
  };

  return (
    <div className="situation-timeline">
      {mergeError && <p className="situation-timeline__error">{mergeError}</p>}
      <div className="situation-timeline__scroll">
        <div className="situation-timeline__track" style={{ width: `${trackWidth}px`, height: `${trackHeight}px` }}>
          {nodes.map((n, i) => {
            const isPpe = n.action?.kind === "ppe";
            const isDragOver = isPpe && dragOverId === n.key && draggingId !== n.key;
            const { side, tier } = layout[i];
            const offset = BASE_OFFSET + tier * ROW_HEIGHT;
            const labelStyle = side === "above" ? { bottom: `${offset}px`, top: "auto" } : { top: `${offset}px` };
            return (
              <button
                key={n.key}
                className={`situation-timeline__point ${isDragOver ? "situation-timeline__point--drop-target" : ""}`}
                style={{ left: `${(n.elapsedSeconds / maxElapsed) * 100}%` }}
                onClick={() => handleClick(n.action)}
                disabled={!n.action}
                draggable={isPpe}
                onDragStart={() => setDraggingId(n.key)}
                onDragEnd={() => {
                  setDraggingId(null);
                  setDragOverId(null);
                }}
                onDragOver={(e) => {
                  if (!isPpe || draggingId === n.key) return;
                  e.preventDefault();
                }}
                onDragEnter={() => {
                  if (isPpe && draggingId !== n.key) setDragOverId(n.key);
                }}
                onDragLeave={() => setDragOverId((cur) => (cur === n.key ? null : cur))}
                onDrop={(e) => {
                  e.preventDefault();
                  if (isPpe) void handleDrop(n.key);
                }}
              >
                <span
                  className="situation-timeline__stem"
                  style={
                    side === "above"
                      ? { bottom: 0, height: `${offset}px`, background: n.color }
                      : { top: 0, height: `${offset}px`, background: n.color }
                  }
                />
                {n.key === "fire" ? (
                  <svg className="situation-timeline__flame" viewBox="0 0 24 24" fill={n.color}>
                    <path d="M12.395 2.553a1 1 0 00-1.45-.385c-.345.23-.614.558-.822.88-.214.33-.403.713-.57 1.116-.334.804-.614 1.768-.84 2.734a31.365 31.365 0 00-.613 3.58 2.64 2.64 0 01-.945-1.067c-.328-.68-.398-1.534-.398-2.654A1 1 0 005.05 6.05 6.981 6.981 0 003 11a7 7 0 1011.95-4.95c-.592-.591-.98-.985-1.348-1.467-.363-.476-.724-1.063-1.207-2.03z" />
                  </svg>
                ) : (
                  <span className="situation-timeline__dot" style={{ background: n.color }} />
                )}
                <span className="situation-timeline__label" style={labelStyle}>
                  {n.label}
                  <br />
                  <span className="situation-timeline__time">+{n.elapsedSeconds}초</span>
                  {n.absoluteAt && (
                    <>
                      <br />
                      <span className="situation-timeline__abs-time">{new Date(n.absoluteAt).toLocaleTimeString("ko-KR")}</span>
                    </>
                  )}
                </span>
              </button>
            );
          })}
        </div>
      </div>
      <div className="situation-timeline__footer">
        <p className="situation-timeline__hint">같은 사람의 중복된 PPE 위반 노드는 서로 끌어다 놓으면 하나로 합쳐집니다.</p>
      </div>
    </div>
  );
}
