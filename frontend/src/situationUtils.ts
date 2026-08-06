import type { SituationCheckEntry } from "./types";

export const STAY_CATEGORY = "체류중";

// 2026-08-06: 하드코딩 hex 대신 index.css의 공유 색상 토큰을 참조한다 — 앱 전체가 같은
// "위험=danger, 정상=ok, 연기 관련=smoke" 팔레트를 쓰도록 통일(전에는 컴포넌트마다 살짝
// 다른 값을 따로 갖고 있어 같은 의미인데 색이 어긋나는 경우가 있었다).
export const CATEGORY_COLOR: Record<string, string> = {
  [STAY_CATEGORY]: "var(--ok)",
  "쓰러진 사람": "var(--danger)",
  "연기에 둘러싸인 사람": "var(--smoke)",
};

export function categoryColor(category: string): string {
  return CATEGORY_COLOR[category] ?? "var(--overlay-neutral)";
}

export function combinedBreakdown(entry: SituationCheckEntry): Record<string, number> {
  const combined: Record<string, number> = {};
  for (const zone of entry.zones) {
    for (const [category, count] of Object.entries(zone.breakdown)) {
      combined[category] = (combined[category] ?? 0) + count;
    }
  }
  return combined;
}

export interface SituationInterval {
  start: SituationCheckEntry;
  end: SituationCheckEntry;
  sampleCount: number;
}

function situationSignature(entry: SituationCheckEntry): string {
  const zones = [...entry.zones]
    .sort((a, b) => a.zone_id.localeCompare(b.zone_id, "ko"))
    .map((zone) => ({
      zoneId: zone.zone_id,
      total: zone.total,
      breakdown: Object.entries(zone.breakdown)
        .filter(([, count]) => count > 0)
        .sort(([a], [b]) => a.localeCompare(b, "ko")),
    }));
  return JSON.stringify(zones);
}

// 초 단위 원본은 증거와 브리핑 계산을 위해 그대로 두되, 화면에서는 구역별 총인원과
// 분류별 인원 구성이 바뀔 때만 새 구간을 만든다. bbox는 사람의 이동만으로 매 프레임
// 달라지므로 동일 상태 판정에 포함하지 않는다.
export function buildSituationIntervals(entries: SituationCheckEntry[]): SituationInterval[] {
  const sorted = [...entries].sort((a, b) => new Date(a.at).getTime() - new Date(b.at).getTime());
  const intervals: SituationInterval[] = [];

  for (const entry of sorted) {
    const previous = intervals[intervals.length - 1];
    if (previous && situationSignature(previous.end) === situationSignature(entry)) {
      previous.end = entry;
      previous.sampleCount += 1;
    } else {
      intervals.push({ start: entry, end: entry, sampleCount: 1 });
    }
  }

  return intervals;
}
