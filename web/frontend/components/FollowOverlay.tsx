"use client";
import { useEffect, useRef, useState } from "react";
import { API_BASE } from "@/lib/api";
import { nearestArrival, type ArrivalTarget, type Pt } from "@/lib/follow";
import { returnHome } from "@/lib/followActions";

type Props = {
  active: boolean;
  ns: string;
  targets: ArrivalTarget[];
  dock: { x: number; y: number; yaw?: number };
  onExit: () => void;
};

export default function FollowOverlay({ active, ns, targets, dock, onExit }: Props) {
  const [pose, setPose] = useState<Pt | undefined>(undefined);
  const [isDocked, setIsDocked] = useState<boolean | undefined>(undefined);
  const [phase, setPhase] = useState<"following" | "returning">("following");
  const [arrivalLabel, setArrivalLabel] = useState<string | null>(null);
  const prevKey = useRef<string | null>(null);

  // active일 때만 SSE 자가 구독.
  // onopen 콜백에서 상태 초기화 → 비동기 컨텍스트이므로 set-state-in-effect 위반 없음.
  useEffect(() => {
    if (!active) return;
    const es = new EventSource(`${API_BASE}/api/stream`, { withCredentials: true });
    es.onopen = () => {
      setPhase("following");
      prevKey.current = null;
      setArrivalLabel(null);
    };
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

  // pose 갱신마다 근접판정(히스테리시스)
  useEffect(() => {
    if (phase !== "following") return;
    const a = nearestArrival(pose, targets, prevKey.current);
    prevKey.current = a ? a.key : null;
    setArrivalLabel(a ? a.label : null);
  }, [pose, targets, phase]);

  // 복귀 중 도킹 완료 → 종료
  useEffect(() => {
    if (phase === "returning" && isDocked === true) onExit();
  }, [phase, isDocked, onExit]);

  if (!active) return null;

  let text: string;
  if (phase === "returning") text = "복귀 중…";
  else if (!pose) text = "위치 수신 대기…";
  else if (arrivalLabel) text = `${arrivalLabel}에 도착`;
  else text = "회진 중 — 안내를 따라오세요";

  const onReturn = async () => {
    setPhase("returning");
    try { await returnHome(ns, dock); } catch { /* feedback로 추적 */ }
  };

  return (
    <div className="fixed inset-0 z-50 bg-[#0b1f1d] text-white grid place-items-center">
      <div className="text-center px-8">
        <div className="text-[clamp(40px,9vw,120px)] font-bold leading-tight">{text}</div>
        <div className="text-[clamp(14px,2vw,22px)] text-white/60 mt-4">
          {ns.toUpperCase()} · 회진 모드
        </div>
      </div>
      <button
        onClick={onReturn}
        disabled={phase === "returning"}
        className="fixed bottom-8 right-8 px-7 py-4 rounded-2xl text-[18px] font-semibold bg-white text-[#0b1f1d] shadow-lg disabled:opacity-50"
      >
        홈 위치로 복귀
      </button>
    </div>
  );
}
