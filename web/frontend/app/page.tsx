"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { getAmrs, getTargets, getMe, startRound, type AmrSnapshot, type GotoTarget } from "@/lib/api";
import { isLive, robotHome } from "@/lib/telemetry";
import { roleAtLeast, type Role } from "@/lib/auth";
import { NURSE_CART_NS, PATROL_NS } from "@/lib/config";
import RoundOverlay from "@/components/RoundOverlay";
import RoundsIntakeOverlay, { type RoundStop } from "@/components/RoundsIntakeOverlay";

// 순회 문진 정차 매핑: 회진 타겟(정확 좌표) ↔ /rooms 키(배정환자).
const ROUND_MAP = [
  { targetKey: "t101_1", room: "101-A", label: "101호 1번" },
  { targetKey: "t101_2", room: "101-B", label: "101호 2번" },
];

type Banner = {
  href: string; title: string; sub: string; tone: string; soft: string; minRole: Role;
  icon: React.ReactNode; chip?: (s: { online: number; total: number }) => string | null;
};

const BANNERS: Banner[] = [
  { href: "/console", title: "실시간 관제", sub: "AMR 위치·모드·LiDAR 실시간", tone: "#0ca39a", soft: "#e3f4f2",
    minRole: "admin", icon: <MapGlyph />, chip: (s) => `AMR ${s.online}/${s.total} 연결` },
  { href: "/patients", title: "환자 정보", sub: "회진 보조 · 의사 1눈 파악", tone: "#2f74e0", soft: "#e7effb",
    minRole: "staff", icon: <PatientGlyph /> },
  { href: "/intake", title: "문진표", sub: "초진 종합 문진 작성·저장", tone: "#16a34a", soft: "#e4f6ea",
    minRole: "patient", icon: <FormGlyph /> },
];

export default function Home() {
  const [stat, setStat] = useState({ online: 0, total: 2 });
  const [targets, setTargets] = useState<Record<string, GotoTarget>>({});
  const [amrs, setAmrs] = useState<Record<string, AmrSnapshot>>({});
  const [role, setRole] = useState<Role>("patient");
  const [roundConfirm, setRoundConfirm] = useState(false);
  const [roundActive, setRoundActive] = useState(false);
  const [roundMsg, setRoundMsg] = useState<string | null>(null);
  const [roundsConfirm, setRoundsConfirm] = useState(false);
  const [roundsActive, setRoundsActive] = useState(false);

  useEffect(() => {
    getMe().then((m) => setRole(m.role)).catch(() => setRole("patient"));
  }, []);

  useEffect(() => {
    const load = () =>
      getAmrs().then((a: Record<string, AmrSnapshot>) => {
        setAmrs(a);
        const vals = Object.values(a);
        const online = vals.filter((s) => isLive(s?.stamp, 5000)).length;
        setStat({ online, total: Math.max(vals.length, 2) });
      }).catch(() => {});
    load();
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    getTargets().then((r) => setTargets(r.targets || {})).catch(() => {});
  }, []);

  // 순회 문진(robot3) 복귀 홈: 도킹 중인 robot3 의 실제 pose(=amcl_pose)를 우선 사용.
  // 미도킹/미수신이면 targets.dock → 기본값 순으로 폴백.
  const dock =
    robotHome(amrs[PATROL_NS]) ??
    (targets["dock"]
      ? { x: targets.dock.x, y: targets.dock.y, yaw: targets.dock.yaw }
      : { x: -8, y: -6, yaw: 0 });

  // 순회 문진 정차 리스트 — 타겟 좌표 + /rooms 키(배정환자).
  const roundStops: RoundStop[] = ROUND_MAP.flatMap((m) => {
    const t = targets[m.targetKey];
    return t ? [{ key: m.targetKey, label: m.label, room: m.room, x: t.x, y: t.y, yaw: t.yaw }] : [];
  });

  // 간호사 투약(시나리오 B, robot6 전담): nurse_cart_mission 발행 후 단계 인식 오버레이.
  async function startRoundFlow() {
    setRoundConfirm(false); setRoundMsg(null);
    try {
      await startRound(NURSE_CART_NS);
      setRoundActive(true);
    } catch {
      setRoundMsg("간호사 투약 시작 실패 — 권한(의료진)·연결 확인");
    }
  }

  // 비로그인(환자) — 환자 패널(문진 안내·시작). 회진/관제/디버그 미노출.
  if (role === "patient") return <PatientPanel />;

  return (
    <div className="p-7 md:p-9 max-w-[1100px] mx-auto">
      {/* 회진 시작 (시나리오 B) — 약품실 OCR → 간호사 추종 → 복귀·도킹. staff+ */}
      {roleAtLeast(role, "staff") && !roundConfirm ? (
        <button
          onClick={() => { setRoundConfirm(true); setRoundMsg(null); }}
          className="w-full rounded-2xl px-7 py-6 mb-6 text-left text-white shadow-md flex items-center justify-between"
          style={{ background: "linear-gradient(90deg,#0ca39a,#0b7d76)" }}
        >
          <div>
            <div className="text-[20px] font-bold">간호사 투약</div>
            <div className="text-[13px] text-white/80 mt-1">
              {roundMsg ?? "robot6 · 약품실 이동 → 약품 OCR → 간호사 추종 → 홈 복귀·도킹 (시나리오 B)"}
            </div>
          </div>
          <span className="text-[26px]">▶</span>
        </button>
      ) : roleAtLeast(role, "staff") && roundConfirm ? (
        <div
          className="w-full rounded-2xl px-7 py-6 mb-6 text-white shadow-md flex items-center justify-between gap-4"
          style={{ background: "linear-gradient(90deg,#0ca39a,#0b7d76)" }}
        >
          <div className="text-[15px] font-semibold">간호사 투약을 시작할까요? (robot6 — 약품실 이동 → OCR → 추종 → 복귀·도킹)</div>
          <div className="flex gap-2 shrink-0">
            <button onClick={startRoundFlow} className="px-5 py-2.5 rounded-xl bg-white text-[#0b7d76] font-semibold">확인</button>
            <button onClick={() => setRoundConfirm(false)} className="px-5 py-2.5 rounded-xl bg-white/20 font-semibold">취소</button>
          </div>
        </div>
      ) : null}
      <RoundOverlay active={roundActive} ns={NURSE_CART_NS} onExit={() => setRoundActive(false)} />

      {/* 순회 문진 (로봇 자율 순회 + QR 배정환자 검증 + 문진/부재중) — 회진과 별개 시나리오. staff+ */}
      {roleAtLeast(role, "staff") && (!roundsConfirm ? (
        <button
          onClick={() => setRoundsConfirm(true)}
          className="w-full rounded-2xl px-7 py-6 mb-6 text-left text-white shadow-md flex items-center justify-between"
          style={{ background: "linear-gradient(90deg,#6d5ae0,#4b3bbd)" }}
        >
          <div>
            <div className="text-[20px] font-bold">순회 문진 시작</div>
            <div className="text-[13px] text-white/80 mt-1">robot3 · 101호 1·2번을 순회하며 환자 QR 인식 후 문진을 진행합니다</div>
          </div>
          <span className="text-[26px]">▶</span>
        </button>
      ) : (
        <div
          className="w-full rounded-2xl px-7 py-6 mb-6 text-white shadow-md flex items-center justify-between gap-4"
          style={{ background: "linear-gradient(90deg,#6d5ae0,#4b3bbd)" }}
        >
          <div className="text-[15px] font-semibold">순회 문진을 시작할까요? (101호 1·2번 순회 후 복귀·도킹)</div>
          <div className="flex gap-2 shrink-0">
            <button onClick={() => { setRoundsConfirm(false); setRoundsActive(true); }}
              className="px-5 py-2.5 rounded-xl bg-white text-[#4b3bbd] font-semibold">확인</button>
            <button onClick={() => setRoundsConfirm(false)}
              className="px-5 py-2.5 rounded-xl bg-white/20 font-semibold">취소</button>
          </div>
        </div>
      ))}
      <RoundsIntakeOverlay
        active={roundsActive}
        ns={PATROL_NS}
        stops={roundStops}
        dock={dock}
        onExit={() => { setRoundsActive(false); setRoundsConfirm(false); }}
      />

      <div className="eyebrow">병동 보조 로봇</div>
      <h1 className="text-[clamp(24px,4vw,34px)] font-bold mt-1.5">통합 관제 콘솔</h1>
      <p className="text-[14px] text-ink-2 mt-2">메뉴를 선택해 관제·환자·문진·디버그로 이동합니다.</p>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 md:gap-5 mt-7 rise">
        {BANNERS.filter((b) => roleAtLeast(role, b.minRole)).map((b) => {
          const chip = b.chip?.(stat);
          return (
            <Link key={b.href} href={b.href}
              className="card card-hover p-6 md:p-7 flex flex-col gap-4 min-h-[180px] group relative overflow-hidden">
              <span className="absolute -right-6 -top-6 w-28 h-28 rounded-full opacity-60 transition-transform group-hover:scale-110"
                style={{ background: b.soft }} />
              <div className="relative flex items-start justify-between">
                <span className="grid place-items-center w-14 h-14 rounded-2xl text-white shadow-sm"
                  style={{ background: b.tone }}>{b.icon}</span>
                {chip && (
                  <span className="pill" style={{ background: b.soft, color: b.tone }}>
                    <span className="dot" style={{ background: b.tone }} /> {chip}
                  </span>
                )}
              </div>
              <div className="relative mt-auto">
                <div className="text-[20px] font-bold">{b.title}</div>
                <div className="text-[13px] text-ink-2 mt-1">{b.sub}</div>
              </div>
              <span className="relative text-[13px] font-semibold flex items-center gap-1" style={{ color: b.tone }}>
                이동 <Arrow />
              </span>
            </Link>
          );
        })}
      </div>
    </div>
  );
}

function PatientPanel() {
  return (
    <div className="p-7 md:p-9 max-w-[680px] mx-auto">
      <div className="card p-8 md:p-10 flex flex-col items-center text-center gap-5 rise">
        <span className="grid place-items-center w-16 h-16 rounded-2xl text-white shadow-sm" style={{ background: "#16a34a" }}>
          <FormGlyph />
        </span>
        <div>
          <div className="eyebrow">환자 자가 문진</div>
          <h1 className="text-[clamp(22px,4vw,30px)] font-bold mt-1.5">안녕하세요, 문진을 시작해 주세요</h1>
          <p className="text-[14px] text-ink-2 mt-2.5 leading-relaxed">
            진료 전 간단한 문진표를 작성하면 의료진이 더 빠르고 정확하게 도와드릴 수 있어요.<br />
            아래 버튼을 눌러 문진을 시작하세요.
          </p>
        </div>
        <Link href="/intake"
          className="mt-1 inline-flex items-center gap-2 rounded-2xl px-7 py-3.5 text-white font-semibold shadow-md group"
          style={{ background: "linear-gradient(90deg,#16a34a,#15803d)" }}>
          문진 시작 <Arrow />
        </Link>
        <p className="text-[12px] text-ink-3 mt-1">의료진이신가요? 좌측 메뉴에서 로그인하세요.</p>
      </div>
    </div>
  );
}

function Arrow() {
  return (<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"
    className="transition-transform group-hover:translate-x-1"><path d="M5 12h14M13 6l6 6-6 6" /></svg>);
}
function MapGlyph() {
  return (<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="1.8" strokeLinejoin="round" strokeLinecap="round"><path d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2Z" /><path d="M9 4v14M15 6v14" /></svg>);
}
function PatientGlyph() {
  return (<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="8" r="3.4" /><path d="M5 20c0-3.6 3.1-6 7-6s7 2.4 7 6" /></svg>);
}
function FormGlyph() {
  return (<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><rect x="5" y="3" width="14" height="18" rx="2.4" /><path d="M9 8h6M9 12h6M9 16h3" /></svg>);
}
