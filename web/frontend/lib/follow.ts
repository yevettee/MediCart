// 회진 근접판정 순수 로직(의존성 0 — vitest로 단위테스트).
export type Pt = { x: number; y: number };
export type ArrivalTarget = { key: string; label: string; x: number; y: number };

// pose에 가장 가까운 타겟 1개를 히스테리시스로 판정.
// prevKey와 같은 타겟이면 exitR(이탈 반경), 아니면 enterR(진입 반경) 기준.
export function nearestArrival(
  pose: Pt | undefined,
  targets: ArrivalTarget[],
  prevKey: string | null,
  enterR = 1.0,
  exitR = 1.2,
): ArrivalTarget | null {
  if (!pose || targets.length === 0) return null;
  let best: ArrivalTarget | null = null;
  let bestD = Infinity;
  for (const t of targets) {
    const d = Math.hypot(pose.x - t.x, pose.y - t.y);
    if (d < bestD) { bestD = d; best = t; }
  }
  if (!best) return null;
  const r = best.key === prevKey ? exitR : enterR;
  return bestD <= r ? best : null;
}
