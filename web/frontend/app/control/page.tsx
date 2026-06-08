"use client";
import { useCallback, useEffect, useState } from "react";
import { PRIMARY_NS, SECONDARY_NS } from "@/lib/config";
import { pushMission, getMissions, Mission, getTargets, GotoTarget } from "@/lib/api";

const ROBOTS = [PRIMARY_NS, SECONDARY_NS];
const ROBOT_COLOR: Record<string, string> = { robot3: "#0ca39a", robot6: "#2f74e0" };

// 시스템 명령(momentary) — tone: danger(빨강·확인) / warn(주황) / safe(틸)
type Cmd = { action: string; label: string; sub: string; tone: "danger" | "warn" | "safe"; confirm?: boolean };
const COMMANDS: Cmd[] = [
  { action: "dock", label: "도킹", sub: "충전 스테이션 복귀", tone: "safe" },
  { action: "undock", label: "언도킹", sub: "스테이션 이탈", tone: "safe" },
  { action: "ros_restart", label: "ROS 재시작", sub: "노드 스택 재기동", tone: "warn", confirm: true },
  { action: "reboot", label: "재부팅", sub: "로봇 PC 재부팅", tone: "danger", confirm: true },
  { action: "shutdown", label: "종료", sub: "로봇 PC 전원 종료", tone: "danger", confirm: true },
];

// 모드(continuous) — 우선순위 높은 순(문진>회진>지시>가이드>순찰). mission_manager 가 선점/복귀 중재.
const MODES: { mode: string; label: string; sub: string }[] = [
  { mode: "intake", label: "문진", sub: "우선순위 5" },
  { mode: "round", label: "회진(추종)", sub: "우선순위 4" },
  { mode: "errand", label: "지시", sub: "우선순위 3" },
  { mode: "guide", label: "가이드", sub: "우선순위 2" },
  { mode: "patrol", label: "순찰", sub: "우선순위 1" },
];

const TONE: Record<string, string> = {
  danger: "bg-red-soft text-red border-[#f3c9cb] hover:border-red",
  warn: "bg-[#fbf0e3] text-[#b0814a] border-[#ecd9be] hover:border-[#df8a44]",
  safe: "bg-teal-soft text-teal-600 border-teal/30 hover:border-teal",
};

export default function ControlPage() {
  const [ns, setNs] = useState(PRIMARY_NS);
  const [missions, setMissions] = useState<Mission[]>([]);
  const [toast, setToast] = useState<null | { ok: boolean; msg: string }>(null);
  const [sending, setSending] = useState("");
  const [targets, setTargets] = useState<Record<string, GotoTarget>>({});

  const refresh = useCallback(() => {
    getMissions(ns).then((r) => setMissions(r.missions || [])).catch(() => setMissions([]));
  }, [ns]);

  useEffect(() => { refresh(); const t = setInterval(refresh, 3000); return () => clearInterval(t); }, [refresh]);
  useEffect(() => { getTargets().then((d) => setTargets(d.targets || {})).catch(() => {}); }, []);

  // key: 버튼 식별(전송중 표시), action/mode: 하달 내용, label: 토스트, confirm: 확인창
  async function dispatch(key: string, action: string, label: string,
                          opts?: { mode?: string; params?: Record<string, unknown>; confirm?: boolean }) {
    const mode = opts?.mode, params = opts?.params, confirm = opts?.confirm;
    if (sending) return;
    if (confirm && !window.confirm(`${ns.toUpperCase()} — "${label}" 하달할까요?`)) return;
    setSending(key);
    try {
      const r = await pushMission(ns, action, params, mode);
      setToast(r.ok ? { ok: true, msg: `${ns.toUpperCase()} ← ${label} 하달됨` } : { ok: false, msg: r.error || "실패" });
      if (r.ok) refresh();
    } catch (e) {
      setToast({ ok: false, msg: String(e) });
    } finally { setSending(""); setTimeout(() => setToast(null), 2600); }
  }

  const col = ROBOT_COLOR[ns] || "#0ca39a";

  return (
    <div className="p-5 md:p-7 max-w-[960px]">
      <div className="eyebrow">로봇 제어</div>
      <h1 className="text-[clamp(20px,3.5vw,26px)] font-bold mt-1">명령 하달</h1>
      <p className="text-[13px] text-ink-3 mt-1">버튼을 누르면 선택한 로봇의 <span className="mono">mission_pool</span> 에 명령이 적재됩니다(ROS 노드 통신 없이 DB 경유). 로봇측 db_bridge→mission_manager 가 처리합니다.</p>

      {/* 로봇 선택 */}
      <div className="mt-5">
        <div className="text-[12px] font-semibold text-ink-3 mb-2">대상 로봇</div>
        <div className="flex gap-2.5">
          {ROBOTS.map((r) => {
            const on = ns === r;
            return (
              <button key={r} onClick={() => setNs(r)}
                className={`flex items-center gap-2.5 px-4 py-2.5 rounded-xl border font-semibold text-[14px] transition-colors ${
                  on ? "text-white border-transparent" : "bg-surface text-ink-2 border-line hover:border-ink-3"}`}
                style={on ? { background: ROBOT_COLOR[r] } : undefined}>
                <span className="w-2.5 h-2.5 rounded-full" style={{ background: on ? "#fff" : ROBOT_COLOR[r] }} />
                {r.toUpperCase()}
              </button>
            );
          })}
        </div>
      </div>

      {/* 시스템 명령 */}
      <div className="mt-6">
        <div className="text-[12px] font-semibold text-ink-3 mb-2">시스템 명령</div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
          {COMMANDS.map((c) => (
            <button key={c.action} onClick={() => dispatch(c.action, c.action, c.label, { confirm: c.confirm })} disabled={!!sending}
              className={`flex flex-col items-start gap-1 p-4 rounded-2xl border text-left transition-colors disabled:opacity-50 ${TONE[c.tone]}`}>
              <span className="font-bold text-[15px]">{c.label}</span>
              <span className="text-[11.5px] opacity-80">{c.sub}</span>
              <span className="mono text-[10.5px] opacity-60 mt-1">{sending === c.action ? "전송 중…" : c.action}</span>
            </button>
          ))}
        </div>
      </div>

      {/* 모드 명령 (시작/정지 — 우선순위 선점·복귀는 mission_manager 가 중재) */}
      <div className="mt-6">
        <div className="flex items-center justify-between mb-2">
          <div className="text-[12px] font-semibold text-ink-3">모드 (높은 우선순위가 선점, 정지 시 하위 모드 복귀)</div>
          <button onClick={() => dispatch("clear", "clear", "전체 모드 해제", { confirm: true })} disabled={!!sending}
            className="text-[12px] font-semibold text-red bg-red-soft border border-[#f3c9cb] rounded-lg px-3 py-1 hover:border-red disabled:opacity-50">
            전체 해제
          </button>
        </div>
        <div className="flex flex-col gap-2">
          {MODES.map((m) => (
            <div key={m.mode} className="flex items-center gap-3 bg-surface-2 border border-line rounded-xl px-4 py-2.5">
              <div className="min-w-0 flex-1">
                <span className="font-bold text-[14px]">{m.label}</span>
                <span className="mono text-[11px] text-ink-3 ml-2">{m.mode} · {m.sub}</span>
              </div>
              <button onClick={() => dispatch(`start:${m.mode}`, "start", `${m.label} 시작`, { mode: m.mode })} disabled={!!sending}
                className="text-[13px] font-semibold text-teal-600 bg-teal-soft border border-teal/30 rounded-lg px-3.5 py-1.5 hover:border-teal disabled:opacity-50">
                {sending === `start:${m.mode}` ? "…" : "시작"}
              </button>
              <button onClick={() => dispatch(`stop:${m.mode}`, "stop", `${m.label} 정지`, { mode: m.mode })} disabled={!!sending}
                className="text-[13px] font-semibold text-ink-2 bg-surface border border-line rounded-lg px-3.5 py-1.5 hover:border-ink-3 disabled:opacity-50">
                {sending === `stop:${m.mode}` ? "…" : "정지"}
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* 이동 프리셋 (goto) */}
      <div className="mt-6">
        <div className="font-bold text-[15px] mb-2">이동 (goto)</div>
        <div className="grid grid-cols-2 gap-2">
          {Object.entries(targets).map(([id, t]) => (
            <button key={id} disabled={!!sending}
              onClick={() => dispatch(`goto:${id}`, "goto", t.label, {
                params: { x: t.x, y: t.y, yaw: t.yaw ?? 0, dock_after: !!t.dock_after, label: t.label },
                confirm: true,
              })}
              className="flex flex-col items-start bg-surface-2 border border-line rounded-xl px-4 py-3 hover:border-brand disabled:opacity-50">
              <span className="font-bold text-[14px]">{t.label}</span>
              <span className="mono text-[10.5px] opacity-60 mt-1">
                {sending === `goto:${id}` ? "전송 중…" : `(${t.x}, ${t.y})${t.dock_after ? " · dock" : ""}`}
              </span>
            </button>
          ))}
          {Object.keys(targets).length === 0 && (
            <span className="text-ink-3 text-[13px]">등록된 목적지 없음(targets 시드 확인)</span>
          )}
        </div>
      </div>

      {/* mission_pool 적재 현황 */}
      <div className="card p-5 mt-7">
        <div className="flex items-center justify-between">
          <h2 className="text-[14px] font-bold">{ns.toUpperCase()} · mission_pool</h2>
          <span className="pill bg-surface-2 text-ink-2 border-line">{missions.length}건</span>
        </div>
        <div className="mt-3 flex flex-col gap-1.5 max-h-[320px] overflow-auto">
          {!missions.length && <p className="text-ink-3 text-[13px]">적재된 명령 없음</p>}
          {missions.map((m) => (
            <div key={m.id} className="flex items-center gap-3 text-[12.5px] bg-surface-2 rounded-lg px-3 py-2 border border-line">
              <span className="pill text-white text-[11px]" style={{ background: col }}>{m.action}{m.mode ? ` ${m.mode}` : ""}</span>
              <span className={`mono text-[11px] ${m.status === "pending" ? "text-[#b0814a]" : "text-green"}`}>{m.status}</span>
              <span className="mono text-[11px] text-ink-3 ml-auto">{fmt(m.ts)}</span>
            </div>
          ))}
        </div>
      </div>

      {toast && (
        <div className={`fixed bottom-6 right-7 z-10 pill ${toast.ok ? "bg-green-soft text-green" : "bg-red-soft text-red"} shadow-lg`}>
          <span className={`dot ${toast.ok ? "bg-green" : "bg-red"}`} /> {toast.msg}
        </div>
      )}
    </div>
  );
}

function fmt(ts?: number) {
  if (!ts) return "—";
  const d = new Date(ts);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}:${String(d.getSeconds()).padStart(2, "0")}`;
}
