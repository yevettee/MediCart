"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { getMe, logout } from "@/lib/api";
import { NAV_ROLES, roleAtLeast, ROLE_LABEL, landingFor, type Role } from "@/lib/auth";

const NAV = [
  { href: "/", label: "홈", sub: "메뉴", icon: HomeIcon, exact: true },
  { href: "/console", label: "관리자 콘솔", sub: "관제·제어·지도·디버그", icon: MapIcon },
  { href: "/patients", label: "환자 정보", sub: "회진 보조", icon: PatientIcon },
  { href: "/intake", label: "문진표", sub: "작성·저장", icon: FormIcon },
  { href: "/ocr", label: "처치실", sub: "투약 준비·검증", icon: FormIcon },
  { href: "/cs-logs", label: "CS 상담 로그", sub: "챗봇 대화 기록", icon: ChatIcon },
  { href: "/qr", label: "QR 스캔", sub: "환자 문진표 호출", icon: QrIcon },
];

export default function Sidebar({
  collapsed, mobileOpen, onCloseMobile, onToggleCollapse,
}: {
  collapsed: boolean; mobileOpen: boolean;
  onCloseMobile: () => void; onToggleCollapse: () => void;
}) {
  const path = usePathname();
  const [role, setRole] = useState<Role>("patient");
  useEffect(() => { getMe().then((m) => setRole(m.role)).catch(() => setRole("patient")); }, [path]);
  const visibleNav = NAV.filter(({ href }) => roleAtLeast(role, NAV_ROLES[href] ?? "admin"));
  return (
    <aside
      className={[
        "z-40 h-screen bg-surface border-r border-line flex flex-col shrink-0",
        "transition-[width,transform] duration-200 ease-out",
        // 데스크톱/태블릿: 인-플로우 sticky, 폭 토글
        "md:sticky md:top-0 md:translate-x-0",
        collapsed ? "md:w-[68px]" : "md:w-[248px]",
        // 좁은 폭: 고정 드로어
        "fixed top-0 left-0 w-[248px]",
        mobileOpen ? "translate-x-0 shadow-2xl" : "-translate-x-full",
      ].join(" ")}
    >
      {/* 브랜드 + 토글 */}
      <div className="px-4 pt-5 pb-4 border-b border-line flex items-center justify-between gap-2">
        <Link href="/" onClick={onCloseMobile} className="flex items-center gap-3 min-w-0">
          <div className="relative w-9 h-9 rounded-xl bg-teal grid place-items-center shadow-[0_4px_14px_-4px_rgba(12,163,154,.6)] shrink-0">
            <CrossIcon />
            <span className="absolute -right-0.5 -top-0.5 w-2.5 h-2.5 rounded-full bg-green border-2 border-surface live-dot" />
          </div>
          {!collapsed && (
            <div className="leading-tight min-w-0">
              <div className="font-bold text-[15px] text-ink truncate">병동 관제</div>
              <div className="text-[11px] text-ink-3 tracking-wide truncate">WARD ASSIST ROBOT</div>
            </div>
          )}
        </Link>
        {/* 접기 토글 (md+) */}
        <button onClick={onToggleCollapse} aria-label="사이드바 토글"
          className="hidden md:grid place-items-center w-7 h-7 rounded-lg text-ink-3 hover:bg-surface-2 hover:text-teal shrink-0">
          <ChevronIcon dir={collapsed ? "right" : "left"} />
        </button>
      </div>

      {/* 네비 */}
      <nav className="flex-1 px-2.5 py-4 flex flex-col gap-1 overflow-y-auto">
        {visibleNav.map(({ href, label, sub, icon: Icon, exact }) => {
          const active = exact ? path === href : path === href || path.startsWith(href + "/");
          return (
            <Link key={href} href={href} onClick={onCloseMobile} title={collapsed ? label : undefined}
              className={`group flex items-center gap-3 rounded-xl px-2.5 py-2.5 transition-colors ${
                active ? "bg-teal-soft" : "hover:bg-surface-2"
              } ${collapsed ? "md:justify-center" : ""}`}>
              <span className={`grid place-items-center w-8 h-8 rounded-lg shrink-0 transition-colors ${
                active ? "bg-teal text-white" : "bg-surface-2 text-ink-2 group-hover:text-teal border border-line"
              }`}>
                <Icon />
              </span>
              {!collapsed && (
                <span className="leading-tight min-w-0">
                  <span className={`block text-[13.5px] font-semibold truncate ${active ? "text-teal-600" : "text-ink"}`}>{label}</span>
                  <span className="block text-[11px] text-ink-3 truncate">{sub}</span>
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      <div className="px-3 py-3 border-t border-line">
        <div className={`flex items-center gap-2 ${collapsed ? "md:justify-center" : ""}`}>
          <span className={`w-2.5 h-2.5 rounded-full shrink-0 ${
            role === "admin" ? "bg-red" : role === "staff" ? "bg-teal" : "bg-ink-3"}`} />
          {!collapsed && (
            <div className="min-w-0 flex-1">
              <div className="text-[12.5px] font-bold text-ink leading-tight">{ROLE_LABEL[role]}</div>
              <div className="text-[10.5px] text-ink-3 truncate">
                {role === "patient" ? "비로그인" : "로그인됨"}
              </div>
            </div>
          )}
          {!collapsed && (
            role === "patient" ? (
              <a href={`/login?next=${encodeURIComponent(path)}`}
                className="text-[11.5px] font-semibold text-teal-600 bg-teal-soft border border-teal/30 rounded-lg px-2.5 py-1 hover:border-teal">로그인</a>
            ) : (
              <button onClick={async () => { await logout(); setRole("patient"); window.location.href = landingFor("patient"); }}
                className="text-[11.5px] font-semibold text-ink-2 bg-surface-2 border border-line rounded-lg px-2.5 py-1 hover:border-ink-3">로그아웃</button>
            )
          )}
        </div>
      </div>
    </aside>
  );
}

/* ── 아이콘 (line, currentColor) ─────────────────────────────────────── */
function CrossIcon() {
  return (<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.4" strokeLinecap="round">
    <path d="M12 7v10M7 12h10" /></svg>);
}
function ChevronIcon({ dir }: { dir: "left" | "right" }) {
  return (<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
    style={{ transform: dir === "right" ? "rotate(180deg)" : undefined }}><path d="M15 6l-6 6 6 6" /></svg>);
}
function HomeIcon() {
  return (<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <path d="M4 11l8-7 8 7" /><path d="M6 10v9h12v-9" /></svg>);
}
function MapIcon() {
  return (<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" strokeLinecap="round">
    <path d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2Z" /><path d="M9 4v14M15 6v14" /></svg>);
}
function PatientIcon() {
  return (<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="8" r="3.2" /><path d="M5 20c0-3.6 3.1-6 7-6s7 2.4 7 6" /></svg>);
}
function FormIcon() {
  return (<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <rect x="5" y="3" width="14" height="18" rx="2.4" /><path d="M9 8h6M9 12h6M9 16h3" /></svg>);
}
function QrIcon() {
  return (<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" />
    <rect x="3" y="14" width="7" height="7" rx="1" />
    <path d="M14 14h1M19 14h1M14 19h3M19 19h1M14 17h1M17 17v2" />
  </svg>);
}
function ChatIcon() {
  return (<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 11.5a8.4 8.4 0 0 1-9 8.4 9 9 0 0 1-3.3-.6L3 21l1.3-4a8.4 8.4 0 1 1 16.7-5.5Z" />
    <path d="M8.5 11.5h.01M12 11.5h.01M15.5 11.5h.01" />
  </svg>);
}
