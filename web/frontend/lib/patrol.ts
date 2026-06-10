// 순회 문진 순수 로직(의존성 0 — vitest 단위테스트). 오버레이 상태머신이 사용.

// 정류장 키(= /api/targets 의 키). 라벨은 targets 에서 가져온다.
export const PATROL_STOPS = ["t101_1", "t101_2"] as const;

// 스캔된 환자 → 다음 동작 분기.
//   intake : 문진표로 (intake_done=false 또는 미설정)
//   skip   : 다음 호실 (intake_done=true)
//   unknown: 미등록 QR (환자 조회 실패) — 계속 스캔 대기
export function decideAfterScan(
  p: { intake_done?: boolean } | null,
): "intake" | "skip" | "unknown" {
  if (!p) return "unknown";
  return p.intake_done ? "skip" : "intake";
}

// 현재 정류장 인덱스 → 다음 인덱스 또는 복귀 신호.
export function nextStop(idx: number, total: number): number | "return" {
  return idx + 1 < total ? idx + 1 : "return";
}
