"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  API_BASE, getAmrs, getRooms, getPatient,
  pushMission, verifyIdentify, setIntakeStatus,
} from "@/lib/api";
import { nearestArrival, type Pt } from "@/lib/follow";
import { returnHome, waitDockState } from "@/lib/followActions";
import QrScanner from "@/components/QrScanner";
import IntakeForm from "@/components/IntakeForm";

export type RoundStop = { key: string; label: string; room: string; x: number; y: number; yaw?: number };

type Props = {
  active: boolean;
  ns: string;
  stops: RoundStop[];
  dock: { x: number; y: number; yaw?: number };
  onExit: () => void;
};

type Phase = "starting" | "moving" | "scanning" | "intake" | "absent" | "returning" | "summary";
type Outcome = { room: string; label: string; name: string; status: "done" | "absent" };

const SCAN_SECONDS = 30;
const ABSENT_SECONDS = 5;

export default function RoundsIntakeOverlay({ active, ns, stops, dock, onExit }: Props) {
  const [phase, setPhase] = useState<Phase>("starting");
  const [idx, setIdx] = useState(0);
  const [assigned, setAssigned] = useState<{ pid: string; name: string }>({ pid: "", name: "" });
  const [scanPid, setScanPid] = useState("");      // 매치되어 문진할 환자
  const [warn, setWarn] = useState("");            // 불일치/미등록 인라인
  const [secs, setSecs] = useState(SCAN_SECONDS);
  const [results, setResults] = useState<Outcome[]>([]);
  const [pose, setPose] = useState<Pt | undefined>();
  const [docked, setDocked] = useState<boolean | undefined>();

  const stop = stops[idx];
  const gotoFired = useRef<number>(-1);
  const advancedRef = useRef(false);
  const resetNonce = useRef(0);

  // ── SSE: pose + dock ──────────────────────────────────────────────
  useEffect(() => {
    if (!active) return;
    const es = new EventSource(`${API_BASE}/api/stream`, { withCredentials: true });
    es.onmessage = (e) => {
      try {
        const d = JSON.parse(e.data);
        if (d?.source !== ns) return;
        if (d.pose) setPose({ x: d.pose.x, y: d.pose.y });
        if (d.dock) setDocked(d.dock.is_docked);
      } catch { /* ignore */ }
    };
    return () => es.close();
  }, [active, ns]);

  // ── 시작: (도크면) undock → 첫 호실 이동 ───────────────────────────
  useEffect(() => {
    if (!active) return;
    setPhase("starting"); setIdx(0); setResults([]); setWarn(""); gotoFired.current = -1;
    let cancelled = false;
    (async () => {
      try {
        const a = await getAmrs();
        const isDocked = a[ns]?.dock?.is_docked ?? false;
        if (isDocked) { await pushMission(ns, "undock"); await waitDockState(ns, false, 20000); }
      } catch { /* 무시하고 진행 */ }
      if (!cancelled) setPhase("moving");
    })();
    return () => { cancelled = true; };
  }, [active, ns]);

  // ── moving: goto 1회 발행 + 배정환자 이름 로드 ─────────────────────
  useEffect(() => {
    if (!active || phase !== "moving" || !stop) return;
    setWarn("");
    if (gotoFired.current !== idx) {
      gotoFired.current = idx;
      pushMission(ns, "goto", { x: stop.x, y: stop.y, yaw: stop.yaw ?? 0 }).catch(() => {});
      (async () => {
        try {
          const rooms = await getRooms();
          const apid = (rooms[stop.room] as { patient?: string } | undefined)?.patient ?? "";
          const ap = apid ? await getPatient(apid).catch(() => null) : null;
          setAssigned({ pid: apid, name: ap?.성명 ?? "" });
        } catch { setAssigned({ pid: "", name: "" }); }
      })();
    }
  }, [active, phase, idx, stop, ns]);

  // ── moving: pose 근접 → 도착 시 scanning ──────────────────────────
  useEffect(() => {
    if (phase !== "moving" || !stop) return;
    const a = nearestArrival(pose, [{ key: stop.key, label: stop.label, x: stop.x, y: stop.y }], null);
    if (a) beginScan();
  }, [phase, pose, stop]); // eslint-disable-line react-hooks/exhaustive-deps

  const beginScan = useCallback(() => {
    setWarn(""); setScanPid(""); setSecs(SCAN_SECONDS);
    resetNonce.current += 1;
    setPhase("scanning");
  }, []);

  // ── 카운트다운 (scanning 30s / absent 5s) ─────────────────────────
  useEffect(() => {
    if (phase !== "scanning" && phase !== "absent") return;
    const nonce = resetNonce.current;
    const t = setInterval(() => {
      setSecs((s) => {
        if (resetNonce.current !== nonce) return s;
        if (s <= 1) {
          clearInterval(t);
          if (phase === "scanning") onScanTimeout();
          else advance();
          return 0;
        }
        return s - 1;
      });
    }, 1000);
    return () => clearInterval(t);
  }, [phase, idx]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── 스캔 결과 처리 ────────────────────────────────────────────────
  const onScan = useCallback(async (pid: string) => {
    if (phase !== "scanning") return;
    try {
      const v = await verifyIdentify(pid, stop?.room);
      if (v.status === "identified" || v.status === "ok_no_room") {
        setScanPid(pid); setPhase("intake");
      } else if (v.status === "mismatch") {
        setWarn(`이 병상 환자가 아닙니다 (이 병상: ${v.assigned_name || assigned.name}님)`);
        setSecs(SCAN_SECONDS); resetNonce.current += 1;   // 타이머 리셋
      } else {
        setWarn("등록되지 않은 환자입니다");
        setSecs(SCAN_SECONDS); resetNonce.current += 1;   // 타이머 리셋
      }
    } catch { setWarn("검증 실패 — 다시 시도"); }
  }, [phase, stop, assigned.name]);

  function record(status: "done" | "absent", pid: string) {
    if (pid) setIntakeStatus(pid, status).catch(() => {});
    setResults((r) => [...r, { room: stop?.room ?? "", label: stop?.label ?? "", name: assigned.name, status }]);
  }

  function onScanTimeout() { record("absent", assigned.pid); setSecs(ABSENT_SECONDS); resetNonce.current += 1; setPhase("absent"); }
  function onAbsentBtn() { record("absent", assigned.pid); setSecs(ABSENT_SECONDS); resetNonce.current += 1; setPhase("absent"); }
  function onIntakeSaved() { record("done", scanPid); advance(); }
  function onIntakeSkip() { record("absent", assigned.pid); advance(); }

  const advance = useCallback(() => {
    if (advancedRef.current) return;
    advancedRef.current = true;
    setTimeout(() => { advancedRef.current = false; }, 300);
    if (idx + 1 < stops.length) { setIdx(idx + 1); setPhase("moving"); }
    else setPhase("returning");
  }, [idx, stops.length]);

  // ── returning: dock 복귀 → 완료 시 summary ────────────────────────
  useEffect(() => {
    if (phase !== "returning") return;
    returnHome(ns, dock).catch(() => {});
  }, [phase, ns, dock]);
  useEffect(() => {
    if (phase === "returning" && docked === true) setPhase("summary");
  }, [phase, docked]);

  if (!active) return null;

  const doneN = results.filter((r) => r.status === "done").length;
  const absentN = results.filter((r) => r.status === "absent").length;

  return (
    <div className="fixed inset-0 z-50 bg-[#0b1f1d] text-white grid place-items-center overflow-auto py-8">
      {/* ── 시작/이동/복귀 메시지 ── */}
      {(phase === "starting" || phase === "moving" || phase === "returning") && (
        <Center sub={`${ns.toUpperCase()} · 순회 문진`}>
          {phase === "starting" && "순회 문진을 가동합니다"}
          {phase === "moving" && (assigned.name ? `${assigned.name}님께 이동 중` : `${stop?.label ?? ""} 이동 중`)}
          {phase === "returning" && "순회 완료 — 복귀·도킹 중"}
          {phase === "moving" && (
            <button onClick={beginScan}
              className="mt-8 mx-auto block px-6 py-3 rounded-xl text-[15px] bg-white/15 hover:bg-white/25 font-semibold">
              도착했어요 — 스캔 시작
            </button>
          )}
        </Center>
      )}

      {/* ── 스캔(30초) ── */}
      {phase === "scanning" && (
        <div className="w-full max-w-[560px] px-6 text-center">
          <div className="text-[clamp(26px,5vw,46px)] font-bold leading-tight">
            {assigned.name ? `${assigned.name}님,` : ""}<br />QR 코드를 인식해주세요
          </div>
          <div className="text-white/60 mt-2">{stop?.label} · 남은 시간 {secs}s</div>
          <div className="mt-5"><QrScanner active onScan={onScan} /></div>
          {warn && <div className="mt-4 rounded-xl bg-red-500/20 border border-red-400/40 px-4 py-3 text-red-100 font-semibold">⚠ {warn}</div>}
          <button onClick={onAbsentBtn}
            className="mt-6 px-6 py-3 rounded-xl bg-white/15 hover:bg-white/25 font-semibold text-[15px]">
            부재중입니다 — 건너뛰기
          </button>
        </div>
      )}

      {/* ── 문진표 ── */}
      {phase === "intake" && (
        <IntakeForm key={scanPid} pid={scanPid} patientName={assigned.name} onSaved={onIntakeSaved} onCancel={onIntakeSkip} />
      )}

      {/* ── 부재중 처리(5초) ── */}
      {phase === "absent" && (
        <Center sub={`${stop?.label ?? ""}`}>
          부재중 처리합니다<br />
          <span className="text-[0.5em] text-white/60">{secs}초 후 다음 병상으로 이동</span>
        </Center>
      )}

      {/* ── 요약 ── */}
      {phase === "summary" && (
        <div className="w-full max-w-[520px] px-6 text-center">
          <div className="text-[clamp(28px,6vw,52px)] font-bold">순회 문진 완료</div>
          <div className="flex justify-center gap-8 mt-6 text-[20px]">
            <span className="text-green-300 font-bold">문진 완료 {doneN}</span>
            <span className="text-amber-300 font-bold">부재중 {absentN}</span>
          </div>
          <div className="mt-6 flex flex-col gap-2 text-left">
            {results.map((r, i) => (
              <div key={i} className="flex items-center justify-between rounded-xl bg-white/10 px-4 py-2.5">
                <span>{r.label} · {r.name || "-"}</span>
                <span className={r.status === "done" ? "text-green-300 font-semibold" : "text-amber-300 font-semibold"}>
                  {r.status === "done" ? "문진 완료" : "부재중"}
                </span>
              </div>
            ))}
          </div>
          <button onClick={onExit} className="mt-8 px-8 py-4 rounded-2xl bg-white text-[#0b1f1d] font-bold text-[17px]">
            확인
          </button>
        </div>
      )}
    </div>
  );
}

function Center({ children, sub }: { children: React.ReactNode; sub: string }) {
  return (
    <div className="text-center px-8">
      <div className="text-[clamp(32px,7vw,84px)] font-bold leading-tight">{children}</div>
      <div className="text-[clamp(13px,1.6vw,18px)] text-white/50 mt-5">{sub}</div>
    </div>
  );
}
