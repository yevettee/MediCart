"use client";
import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { login } from "@/lib/api";
import { requiredRoleForRoute, roleAtLeast, landingFor } from "@/lib/auth";

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [pw, setPw] = useState("");
  const [err, setErr] = useState(false);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr(false);
    const role = await login(pw).catch(() => null);
    setBusy(false);
    if (role) {
      const next = params.get("next") || "";
      const safe = next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/\\");
      const dest = safe && roleAtLeast(role, requiredRoleForRoute(next)) ? next : landingFor(role);
      router.replace(dest);
    } else { setErr(true); setPw(""); }
  }

  return (
    <div className="min-h-screen grid place-items-center p-6 bg-canvas">
      <form onSubmit={submit} className="card w-full max-w-[380px] p-7 rise">
        <div className="flex items-center gap-3">
          <div className="w-11 h-11 rounded-xl bg-teal grid place-items-center shadow-[0_4px_14px_-4px_rgba(12,163,154,.6)]">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.4" strokeLinecap="round"><path d="M12 7v10M7 12h10" /></svg>
          </div>
          <div>
            <div className="font-bold text-[17px]">병동 관제</div>
            <div className="text-[12px] text-ink-3">WARD ASSIST ROBOT</div>
          </div>
        </div>

        <label className="block text-[13px] font-semibold text-ink-2 mt-6 mb-1.5">접속 비밀번호</label>
        <input autoFocus type="password" value={pw}
          onChange={(e) => setPw(e.target.value)}
          onInput={(e) => setPw((e.target as HTMLInputElement).value)}
          placeholder="비밀번호" className="field" />
        {err && <p className="text-red text-[12.5px] mt-2">비밀번호가 올바르지 않습니다.</p>}

        <button type="submit" disabled={busy}
          className="w-full mt-5 bg-teal text-white font-semibold text-[14px] py-2.5 rounded-xl hover:bg-teal-600 transition-colors disabled:opacity-40 shadow-[0_6px_16px_-6px_rgba(12,163,154,.6)]">
          {busy ? "확인 중…" : "입장"}
        </button>
        <p className="text-[11.5px] text-ink-3 mt-4 text-center">데모 환경 · 인가된 사용자만 접속</p>
      </form>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}
