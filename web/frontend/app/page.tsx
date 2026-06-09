"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { getAmrs, getTargets, type AmrSnapshot, type GotoTarget } from "@/lib/api";
import { PRIMARY_NS } from "@/lib/config";
import { startFollow } from "@/lib/followActions";
import { type ArrivalTarget } from "@/lib/follow";
import FollowOverlay from "@/components/FollowOverlay";

type Banner = {
  href: string; title: string; sub: string; tone: string; soft: string;
  icon: React.ReactNode; chip?: (s: { online: number; total: number }) => string | null;
};

const BANNERS: Banner[] = [
  { href: "/map", title: "실시간 관제", sub: "AMR 위치·모드·LiDAR 실시간", tone: "#0ca39a", soft: "#e3f4f2",
    icon: <MapGlyph />, chip: (s) => `AMR ${s.online}/${s.total} 연결` },
  { href: "/patients", title: "환자 정보", sub: "회진 보조 · 의사 1눈 파악", tone: "#2f74e0", soft: "#e7effb",
    icon: <PatientGlyph /> },
  { href: "/intake", title: "문진표", sub: "초진 종합 문진 작성·저장", tone: "#16a34a", soft: "#e4f6ea",
    icon: <FormGlyph /> },
  { href: "/debug", title: "디버그", sub: "PC1·PC2 Redis 종합 시각화", tone: "#b0814a", soft: "#f4ecdf",
    icon: <DebugGlyph /> },
];

export default function Home() {
  const [stat, setStat] = useState({ online: 0, total: 2 });
  const [confirming, setConfirming] = useState(false);
  const [followActive, setFollowActive] = useState(false);
  const [targets, setTargets] = useState<Record<string, GotoTarget>>({});

  useEffect(() => {
    const load = () =>
      getAmrs().then((a: Record<string, AmrSnapshot>) => {
        const vals = Object.values(a);
        const now = Date.now() / 1000;
        const online = vals.filter((s) => s && s.stamp && now - s.stamp < 5).length;
        setStat({ online, total: Math.max(vals.length, 2) });
      }).catch(() => {});
    load();
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    getTargets().then((r) => setTargets(r.targets || {})).catch(() => {});
  }, []);

  const arrivalTargets: ArrivalTarget[] = ["pharmacy", "t101_1", "t101_2"]
    .flatMap((k) => {
      const t = targets[k];
      return t ? [{ key: k, label: t.label, x: t.x, y: t.y }] : [];
    });
  const dock = targets["dock"]
    ? { x: targets.dock.x, y: targets.dock.y, yaw: targets.dock.yaw }
    : { x: -8, y: -6, yaw: 0 };

  async function confirmStart() {
    setConfirming(false);
    let docked = true;
    try {
      const a = await getAmrs();
      docked = a[PRIMARY_NS]?.dock?.is_docked ?? true;
    } catch { /* 기본 docked 가정 */ }
    setFollowActive(true);
    startFollow(PRIMARY_NS, docked).catch(() => {});
  }

  return (
    <div className="p-7 md:p-9 max-w-[1100px] mx-auto">
      {!confirming ? (
        <button
          onClick={() => setConfirming(true)}
          className="w-full rounded-2xl px-7 py-6 mb-6 text-left text-white shadow-md flex items-center justify-between"
          style={{ background: "linear-gradient(90deg,#0ca39a,#0b7d76)" }}
        >
          <div>
            <div className="text-[20px] font-bold">회진 모드 시작</div>
            <div className="text-[13px] text-white/80 mt-1">AMR이 앞의 대상을 따라 병동을 회진합니다</div>
          </div>
          <span className="text-[26px]">▶</span>
        </button>
      ) : (
        <div
          className="w-full rounded-2xl px-7 py-6 mb-6 text-white shadow-md flex items-center justify-between gap-4"
          style={{ background: "linear-gradient(90deg,#0ca39a,#0b7d76)" }}
        >
          <div className="text-[15px] font-semibold">회진 모드를 시작할까요? (도크 상태면 자동 undock)</div>
          <div className="flex gap-2 shrink-0">
            <button onClick={confirmStart} className="px-5 py-2.5 rounded-xl bg-white text-[#0b7d76] font-semibold">확인</button>
            <button onClick={() => setConfirming(false)} className="px-5 py-2.5 rounded-xl bg-white/20 font-semibold">취소</button>
          </div>
        </div>
      )}
      <FollowOverlay
        active={followActive}
        ns={PRIMARY_NS}
        targets={arrivalTargets}
        dock={dock}
        onExit={() => setFollowActive(false)}
      />
      <div className="eyebrow">병동 보조 로봇</div>
      <h1 className="text-[clamp(24px,4vw,34px)] font-bold mt-1.5">통합 관제 콘솔</h1>
      <p className="text-[14px] text-ink-2 mt-2">메뉴를 선택해 관제·환자·문진·디버그로 이동합니다.</p>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 md:gap-5 mt-7 rise">
        {BANNERS.map((b) => {
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
function DebugGlyph() {
  return (<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><rect x="4" y="9" width="16" height="10" rx="2" /><path d="M9 9V6a3 3 0 0 1 6 0v3M8 14h.01M12 14h.01M16 14h.01" /></svg>);
}
