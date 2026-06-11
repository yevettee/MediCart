"use client";
import { useEffect, useState } from "react";
import { getCsLogs, LANGS, type CsSession } from "@/lib/csChat";

/* CS 챗봇 상담 로그 뷰어 (의료진+) — RTDB cs_chat 에 적재된 환자↔봇 대화를 세션별로 본다.
   좌: 세션 목록(최신순) · 우: 선택 세션 대화. /api/cs_logs(staff) 에서 읽는다. */

const LANG_LABEL: Record<string, string> = Object.fromEntries(LANGS.map((l) => [l.code, l.label]));

function fmt(ts?: number): string {
  if (!ts) return "—";
  return new Date(ts).toLocaleString("ko-KR", {
    month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
  });
}

export default function CsLogsPage() {
  const [sessions, setSessions] = useState<CsSession[]>([]);
  const [sel, setSel] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  // 최초 1회 로드 — setState 는 promise 콜백(.then/.catch/.finally) 안에서만(동기 X).
  useEffect(() => {
    let alive = true;
    getCsLogs()
      .then((s) => { if (!alive) return; setSessions(s); setSel((c) => c ?? s[0]?.id ?? null); setErr(""); })
      .catch((e) => { if (alive) setErr(e instanceof Error ? e.message : "불러오기 실패"); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, []);

  // 새로고침 버튼 — 이벤트 핸들러는 동기 setState 허용(스피너 즉시 반영).
  function refresh() {
    setLoading(true); setErr("");
    getCsLogs()
      .then((s) => { setSessions(s); setSel((c) => c ?? s[0]?.id ?? null); })
      .catch((e) => setErr(e instanceof Error ? e.message : "불러오기 실패"))
      .finally(() => setLoading(false));
  }

  const current = sessions.find((s) => s.id === sel) ?? null;
  const totalMsgs = sessions.reduce((n, s) => n + s.count, 0);

  return (
    <div className="p-6 md:p-8 max-w-6xl">
      <header className="mb-6 flex items-end justify-between gap-4 flex-wrap">
        <div>
          <div className="eyebrow">환자 상담</div>
          <h1 className="text-2xl font-bold text-ink mt-1">CS 챗봇 상담 로그</h1>
          <p className="text-ink-3 text-sm mt-1">
            환자 안내 챗봇 대화 기록 · 세션 {sessions.length}건 · 메시지 {totalMsgs}개
          </p>
        </div>
        <button onClick={refresh} disabled={loading}
          className="rounded-xl bg-teal text-white px-4 py-2 text-sm font-semibold hover:bg-teal-600 disabled:opacity-50 transition-colors flex items-center gap-2">
          <RefreshIcon spin={loading} /> 새로고침
        </button>
      </header>

      {err && (
        <div className="rounded-2xl bg-red-soft border border-red/30 p-4 text-red text-sm mb-4">
          로그를 불러오지 못했습니다: {err}
        </div>
      )}

      {!err && !loading && sessions.length === 0 && (
        <div className="card p-10 text-center text-ink-3">
          아직 상담 기록이 없습니다. 환자가 챗봇으로 대화하면 여기에 누적됩니다.
        </div>
      )}

      {sessions.length > 0 && (
        <div className="grid md:grid-cols-[300px_1fr] gap-5">
          {/* 세션 목록 */}
          <div className="flex flex-col gap-2 max-h-[72vh] overflow-y-auto pr-1">
            {sessions.map((s) => {
              const firstUser = s.messages.find((m) => m.role === "user")?.text ?? "(빈 대화)";
              const active = s.id === sel;
              return (
                <button key={s.id} onClick={() => setSel(s.id)}
                  className={`text-left rounded-2xl p-3.5 border transition-colors ${
                    active ? "bg-teal-soft border-teal/40" : "bg-surface border-line hover:border-teal/30"
                  }`}>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="pill bg-surface-2 text-ink-2 text-[11px] font-semibold">{LANG_LABEL[s.lang] ?? s.lang}</span>
                    <span className="text-ink-3 text-[11.5px] ml-auto">{fmt(s.updated_at)}</span>
                  </div>
                  <p className="text-ink text-[13.5px] font-medium line-clamp-2 leading-snug">{firstUser}</p>
                  <p className="text-ink-3 text-[11.5px] mt-1">{s.count}개 메시지 · {s.id.slice(0, 8)}</p>
                </button>
              );
            })}
          </div>

          {/* 선택 세션 대화 */}
          <div className="card p-0 overflow-hidden flex flex-col max-h-[72vh]">
            {current ? (
              <>
                <div className="px-5 py-3.5 border-b border-line bg-surface-2 flex items-center gap-3">
                  <span className="grid place-items-center w-9 h-9 rounded-full bg-blue-soft text-blue">
                    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"><rect x="4" y="8" width="16" height="11" rx="3" /><path d="M12 8V4M9 13h.01M15 13h.01" /></svg>
                  </span>
                  <div className="min-w-0">
                    <div className="font-semibold text-ink text-[14px]">세션 {current.id.slice(0, 12)}</div>
                    <div className="text-ink-3 text-[12px]">{LANG_LABEL[current.lang] ?? current.lang} · {fmt(current.started_at)} ~ {fmt(current.updated_at)}</div>
                  </div>
                </div>
                <div className="flex-1 overflow-y-auto px-4 py-4 flex flex-col gap-2.5 bg-canvas">
                  {current.messages.map((m, i) => {
                    const user = m.role === "user";
                    return (
                      <div key={i} className={`flex flex-col ${user ? "items-end" : "items-start"}`}>
                        <div className={`max-w-[80%] px-3.5 py-2.5 text-[14px] leading-relaxed whitespace-pre-line ${
                          user ? "bg-blue text-white rounded-2xl rounded-br-md" : "bg-blue-soft text-ink rounded-2xl rounded-bl-md"
                        }`}>
                          {m.text}
                        </div>
                        <span className="text-ink-3 text-[10.5px] mt-1 px-1">{user ? "환자" : "메디"} · {fmt(m.ts)}</span>
                      </div>
                    );
                  })}
                </div>
              </>
            ) : (
              <div className="m-auto text-ink-3 text-sm p-10">왼쪽에서 세션을 선택하세요.</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function RefreshIcon({ spin }: { spin?: boolean }) {
  return (
    <svg className={spin ? "animate-spin" : ""} width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 12a9 9 0 1 1-2.6-6.4M21 4v5h-5" />
    </svg>
  );
}
