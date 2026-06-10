"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  getPatient, getRooms, markIntakeDone, pushMission, resetIntakeRound,
  getPatrolPhase, sendPatrolAdvance, type GotoTarget,
} from "@/lib/api";
import { PATROL_STOPS, STOP_ROOMS, decideAfterScan, nextStop } from "@/lib/patrol";
import { useQrScanner } from "@/lib/useQrScanner";
import IntakeForm from "@/components/IntakeForm";

const PID_RE = /^P-\d{4}-\d{4}$/;
const QR_WAIT_MS = 60_000;       // 호실당 QR 대기
const TIMEOUT_DWELL_MS = 5_000;  // 시간초과 메시지 후 다음 호실
const MSG_DWELL_MS = 2_500;      // intro / skip 메시지
const ARRIVE_TIMEOUT_MS = 90_000;
const POLL_MS = 1_000;           // patrol/phase 폴링 주기

type Step =
  | "intro" | "moving" | "moveDelay" | "scanning"
  | "intake" | "skip" | "timeout" | "returning" | "done";

type Props = { active: boolean; ns: string; targets: Record<string, GotoTarget>; onExit: () => void };

export default function PatrolIntakeOverlay({ active, ns, targets, onExit }: Props) {
  const [step, setStep] = useState<Step>("intro");
  const [idx, setIdx] = useState(0);
  const [pid, setPid] = useState<string>("");
  const [note, setNote] = useState<string>("");
  const stepRef = useRef<Step>("intro");
  stepRef.current = step;
  const idxRef = useRef(0);
  idxRef.current = idx;
  const lastArrivedRef = useRef<number>(-1);   // 처리한 도착 idx(중복 방지)

  const stopKey = PATROL_STOPS[idx];
  const stopTarget = targets[stopKey];
  const stopLabel = stopTarget?.label ?? `정류장 ${idx + 1}`;
  const dock = targets["dock"] ?? { label: "도크", x: -8, y: -6, yaw: 0 };

  // 순회 정차 목록(patrol_intake_mission params) — targets 없는 정류장은 제외.
  const buildStops = useCallback(() => PATROL_STOPS.flatMap((key) => {
    const t = targets[key];
    return t ? [{ x: t.x, y: t.y, yaw: t.yaw ?? 0, room: STOP_ROOMS[key] ?? "", label: t.label ?? key }] : [];
  }), [targets]);

  // QR 디코드 → 환자 분기 (scanning 단계에서만)
  const onDecode = useCallback(async (raw: string) => {
    if (stepRef.current !== "scanning" || !PID_RE.test(raw)) return;
    const p = await getPatient(raw).catch(() => null);
    if (stepRef.current !== "scanning") return;   // await 중 단계 이탈 시 늦은 디코드 폐기
    const decision = decideAfterScan(p);
    if (decision === "unknown") { setNote(`등록되지 않은 QR: ${raw}`); return; }
    // 병상 배정환자 대조 — 이 병상 환자가 아니면 거부하고 계속 스캔.
    const room = STOP_ROOMS[PATROL_STOPS[idxRef.current]];
    if (room) {
      try {
        const rooms = await getRooms();
        if (stepRef.current !== "scanning") return;
        const assigned = (rooms[room] as { patient?: string } | undefined)?.patient;
        if (assigned && assigned !== raw) { setNote(`이 병상(${room}) 환자가 아닙니다`); return; }
      } catch { /* 대조 실패 시 통과(폴백) */ }
    }
    setPid(raw);
    if (decision === "skip") { setNote(`${p?.성명 ?? raw} — 이미 문진 완료`); setStep("skip"); }
    else { setNote(""); setStep("intake"); }
  }, []);

  const { videoRef, camOn, camErr, start: startCam, stop: stopCam } = useQrScanner(onDecode);

  // 활성화 시 1회 초기화
  useEffect(() => {
    if (!active) return;
    setStep("intro"); setIdx(0); setPid(""); setNote("");
    lastArrivedRef.current = -1;
  }, [active]);

  // 도착 처리: 해당 병상에서 QR 스캔 시작
  const arriveAt = useCallback((i: number) => {
    if (i < 0 || i >= PATROL_STOPS.length) return;
    lastArrivedRef.current = i;
    setIdx(i); setNote(""); setPid("");
    setStep("scanning");
  }, []);

  // intro → 회차 리셋 + patrol_intake_mission 1건 발행(로봇이 undock→순회 자율 수행) → 이동
  useEffect(() => {
    if (!active || step !== "intro") return;
    let alive = true;
    resetIntakeRound().catch(() => {});
    const stops = buildStops();
    if (stops.length) {
      pushMission(ns, "patrol_intake_mission",
        { stops, home: { x: dock.x, y: dock.y, yaw: dock.yaw ?? 0 } }).catch(() => {});
    }
    const t = setTimeout(() => { if (alive) setStep("moving"); }, MSG_DWELL_MS);
    return () => { alive = false; clearTimeout(t); };
  }, [active, step]); // eslint-disable-line react-hooks/exhaustive-deps

  // 폴링: RTDB patrol/phase 로 도착·복귀완료 감지 (pose 근접 추측 대체)
  useEffect(() => {
    if (!active) return;
    const poll = async () => {
      try {
        const p = await getPatrolPhase();
        if (stepRef.current === "returning") {
          if (p.phase === "idle") setStep("done");
          return;
        }
        if (
          p.phase === "arrived" && typeof p.stop?.idx === "number" &&
          p.stop.idx !== lastArrivedRef.current && stepRef.current === "moving"
        ) {
          arriveAt(p.stop.idx);
        }
      } catch { /* 폴링 실패 무시 */ }
    };
    const t = setInterval(poll, POLL_MS);
    return () => clearInterval(t);
  }, [active, arriveAt]);

  // moving 지연 워치독 → moveDelay (도착 신호 미수신 시 수동 폴백 노출)
  useEffect(() => {
    if (step !== "moving") return;
    const wd = setTimeout(() => { if (stepRef.current === "moving") setStep("moveDelay"); }, ARRIVE_TIMEOUT_MS);
    return () => clearTimeout(wd);
  }, [step]);

  // 로봇 미연결/지연 폴백: 수동으로 다음 병상 도착 처리
  const manualArrive = useCallback(() => {
    const n = lastArrivedRef.current + 1;   // 최초 -1 → 0
    if (n < PATROL_STOPS.length) arriveAt(n);
  }, [arriveAt]);

  // scanning 진입 시 카메라 ON + 60s 타임아웃, 떠날 때 카메라 OFF
  useEffect(() => {
    if (step !== "scanning") return;
    setNote("");
    startCam();
    const to = setTimeout(() => { if (stepRef.current === "scanning") setStep("timeout"); }, QR_WAIT_MS);
    return () => { clearTimeout(to); stopCam(); };
  }, [step, startCam, stopCam]);

  // 정차 종료 → 핸드셰이크(intake_done) → 로봇이 다음 병상/복귀로 진행
  const advance = useCallback(() => {
    sendPatrolAdvance().catch(() => {});
    const n = nextStop(idxRef.current, PATROL_STOPS.length);
    if (n === "return") setStep("returning");        // 로봇 홈 복귀 → phase=idle 대기
    else { setIdx(n); setNote(""); setPid(""); setStep("moving"); }  // 다음 도착 신호 대기
  }, []);

  // skip / timeout 메시지 후 다음 정류장
  useEffect(() => {
    if (step !== "skip" && step !== "timeout") return;
    const dwell = step === "timeout" ? TIMEOUT_DWELL_MS : MSG_DWELL_MS;
    const t = setTimeout(() => advance(), dwell);
    return () => clearTimeout(t);
  }, [step, advance]);

  // returning 완료(phase=idle) → done → 닫기
  useEffect(() => { if (step === "done") onExit(); }, [step, onExit]);

  const onIntakeSaved = useCallback(() => {
    if (pid) markIntakeDone(pid).catch(() => {});
    setNote("문진 저장 완료");
    advance();
  }, [pid, advance]);

  // 중단: 핸드셰이크로 현재 정차를 빠져나가 로봇이 복귀하도록 + UI 복귀 대기.
  // (완전 취소는 시퀀서 cancel 지원 필요 — 후속 과제)
  const abort = useCallback(() => {
    pushMission(ns, "mission_cancel", {}).catch(() => {});
    setStep("returning");
  }, [ns]);

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
              <div className="mt-6 flex gap-3 justify-center">
                <button onClick={() => setStep("moving")} className="px-6 py-3 rounded-2xl bg-white/15 hover:bg-white/25 font-semibold">다시 대기</button>
                <button onClick={manualArrive} className="px-6 py-3 rounded-2xl bg-white text-[#0b1f1d] font-semibold">수동 도착 처리</button>
              </div>
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
    case "moveDelay": return "이동 지연 — 도착 신호 대기 중";
    case "skip": return note || "이미 문진 완료 — 다음 호실로";
    case "timeout": return "시간 초과 — 다음 호실로 이동합니다";
    case "returning": return "복귀 중…";
    case "done": return "순회 완료";
    default: return "";
  }
}
