"use client";
import { useCallback, useEffect, useState } from "react";
import { PRIMARY_NS, SECONDARY_NS } from "@/lib/config";
import { pushMission, getMissions, Mission } from "@/lib/api";

const ROBOTS = [PRIMARY_NS, SECONDARY_NS];
const ROBOT_COLOR: Record<string, string> = { robot3: "#0ca39a", robot6: "#2f74e0" };

// 명령 — tone: danger(빨강·확인필요) / warn(주황) / safe(틸)
type Cmd = { action: string; label: string; sub: string; tone: "danger" | "warn" | "safe"; confirm?: boolean };
const COMMANDS: Cmd[] = [
  { action: "dock", label: "도킹", sub: "충전 스테이션 복귀", tone: "safe" },
  { action: "undock", label: "언도킹", sub: "스테이션 이탈", tone: "safe" },
  { action: "ros_restart", label: "ROS 재시작", sub: "노드 스택 재기동", tone: "warn", confirm: true },
  { action: "reboot", label: "재부팅", sub: "로봇 PC 재부팅", tone: "danger", confirm: true },
  { action: "shutdown", label: "종료", sub: "로봇 PC 전원 종료", tone: "danger", confirm: true },
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

  const refresh = useCallback(() => {
    getMissions(ns).then((r) => setMissions(r.missions || [])).catch(() => setMissions([]));
  }, [ns]);

  useEffect(() => { refresh(); const t = setInterval(refresh, 3000); return () => clearInterval(t); }, [refresh]);

  async function send(cmd: Cmd) {
    if (sending) return;
    if (cmd.confirm && !window.confirm(`${ns.toUpperCase()} — "${cmd.label}" 명령을 하달할까요?`)) return;
    setSending(cmd.action);
    try {
      const r = await pushMission(ns, cmd.action);
      setToast(r.ok ? { ok: true, msg: `${ns.toUpperCase()} ← ${cmd.label} 하달됨` } : { ok: false, msg: r.error || "실패" });
      if (r.ok) refresh();
    } catch { setToast({ ok: false, msg: "전송 실패" }); }
    finally { setSending(""); setTimeout(() => setToast(null), 2600); }
  }

  const col = ROBOT_COLOR[ns] || "#0ca39a";

  return (
    <div className="p-5 md:p-7 max-w-[960px]">
      <div className="eyebrow">로봇 제어</div>
      <h1 className="text-[clamp(20px,3.5vw,26px)] font-bold mt-1">명령 하달</h1>
      <p className="text-[13px] text-ink-3 mt-1">버튼을 누르면 선택한 로봇의 <span className="mono">mission_pool</span> 에 명령이 적재됩니다(ROS 노드 통신 없이 DB 경유). 로봇측 리스너가 순서대로 실행합니다.</p>

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

      {/* 명령 버튼 */}
      <div className="mt-6">
        <div className="text-[12px] font-semibold text-ink-3 mb-2">명령</div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
          {COMMANDS.map((c) => (
            <button key={c.action} onClick={() => send(c)} disabled={!!sending}
              className={`flex flex-col items-start gap-1 p-4 rounded-2xl border text-left transition-colors disabled:opacity-50 ${TONE[c.tone]}`}>
              <span className="font-bold text-[15px]">{c.label}</span>
              <span className="text-[11.5px] opacity-80">{c.sub}</span>
              <span className="mono text-[10.5px] opacity-60 mt-1">{sending === c.action ? "전송 중…" : c.action}</span>
            </button>
          ))}
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
              <span className="pill text-white text-[11px]" style={{ background: col }}>{m.action}</span>
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
