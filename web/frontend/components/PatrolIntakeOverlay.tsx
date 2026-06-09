"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE, getPatient, markIntakeDone, pushMission, resetIntakeRound, type GotoTarget } from "@/lib/api";
import { nearestArrival, type ArrivalTarget, type Pt } from "@/lib/follow";
import { PATROL_STOPS, decideAfterScan, nextStop } from "@/lib/patrol";
import { useQrScanner } from "@/lib/useQrScanner";
import IntakeForm from "@/components/IntakeForm";

const PID_RE = /^P-\d{4}-\d{4}$/;
const QR_WAIT_MS = 60_000;       // 호실당 QR 대기
const TIMEOUT_DWELL_MS = 5_000;  // 시간초과 메시지 후 다음 호실
const MSG_DWELL_MS = 2_500;      // intro / skip 메시지
const ARRIVE_TIMEOUT_MS = 90_000;

type Step =
  | "intro" | "moving" | "moveDelay" | "scanning"
  | "intake" | "skip" | "timeout" | "returning" | "done";

type Props = { active: boolean; ns: string; targets: Record<string, GotoTarget>; onExit: () => void };

export default function PatrolIntakeOverlay({ active, ns, targets, onExit }: Props) {
  const [step, setStep] = useState<Step>("intro");
  const [idx, setIdx] = useState(0);
  const [pose, setPose] = useState<Pt | undefined>();
  const [isDocked, setIsDocked] = useState<boolean | undefined>();
  const [pid, setPid] = useState<string>("");
  const [note, setNote] = useState<string>("");
  const stepRef = useRef<Step>("intro");
  stepRef.current = step;
  const idxRef = useRef(0);
  idxRef.current = idx;

  const stopKey = PATROL_STOPS[idx];
  const stopTarget = targets[stopKey];
  const stopLabel = stopTarget?.label ?? `정류장 ${idx + 1}`;
  const dock = targets["dock"] ?? { label: "도크", x: -8, y: -6, yaw: 0 };

  // QR 디코드 → 환자 분기 (scanning 단계에서만)
  const onDecode = useCallback(async (raw: string) => {
    if (stepRef.current !== "scanning" || !PID_RE.test(raw)) return;
    const p = await getPatient(raw).catch(() => null);
    const decision = decideAfterScan(p);
    if (decision === "unknown") { setNote(`등록되지 않은 QR: ${raw}`); return; }
    setPid(raw);
    if (decision === "skip") { setNote(`${p?.성명 ?? raw} — 이미 문진 완료`); setStep("skip"); }
    else { setNote(""); setStep("intake"); }
  }, []);

  const { videoRef, camOn, camErr, start: startCam, stop: stopCam } = useQrScanner(onDecode);

  // SSE 자가 구독(active 동안). pose/dock 수신.
  useEffect(() => {
    if (!active) return;
    const es = new EventSource(`${API_BASE}/api/stream`, { withCredentials: true });
    es.onopen = () => { setStep("intro"); setIdx(0); setPose(undefined); setIsDocked(undefined); setNote(""); };
    es.onmessage = (e) => {
      try {
        const d = JSON.parse(e.data);
        if (d?.source !== ns) return;
        if (d.pose) setPose({ x: d.pose.x, y: d.pose.y });
        if (d.dock) setIsDocked(d.dock.is_docked);
      } catch { /* ignore */ }
    };
    return () => es.close();
  }, [active, ns]);

  const advance = useCallback(() => {
    const n = nextStop(idxRef.current, PATROL_STOPS.length);
    if (n === "return") {
      setStep("returning");
      pushMission(ns, "goto", { x: dock.x, y: dock.y, yaw: dock.yaw ?? 0, dock_after: true }).catch(() => {});
    } else {
      setIdx(n); setNote(""); setPid(""); setStep("moving");
    }
  }, [ns, dock]);

  // intro → 순회 시작(회차 리셋) → 첫 이동
  useEffect(() => {
    if (!active || step !== "intro") return;
    let alive = true;
    resetIntakeRound().catch(() => {});
    const t = setTimeout(() => { if (alive) setStep("moving"); }, MSG_DWELL_MS);
    return () => { alive = false; clearTimeout(t); };
  }, [active, step]);

  // moving → goto 발행 + 도착(반경) 대기 + 지연 워치독
  useEffect(() => {
    if (step !== "moving") return;
    const tgt = targets[PATROL_STOPS[idxRef.current]];
    if (tgt) pushMission(ns, "goto", { x: tgt.x, y: tgt.y, yaw: tgt.yaw ?? 0 }).catch(() => {});
    const wd = setTimeout(() => { if (stepRef.current === "moving") setStep("moveDelay"); }, ARRIVE_TIMEOUT_MS);
    return () => clearTimeout(wd);
  }, [step, ns, targets]);

  // pose 갱신마다 현재 타겟 근접판정 → 도착 시 scanning
  useEffect(() => {
    if (step !== "moving" || !stopTarget) return;
    const at: ArrivalTarget[] = [{ key: stopKey, label: stopLabel, x: stopTarget.x, y: stopTarget.y }];
    if (nearestArrival(pose, at, null)) setStep("scanning");
  }, [step, pose, stopTarget, stopKey, stopLabel]);

  // scanning 진입 시 카메라 ON + 60s 타임아웃, 떠날 때 카메라 OFF
  useEffect(() => {
    if (step !== "scanning") return;
    setNote("");
    startCam();
    const to = setTimeout(() => { if (stepRef.current === "scanning") setStep("timeout"); }, QR_WAIT_MS);
    return () => { clearTimeout(to); stopCam(); };
  }, [step, startCam, stopCam]);

  // skip / timeout 메시지 후 다음 정류장
  useEffect(() => {
    if (step !== "skip" && step !== "timeout") return;
    const dwell = step === "timeout" ? TIMEOUT_DWELL_MS : MSG_DWELL_MS;
    const t = setTimeout(() => advance(), dwell);
    return () => clearTimeout(t);
  }, [step, advance]);

  // returning 완료(도킹) → done → 닫기
  useEffect(() => {
    if (step === "returning" && isDocked === true) setStep("done");
  }, [step, isDocked]);
  useEffect(() => { if (step === "done") onExit(); }, [step, onExit]);

  const onIntakeSaved = useCallback(() => {
    if (pid) markIntakeDone(pid).catch(() => {});
    setNote("문진 저장 완료");
    advance();
  }, [pid, advance]);

  const abort = useCallback(() => {
    pushMission(ns, "mission_cancel", {}).catch(() => {});
    setStep("returning");
    pushMission(ns, "goto", { x: dock.x, y: dock.y, yaw: dock.yaw ?? 0, dock_after: true }).catch(() => {});
  }, [ns, dock]);

  if (!active) return null;

  return (
    <div className="fixed inset-0 z-50 bg-[#0b1f1d] text-white overflow-auto">
      {step === "intake" ? (
        <div className="min-h-full bg-surface text-ink p-7">
          <div className="max-w-[880px] mx-auto">
            <div className="eyebrow">순회 문진 · {stopLabel}</div>
            <h1 className="text-[24px] font-bold mt-1 mb-2">{pid} 문진표 작성</h1>
            <IntakeForm pid={pid} onSaved={onIntakeSaved} />
          </div>
        </div>
      ) : step === "scanning" ? (
        <div className="min-h-full grid place-items-center p-8">
          <div className="w-full max-w-[560px] text-center">
            <div className="text-[clamp(22px,4vw,40px)] font-bold mb-2">{stopLabel} — 환자 QR을 스캔해 주세요</div>
            <div className="text-white/60 mb-6">1분 내 미스캔 시 다음 호실로 이동합니다</div>
            <video ref={videoRef} className="w-full rounded-2xl bg-black" autoPlay muted playsInline />
            {camErr && <p className="text-red-300 mt-3">{camErr}</p>}
            {!camOn && !camErr && <p className="text-white/60 mt-3">카메라 준비 중…</p>}
            {note && <p className="text-amber-200 mt-3">{note}</p>}
          </div>
        </div>
      ) : (
        <div className="min-h-full grid place-items-center p-8">
          <div className="text-center px-8">
            <div className="text-[clamp(40px,9vw,120px)] font-bold leading-tight">{bigText(step, stopLabel, note)}</div>
            <div className="text-[clamp(14px,2vw,22px)] text-white/60 mt-4">{ns.toUpperCase()} · 순회 문진</div>
            {step === "moveDelay" && (
              <button onClick={() => setStep("moving")} className="mt-6 px-6 py-3 rounded-2xl bg-white text-[#0b1f1d] font-semibold">이동 재시도</button>
            )}
          </div>
        </div>
      )}
      {step !== "done" && (
        <button onClick={abort}
          className="fixed bottom-8 right-8 px-7 py-4 rounded-2xl text-[18px] font-semibold bg-white text-[#0b1f1d] shadow-lg">
          순회 중단 · 복귀
        </button>
      )}
    </div>
  );
}

function bigText(step: Step, stopLabel: string, note: string): string {
  switch (step) {
    case "intro": return "순회 문진을 가동합니다.";
    case "moving": return `${stopLabel}(으)로 이동 중…`;
    case "moveDelay": return "이동 지연 — 위치 확인";
    case "skip": return note || "이미 문진 완료 — 다음 호실로";
    case "timeout": return "시간 초과 — 다음 호실로 이동합니다";
    case "returning": return "복귀 중…";
    case "done": return "순회 완료";
    default: return "";
  }
}
