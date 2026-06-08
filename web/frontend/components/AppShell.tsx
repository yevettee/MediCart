"use client";
import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import Sidebar from "./Sidebar";

export default function AppShell({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const path = usePathname();

  // 접힘 상태 persist (태블릿/데스크톱)
  useEffect(() => {
    setCollapsed(localStorage.getItem("sidebar:collapsed") === "1");
  }, []);
  const toggleCollapse = () => {
    setCollapsed((c) => {
      localStorage.setItem("sidebar:collapsed", c ? "0" : "1");
      return !c;
    });
  };

  // 라우트 이동 시 모바일 드로어 닫기
  useEffect(() => { setMobileOpen(false); }, [path]);

  // 로그인·디스플레이 페이지는 사이드바/크롬 없이 단독 렌더
  if (path === "/login" || path === "/display") return <>{children}</>;

  return (
    <div className="flex min-h-screen">
      <Sidebar
        collapsed={collapsed}
        mobileOpen={mobileOpen}
        onCloseMobile={() => setMobileOpen(false)}
        onToggleCollapse={toggleCollapse}
      />

      {/* 좁은 폭 드로어 백드롭 */}
      {mobileOpen && (
        <div className="fixed inset-0 z-30 bg-ink/30 backdrop-blur-[1px] md:hidden"
          onClick={() => setMobileOpen(false)} />
      )}

      <div className="flex-1 min-w-0 flex flex-col">
        {/* 모바일 상단바 (햄버거) — md 미만에서만 */}
        <header className="md:hidden sticky top-0 z-20 flex items-center gap-3 px-4 h-14 bg-surface/90 backdrop-blur border-b border-line">
          <button onClick={() => setMobileOpen(true)} aria-label="메뉴 열기"
            className="grid place-items-center w-9 h-9 rounded-lg text-ink-2 hover:bg-surface-2">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M4 7h16M4 12h16M4 17h16" /></svg>
          </button>
          <div className="flex items-center gap-2">
            <span className="w-6 h-6 rounded-lg bg-teal grid place-items-center">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.6" strokeLinecap="round"><path d="M12 7v10M7 12h10" /></svg>
            </span>
            <span className="font-bold text-[14px]">병동 관제</span>
          </div>
        </header>

        <main className="flex-1 min-w-0">{children}</main>
      </div>
    </div>
  );
}
