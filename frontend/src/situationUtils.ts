import type { SituationCheckEntry } from "./types";

export const STAY_CATEGORY = "체류중";

export const CATEGORY_COLOR: Record<string, string> = {
  [STAY_CATEGORY]: "#4ade80", // 초록 — 우려 없음
  "쓰러진 사람": "#ff2d2d", // 빨강
  "연기에 둘러싸인 사람": "#3b82f6", // 파랑
};

export function categoryColor(category: string): string {
  return CATEGORY_COLOR[category] ?? "#e8e8ec";
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
