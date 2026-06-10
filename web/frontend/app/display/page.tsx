"use client";
import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";

const POLL_MS = 2000;

export default function DisplayPage() {
  const router = useRouter();
  const prevPidRef = useRef("");
  const prevPhaseRef = useRef("");

  /* Firebase 폴링 ①QR 스캔 → 문진표 이동 ②nurse_cart 약품실 도착 → 로그인(+/ocr 리디렉트) */
  useEffect(() => {
    let pidInitialized = false;

    async function poll() {
      // ── QR 스캔 폴링 ─────────────────────────────────────────────────
      try {
        const r = await fetch("/api/display/patient", { cache: "no-store" });
        if (r.ok) {
          const { pid } = await r.json();
          if (!pidInitialized) {
            pidInitialized = true;
            prevPidRef.current = pid ?? "";
          } else if (pid && pid !== prevPidRef.current) {
            prevPidRef.current = pid;
            router.push(`/intake?pid=${pid}`);
          }
        }
      } catch { /* 네트워크 오류 무시 */ }

      // ── 간호사 카트 약품실 도착 폴링 ─────────────────────────────────
      // /api/nurse_cart/phase 는 인증 불필요(auth.py _OPEN) — 공용 화면에서 폴링 가능
      try {
        const r = await fetch("/api/nurse_cart/phase", { cache: "no-store" });
        if (r.ok) {
          const { phase } = await r.json();
          if (phase === "arrived" && prevPhaseRef.current !== "arrived") {
            // 비밀번호 입력 후 바로 /ocr 로 이동하도록 next 파라미터 전달
            router.push("/login?next=/ocr");
          }
          prevPhaseRef.current = phase ?? "idle";
        }
      } catch { /* 네트워크 오류 무시 */ }
    }

    poll();
    const timer = setInterval(poll, POLL_MS);
    return () => clearInterval(timer);
  }, [router]);

  return (
    <div className="min-h-screen bg-surface flex flex-col items-center justify-center gap-6 text-ink-3">
      <svg width="72" height="72" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round" className="opacity-20">
        <rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" />
        <rect x="3" y="14" width="7" height="7" rx="1" />
        <path d="M14 14h1M19 14h1M14 19h3M19 19h1M14 17h1M17 17v2" />
      </svg>
      <div className="text-center">
        <p className="text-lg font-medium">QR 스캔을 기다리는 중</p>
        <p className="text-sm mt-1 opacity-60">PC에서 환자 QR을 스캔하면 문진표가 자동으로 열립니다</p>
      </div>
      <span className="flex items-center gap-2 text-xs">
        <span className="w-2 h-2 rounded-full bg-teal animate-pulse" />
        실시간 연결 · 2초 갱신
      </span>
    </div>
  );
}
