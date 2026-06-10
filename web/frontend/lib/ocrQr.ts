// 처치실 QR 환자 확인 — 순수 3단계 판정(의존성 0, vitest). 표시명은 호출측에서 부여.
export type QrDecision =
  | { kind: "blocked_patient"; scannedPid: string }
  | { kind: "blocked_meds"; unready: { name: string; status: string }[] }
  | { kind: "complete"; injCount: number };

export type InjLike = { id: string; status?: string; 약품명?: string; 약물명?: string };

// 스캔 PID·선택 PID·주사목록 → 판정.
//   다른 환자          → blocked_patient
//   미confirmed 약품 有 → blocked_meds (미준비 목록)
//   전부 confirmed     → complete
export function decideQr(
  scannedPid: string,
  selectedPid: string,
  injections: InjLike[],
): QrDecision {
  if (scannedPid !== selectedPid) return { kind: "blocked_patient", scannedPid };
  const unready = injections
    .filter((i) => i.status !== "confirmed")
    .map((i) => ({ name: (i.약품명 || i.약물명 || i.id), status: i.status ?? "pending" }));
  if (unready.length > 0) return { kind: "blocked_meds", unready };
  return { kind: "complete", injCount: injections.length };
}
