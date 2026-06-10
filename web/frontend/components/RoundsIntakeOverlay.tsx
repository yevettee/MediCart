"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  getRooms, getPatient, pushMission, verifyIdentify, setIntakeStatus,
  getPatrolPhase, sendPatrolAdvance,
} from "@/lib/api";
import QrScanner from "@/components/QrScanner";
import IntakeForm from "@/components/IntakeForm";

export type RoundStop = { key: string; label: string; room: string; x: number; y: number; yaw?: number };

type Props = {
  active: boolean;
  ns: string;
  stops: RoundStop[];
  dock: { x: number; y: number; yaw?: number; dock_after?: boolean };
  onExit: () => void;
};

type Phase = "starting" | "moving" | "scanning" | "intake" | "absent" | "noassign" | "returning" | "summary";
type Outcome = { room: string; label: string; name: string; status: "done" | "absent" | "none" };

const SCAN_SECONDS = 30;
const ABSENT_SECONDS = 5;
const POLL_MS = 1000;

export default function RoundsIntakeOverlay({ active, ns, stops, dock, onExit }: Props) {
  const [phase, setPhase] = useState<Phase>("starting");
  const [idx, setIdx] = useState(0);
  const [assigned, setAssigned] = useState<{ pid: string; name: string }>({ pid: "", name: "" });
  const [scanPid, setScanPid] = useState("");      // 매치되어 문진할 환자
  const [warn, setWarn] = useState("");            // 불일치/미등록 인라인
  const [secs, setSecs] = useState(SCAN_SECONDS);
  const [results, setResults] = useState<Outcome[]>([]);

  const stop = stops[idx];
  const phaseRef = useRef<Phase>(phase);           // 폴링 콜백에서 최신 phase 참조
  const lastArrivedRef = useRef<number>(-1);       // 처리한 도착 idx(중복 방지)
  const resetNonce = useRef(0);
  const advancingRef = useRef(false);

  useEffect(() => { phaseRef.current = phase; }, [phase]);

  // ── 시작: patrol_intake_mission 한 건 발행(로봇이 undock→순회 자율 수행) ──────
  //   기존엔 브라우저가 undock+병상별 goto 를 하나씩 발행했으나(스텝마다 Firebase 왕복),
  //   이제 시퀀서가 한 번에 받아 병상 사이 이동을 로봇 내부에서 처리한다.
  useEffect(() => {
    if (!active) return;
    setPhase("starting"); setIdx(0); setResults([]); setWarn("");
    lastArrivedRef.current = -1; advancingRef.current = false;
    let cancelled = false;
    (async () => {
      try {
        const stopsPayload = stops.map((s) => ({
          x: s.x, y: s.y, yaw: s.yaw ?? 0, room: s.room, label: s.label,
        }));
        await pushMission(ns, "patrol_intake_mission", { stops: stopsPayload, home: dock });
      } catch { /* 무시하고 진행 — 로봇 미연결 시 수동 버튼 폴백 */ }
      if (!cancelled) setPhase("moving");
    })();
    return () => { cancelled = true; };
  }, [active, ns]); // eslint-disable-line react-hooks/exhaustive-deps

  const beginScan = useCallback(() => {
    setWarn(""); setScanPid(""); setSecs(SCAN_SECONDS);
    resetNonce.current += 1;
    advancingRef.current = false;
    setPhase("scanning");
  }, []);

  // ── 도착 처리: 배정환자 로드 후 스캔 시작 ─────────────────────────────
  const arriveAt = useCallback((i: number) => {
    if (i < 0 || i >= stops.length) return;
    lastArrivedRef.current = i;
    setIdx(i);
    setWarn(""); setScanPid("");
    const room = stops[i].room;
    (async () => {
      let apid = "", name = "";
      try {
        // /api/rooms 응답은 { rooms: {...} } 형태 — MapView 와 동일하게 .rooms 로 접근.
        const resp = await getRooms();
        const roomsMap = (resp?.rooms as Record<string, { patient?: string }> | undefined) ?? {};
        apid = roomsMap[room]?.patient ?? "";
        if (apid) { const ap = await getPatient(apid).catch(() => null); name = ap?.성명 ?? ""; }
      } catch { apid = ""; name = ""; }
      setAssigned({ pid: apid, name });
      if (apid) beginScan();           // 배정환자 있음 → QR 스캔
      else setPhase("noassign");       // 배정환자 없음 → 안내 후 자동 다음
    })();
  }, [stops, beginScan]);

  // ── 폴링: RTDB patrol/phase 로 도착·완료 감지 ─────────────────────────
  useEffect(() => {
    if (!active) return;
    const poll = async () => {
      try {
        const p = await getPatrolPhase(ns);
        if (phaseRef.current === "returning") {
          if (p.phase === "idle") setPhase("summary");
          return;
        }
        if (
          p.phase === "arrived" && typeof p.stop?.idx === "number" &&
          p.stop.idx !== lastArrivedRef.current &&
          (phaseRef.current === "moving" || phaseRef.current === "starting")
        ) {
          arriveAt(p.stop.idx);
        }
      } catch { /* 폴링 실패 무시 */ }
    };
    const t = setInterval(poll, POLL_MS);
    return () => clearInterval(t);
  }, [active, arriveAt]);

  // ── 카운트다운 (scanning 30s / absent 5s) ─────────────────────────────
  useEffect(() => {
    if (phase !== "scanning" && phase !== "absent") return;
    const nonce = resetNonce.current;
    const t = setInterval(() => {
      setSecs((s) => {
        if (resetNonce.current !== nonce) return s;
        if (s <= 1) {
          clearInterval(t);
          if (phase === "scanning") onScanTimeout();
          else finishStop();
          return 0;
        }
        return s - 1;
      });
    }, 1000);
    return () => clearInterval(t);
  }, [phase, idx]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── 스캔 결과 처리 ────────────────────────────────────────────────────
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

  function record(status: "done" | "absent" | "none", pid: string) {
    if (pid && status !== "none") setIntakeStatus(pid, status).catch(() => {});
    setResults((r) => [...r, { room: stop?.room ?? "", label: stop?.label ?? "", name: assigned.name, status }]);
  }

  function onScanTimeout() { record("absent", assigned.pid); setSecs(ABSENT_SECONDS); resetNonce.current += 1; setPhase("absent"); }
  function onAbsentBtn() { record("absent", assigned.pid); setSecs(ABSENT_SECONDS); resetNonce.current += 1; setPhase("absent"); }
  function onIntakeSaved() { record("done", scanPid); finishStop(); }
  function onIntakeSkip() { record("absent", assigned.pid); finishStop(); }

  // ── 정차 종료: intake_done 신호 → 로봇이 다음 병상(또는 복귀)으로 진행 ──
  const finishStop = useCallback(() => {
    if (advancingRef.current) return;
    advancingRef.current = true;
    sendPatrolAdvance(ns).catch(() => {});
    if (lastArrivedRef.current + 1 >= stops.length) setPhase("returning");
    else setPhase("moving");          // 다음 도착 신호 대기
  }, [stops.length]);

  // ── 배정환자 없음: 잠시 안내 후 자동으로 다음 병상(또는 복귀) ──────────
  useEffect(() => {
    if (phase !== "noassign") return;
    const t = setTimeout(() => { record("none", ""); finishStop(); }, 2500);
    return () => clearTimeout(t);
  }, [phase]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── 로봇 미연결 폴백: 수동으로 다음 병상 도착 처리 ───────────────────
  const manualArrive = useCallback(() => {
    const next = lastArrivedRef.current + 1;   // 최초 -1 → 0
    if (next < stops.length) arriveAt(next);
  }, [arriveAt, stops.length]);

  if (!active) return null;

  const doneN = results.filter((r) => r.status === "done").length;
  const absentN = results.filter((r) => r.status === "absent").length;
  const noneN = results.filter((r) => r.status === "none").length;

  return (
    <div className="fixed inset-0 z-50 bg-[#0b1f1d] text-white grid place-items-center overflow-auto py-8">
      {/* ── 시작/이동/복귀 메시지 ── */}
      {(phase === "starting" || phase === "moving" || phase === "returning") && (
        <Center sub={`${ns.toUpperCase()} · 순회 문진`}>
          {phase === "starting" && "순회 문진을 가동합니다"}
          {phase === "moving" && (assigned.name ? `${assigned.name}님께 이동 중` : `${stop?.label ?? ""} 이동 중`)}
          {phase === "returning" && "순회 완료 — 복귀·도킹 중"}
          {phase === "moving" && (
            <button onClick={manualArrive}
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

      {/* ── 배정환자 없음 → 자동 다음 ── */}
      {phase === "noassign" && (
        <Center sub={`${stop?.label ?? ""}`}>
          배정 환자가 없습니다<br />
          <span className="text-[0.5em] text-white/60">다음 병상으로 이동합니다</span>
        </Center>
      )}

      {/* ── 요약 ── */}
      {phase === "summary" && (
        <div className="w-full max-w-[520px] px-6 text-center">
          <div className="text-[clamp(28px,6vw,52px)] font-bold">순회 문진 완료</div>
          <div className="flex justify-center gap-8 mt-6 text-[20px]">
            <span className="text-green-300 font-bold">문진 완료 {doneN}</span>
            <span className="text-amber-300 font-bold">부재중 {absentN}</span>
            {noneN > 0 && <span className="text-white/50 font-bold">미배정 {noneN}</span>}
          </div>
          <div className="mt-6 flex flex-col gap-2 text-left">
            {results.map((r, i) => (
              <div key={i} className="flex items-center justify-between rounded-xl bg-white/10 px-4 py-2.5">
                <span>{r.label} · {r.name || "-"}</span>
                <span className={r.status === "done" ? "text-green-300 font-semibold" : r.status === "absent" ? "text-amber-300 font-semibold" : "text-white/50 font-semibold"}>
                  {r.status === "done" ? "문진 완료" : r.status === "absent" ? "부재중" : "배정 환자 없음"}
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
