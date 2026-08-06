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
