"use client";
import { useCallback, useEffect, useState } from "react";
import { getNurseCartPhase, nurseCartRoundDone, type NurseCartPhase } from "@/lib/api";

// 회진(시나리오 B) 단계 인식 풀스크린 오버레이.
// 로봇이 {ns}/nurse_cart/phase 를 기록하고, 웹은 폴링해 현재 단계를 표시한다.
//   idle: 약품실로 이동 중 · arrived: 약품실 도착(OCR 대기) · tracking: 추종 중 · done: 복귀 완료
// OCR 완료는 /ocr 화면에서, 회진 종료(추종 중지·복귀)는 이 오버레이의 버튼으로.

type Props = { active: boolean; ns: string; onExit: () => void };

const STEP_LABELS: { key: NurseCartPhase; short: string }[] = [
  { key: "idle", short: "이동" },
  { key: "arrived", short: "약품실·OCR" },
  { key: "tracking", short: "추종" },
  { key: "done", short: "복귀" },
];

const PHASE_TEXT: Record<NurseCartPhase, string> = {
  idle: "약품실로 이동 중…",
  arrived: "약품실 도착 — OCR을 진행하세요",
  tracking: "간호사 추종 중",
  done: "복귀·도킹 완료",
};

const PHASE_SUB: Record<NurseCartPhase, string> = {
  idle: "로봇이 약품실로 이동합니다.",
  arrived: "약품 OCR 페이지(/ocr)에서 스캔 후 'OCR 완료'를 누르면 로봇이 입구로 이동해 추종을 시작합니다.",
  tracking: "회진이 끝나면 아래 '회진 종료'를 누르세요 — 로봇이 홈으로 복귀·도킹합니다.",
  done: "회진이 종료되었습니다.",
};

export default function RoundOverlay({ active, ns, onExit }: Props) {
  const [phase, setPhase] = useState<NurseCartPhase>("idle");
  const [ending, setEnding] = useState(false);

  // 활성 동안 단계 폴링(2s)
  useEffect(() => {
    if (!active) return;
    setPhase("idle"); setEnding(false);
    let alive = true;
    const tick = () => getNurseCartPhase().then((r) => { if (alive) setPhase(r.phase); }).catch(() => {});
    tick();
    const t = setInterval(tick, 2000);
    return () => { alive = false; clearInterval(t); };
  }, [active]);

  // 복귀 완료 → 잠시 후 닫기
  useEffect(() => {
    if (!active || phase !== "done") return;
    const t = setTimeout(() => onExit(), 3000);
    return () => clearTimeout(t);
  }, [active, phase, onExit]);

  const endRound = useCallback(async () => {
    setEnding(true);
    try { await nurseCartRoundDone(); } catch { /* 무시 — 로봇이 복귀 처리 */ }
    finally { setEnding(false); }
  }, []);

  if (!active) return null;

  const cur = STEP_LABELS.findIndex((s) => s.key === phase);

  return (
    <div className="fixed inset-0 z-50 bg-[#0b1f1d] text-white grid place-items-center overflow-auto p-8">
      <div className="text-center max-w-[760px]">
        <div className="text-[clamp(13px,1.6vw,18px)] text-white/50 mb-4">{ns.toUpperCase()} · 회진 (시나리오 B)</div>

        <div className="flex items-center justify-center gap-2 text-[12px] mb-6 flex-wrap">
          {STEP_LABELS.map((s, i) => (
            <span key={s.key} className="flex items-center gap-2">
              <span className={`px-3 py-1 rounded-full ${i <= cur ? "bg-teal text-white" : "bg-white/10 text-white/50"}`}>{s.short}</span>
              {i < STEP_LABELS.length - 1 && <span className="text-white/30">→</span>}
            </span>
          ))}
        </div>

        <div className="text-[clamp(30px,6vw,72px)] font-bold leading-tight">{PHASE_TEXT[phase]}</div>
        <div className="text-[clamp(13px,2vw,18px)] text-white/60 mt-4 leading-relaxed">{PHASE_SUB[phase]}</div>
      </div>

      {phase !== "done" && (
        <button
          onClick={endRound}
          disabled={ending}
          className="fixed bottom-8 right-8 px-7 py-4 rounded-2xl text-[18px] font-semibold bg-white text-[#0b1f1d] shadow-lg disabled:opacity-50"
        >
          {ending ? "종료 중…" : "회진 종료 · 복귀"}
        </button>
      )}
    </div>
  );
}
