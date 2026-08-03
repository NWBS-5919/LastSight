// DashboardTimeline이 쓰는 라벨 배치 로직.
// 시간상 가까운 이정표끼리 라벨이 겹치는 걸 줄이기 위해, 각 항목을 놓을 때마다 위/아래
// 두 방향 각각에 여러 단(tier)을 두고, 라벨 폭(글자 수로 추정)만큼 간격이 나는 가장
// 가까운 단을 그리디하게 골라 채운다 — 단 하나만 쓰면(예전 방식) 시간이 가까운 이정표가
// 3개 이상 몰릴 때 같은 단 안에서도 겹쳤다(실측 — 종료 시점 부근에서 라벨이 겹쳐 안 보임).
export interface TimelineLayoutItem {
  side: "above" | "below";
  tier: number;
}

function estimateLabelHalfWidth(label: string): number {
  // 모노스페이스 11px 기준 한글 글자는 대략 11px, 나머지는 더 좁다 — 정확한 측정 대신
  // 글자 수 기반으로 대략치를 잡는다(과소평가해서 겹치는 것보다 과대평가가 안전).
  return Math.min(140, Math.max(40, label.length * 5));
}

export function assignTimelineLayout(
  items: { elapsedSeconds: number; label: string }[],
  trackWidth: number,
  maxElapsed: number,
): TimelineLayoutItem[] {
  const laneLastX: { above: number[]; below: number[] } = { above: [], below: [] };

  const pick = (side: "above" | "below", x: number, minGap: number): number => {
    const lanes = laneLastX[side];
    for (let tier = 0; tier < lanes.length; tier++) {
      if (x - lanes[tier] >= minGap) return tier;
    }
    return lanes.length;
  };

  return items.map(({ elapsedSeconds, label }) => {
    const x = (elapsedSeconds / maxElapsed) * trackWidth;
    const minGap = estimateLabelHalfWidth(label) * 2 + 12;

    const aboveTier = pick("above", x, minGap);
    const belowTier = pick("below", x, minGap);
    // 더 낮은(=화면상 dot에 더 가까운) 단을 쓸 수 있는 쪽을 우선한다. 둘 다 새 단을
    // 만들어야 한다면(동률) 아래쪽을 우선해 기존 배치와 방향을 맞춘다.
    const side: "above" | "below" = aboveTier < belowTier ? "above" : "below";
    const tier = side === "above" ? aboveTier : belowTier;

    laneLastX[side][tier] = x;
    return { side, tier };
  });
}
