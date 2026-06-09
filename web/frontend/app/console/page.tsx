"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE, getAmrs, AmrSnapshot, getMissions, Mission, getTargets, GotoTarget, pushMission, saveMode } from "@/lib/api";
import { PRIMARY_NS, SECONDARY_NS } from "@/lib/config";
import MapView from "@/components/MapView";
import UPlotChart from "@/components/UPlotChart";

const ROBOTS = [PRIMARY_NS, SECONDARY_NS];
const COLOR: Record<string, string> = { robot3: "#0ca39a", robot6: "#2f74e0" };
const CAP = 600;

type Cmd = { action: string; label: string; sub: string; tone: "danger" | "warn" | "safe"; confirm?: boolean };
const COMMANDS: Cmd[] = [
  { action: "dock", label: "도킹", sub: "충전 복귀", tone: "safe" },
  { action: "undock", label: "언도킹", sub: "스테이션 이탈", tone: "safe" },
  { action: "ros_restart", label: "ROS 재시작", sub: "노드 재기동", tone: "warn", confirm: true },
  { action: "reboot", label: "재부팅", sub: "로봇 PC", tone: "danger", confirm: true },
  { action: "shutdown", label: "종료", sub: "전원 종료", tone: "danger", confirm: true },
];
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

type Buf = { t: number[]; batt: number[]; lin: number[]; ang: number[]; msgTimes: number[] };
const newBuf = (): Buf => ({ t: [], batt: [], lin: [], ang: [], msgTimes: [] });
const push = (a: number[], v: number) => { a.push(v); if (a.length > CAP) a.shift(); };
type Alert = { source?: string; class?: string; distance?: number; confidence?: number; stamp?: number };

export default function ConsolePage() {
  const [ns, setNs] = useState(PRIMARY_NS);
  // SSE 수신은 ref 에 적재(고빈도), 화면 갱신은 5Hz 틱으로 분리(맵+차트 동시)
  const snaps = useRef<Record<string, AmrSnapshot>>({});
  const bufs = useRef<Record<string, Buf>>({ [PRIMARY_NS]: newBuf(), [SECONDARY_NS]: newBuf() });
  const [amrs, setAmrs] = useState<Record<string, AmrSnapshot>>({});
  const [, setTick] = useState(0);
  const [live, setLive] = useState(false);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  // 제어
  const [missions, setMissions] = useState<Mission[]>([]);
  const [targets, setTargets] = useState<Record<string, GotoTarget>>({});
  const [sending, setSending] = useState("");
  const [toast, setToast] = useState<null | { ok: boolean; msg: string }>(null);

  // ── 단일 SSE 스트림(텔레메트리 + 알림) ──
  useEffect(() => {
    getAmrs().then((a) => { snaps.current = { ...snaps.current, ...a }; setAmrs({ ...snaps.current }); }).catch(() => {});
    const es = new EventSource(`${API_BASE}/api/stream`, { withCredentials: true });
    es.onopen = () => setLive(true);
    es.onerror = () => setLive(false);
    es.onmessage = (e) => {
      try {
        const d = JSON.parse(e.data);
        const src = d?.source;
        if (!src) return;
        snaps.current[src] = d;
        if (!bufs.current[src]) bufs.current[src] = newBuf();
        const b = bufs.current[src];
        push(b.t, b.t.length);
        push(b.batt, d.battery?.pct ?? 0);
        push(b.lin, d.vel?.lin ?? 0);
        push(b.ang, d.vel?.ang ?? 0);
        b.msgTimes.push(Date.now());
        if (b.msgTimes.length > 100) b.msgTimes.shift();
      } catch {}
    };
    const ea = new EventSource(`${API_BASE}/api/alerts`, { withCredentials: true });
    ea.onmessage = (e) => { try { setAlerts((p) => [{ ...JSON.parse(e.data) }, ...p].slice(0, 50)); } catch {} };
    // 5Hz: 맵(amrs state) + 차트(setTick) 동시 갱신
    const t = setInterval(() => { setAmrs({ ...snaps.current }); setTick((x) => x + 1); }, 200);
    return () => { es.close(); ea.close(); clearInterval(t); };
  }, []);

  // ── mission_pool 폴링 + goto 타깃 ──
  const refresh = useCallback(() => {
    getMissions(ns).then((r) => setMissions(r.missions || [])).catch(() => setMissions([]));
  }, [ns]);
  useEffect(() => { refresh(); const t = setInterval(refresh, 3000); return () => clearInterval(t); }, [refresh]);
  useEffect(() => { getTargets().then((d) => setTargets(d.targets || {})).catch(() => {}); }, []);

  async function dispatch(key: string, action: string, label: string,
                          opts?: { mode?: string; params?: Record<string, unknown>; confirm?: boolean }) {
    if (sending) return;
    if (opts?.confirm && !window.confirm(`${ns.toUpperCase()} — "${label}" 하달할까요?`)) return;
    setSending(key);
    try {
      const r = await pushMission(ns, action, opts?.params, opts?.mode);
      setToast(r.ok ? { ok: true, msg: `${ns.toUpperCase()} ← ${label} 하달됨` } : { ok: false, msg: r.error || "실패" });
      if (r.ok) refresh();
    } catch (e) { setToast({ ok: false, msg: String(e) }); }
    finally { setSending(""); setTimeout(() => setToast(null), 2600); }
  }

  const col = COLOR[ns] || "#0ca39a";

  return (
    <div className="p-5 md:p-7">
      {/* ── 헤더: 로봇 선택 · LIVE · 전체해제 ── */}
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="eyebrow">관리자 콘솔</div>
          <h1 className="text-[clamp(20px,3.5vw,26px)] font-bold mt-1 leading-tight">실시간 관제 · 제어 · 디버그</h1>
        </div>
        <div className="flex items-center gap-2.5 flex-wrap">
          {ROBOTS.map((r) => {
            const on = ns === r;
            return (
              <button key={r} onClick={() => setNs(r)}
                className={`flex items-center gap-2 px-3.5 py-2 rounded-xl border font-bold text-[13px] transition-colors ${on ? "text-white border-transparent" : "bg-surface text-ink-2 border-line hover:border-ink-3"}`}
                style={on ? { background: COLOR[r] } : undefined}>
                <span className="w-2.5 h-2.5 rounded-full" style={{ background: on ? "#fff" : COLOR[r] }} />
                {r.toUpperCase()}
              </button>
            );
          })}
          <span className={`pill ${live ? "bg-green-soft text-green" : "bg-surface-2 text-ink-3"}`}>
            <span className={`dot ${live ? "bg-green live-dot" : "bg-ink-3"}`} /> {live ? "수신 중" : "연결 대기"}
          </span>
          <button onClick={() => dispatch("clear", "clear", "전체 모드 해제", { confirm: true })} disabled={!!sending}
            className="text-[12px] font-semibold text-red bg-red-soft border border-[#f3c9cb] rounded-lg px-3 py-2 hover:border-red disabled:opacity-50">
            전체 해제
          </button>
        </div>
      </div>

      {/* ── 상단: 지도(좌) + 제어(우) ── */}
      <div className="grid grid-cols-1 xl:grid-cols-[1fr_372px] gap-5 mt-5 rise">
        {/* 실시간 관제 지도 */}
        <div className="flex flex-col gap-2 min-w-0">
          <MapToolbar amrs={amrs} />
          <div className="h-[clamp(380px,52vh,620px)]">
            <MapView embedded ns={ns} amrs={amrs} live={live} />
          </div>
        </div>

        {/* 로봇 제어 패널 */}
        <div className="card p-4 flex flex-col gap-5 h-[clamp(380px,52vh,620px)] overflow-auto">
          <div>
            <div className="text-[12px] font-semibold text-ink-3 mb-2">시스템 명령</div>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
              {COMMANDS.map((c) => (
                <button key={c.action} onClick={() => dispatch(c.action, c.action, c.label, { confirm: c.confirm })} disabled={!!sending}
                  className={`flex flex-col items-start gap-0.5 p-3 rounded-xl border text-left transition-colors disabled:opacity-50 ${TONE[c.tone]}`}>
                  <span className="font-bold text-[13.5px]">{c.label}</span>
                  <span className="text-[10.5px] opacity-80">{c.sub}</span>
                  <span className="mono text-[9.5px] opacity-60 mt-0.5">{sending === c.action ? "전송 중…" : c.action}</span>
                </button>
              ))}
            </div>
          </div>

          <div>
            <div className="text-[12px] font-semibold text-ink-3 mb-2">모드 (높은 우선순위가 선점)</div>
            <div className="flex flex-col gap-1.5">
              {MODES.map((m) => (
                <div key={m.mode} className="flex items-center gap-2 bg-surface-2 border border-line rounded-lg px-3 py-2">
                  <div className="min-w-0 flex-1">
                    <span className="font-bold text-[13px]">{m.label}</span>
                    <span className="mono text-[10px] text-ink-3 ml-1.5">{m.mode}·{m.sub}</span>
                  </div>
                  <button onClick={() => dispatch(`start:${m.mode}`, "start", `${m.label} 시작`, { mode: m.mode })} disabled={!!sending}
                    className="text-[12px] font-semibold text-teal-600 bg-teal-soft border border-teal/30 rounded-md px-2.5 py-1 hover:border-teal disabled:opacity-50">
                    {sending === `start:${m.mode}` ? "…" : "시작"}
                  </button>
                  <button onClick={() => dispatch(`stop:${m.mode}`, "stop", `${m.label} 정지`, { mode: m.mode })} disabled={!!sending}
                    className="text-[12px] font-semibold text-ink-2 bg-surface border border-line rounded-md px-2.5 py-1 hover:border-ink-3 disabled:opacity-50">
                    {sending === `stop:${m.mode}` ? "…" : "정지"}
                  </button>
                </div>
              ))}
            </div>
          </div>

          <div>
            <div className="text-[12px] font-semibold text-ink-3 mb-2">이동 (goto)</div>
            <div className="grid grid-cols-2 gap-2">
              {Object.entries(targets).map(([id, t]) => (
                <button key={id} disabled={!!sending}
                  onClick={() => dispatch(`goto:${id}`, "goto", t.label, {
                    params: { x: t.x, y: t.y, yaw: t.yaw ?? 0, dock_after: !!t.dock_after, label: t.label }, confirm: true,
                  })}
                  className="flex flex-col items-start bg-surface-2 border border-line rounded-lg px-3 py-2 hover:border-brand disabled:opacity-50">
                  <span className="font-bold text-[12.5px]">{t.label}</span>
                  <span className="mono text-[9.5px] opacity-60 mt-0.5">{sending === `goto:${id}` ? "전송 중…" : `(${t.x}, ${t.y})${t.dock_after ? "·dock" : ""}`}</span>
                </button>
              ))}
              {Object.keys(targets).length === 0 && <span className="text-ink-3 text-[12px] col-span-2">등록된 목적지 없음</span>}
            </div>
          </div>

          <div className="mt-auto">
            <div className="flex items-center justify-between mb-1.5">
              <div className="text-[12px] font-semibold text-ink-3">{ns.toUpperCase()} · mission_pool</div>
              <span className="pill bg-surface-2 text-ink-2 border-line text-[11px]">{missions.length}건</span>
            </div>
            <div className="flex flex-col gap-1 max-h-[160px] overflow-auto">
              {!missions.length && <p className="text-ink-3 text-[12px]">적재된 명령 없음</p>}
              {missions.map((m) => (
                <div key={m.id} className="flex items-center gap-2 text-[11.5px] bg-surface-2 rounded-md px-2.5 py-1.5 border border-line">
                  <span className="pill text-white text-[10px]" style={{ background: col }}>{m.action}{m.mode ? ` ${m.mode}` : ""}</span>
                  <span className={`mono text-[10px] ${m.status === "pending" ? "text-[#b0814a]" : "text-green"}`}>{m.status}</span>
                  <span className="mono text-[10px] text-ink-3 ml-auto">{fmtTs(m.ts)}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* ── 하단: 디버그 텔레메트리(선택 로봇) + 알림 로그 ── */}
      <div className="grid grid-cols-1 xl:grid-cols-[1fr_372px] gap-5 mt-5">
        <AmrPanel src={ns} snap={amrs[ns]} buf={bufs.current[ns] || newBuf()} />
        <AlertLog alerts={alerts} />
      </div>

      {toast && (
        <div className={`fixed bottom-6 right-7 z-10 pill ${toast.ok ? "bg-green-soft text-green" : "bg-red-soft text-red"} shadow-lg`}>
          <span className={`dot ${toast.ok ? "bg-green" : "bg-red"}`} /> {toast.msg}
        </div>
      )}
    </div>
  );
}

// 자율 맵 생성(매핑) 토글 바
function MapToolbar({ amrs }: { amrs: Record<string, AmrSnapshot> }) {
  const mapping = (amrs[PRIMARY_NS]?.mode || "") === "mapping";
  const [busy, setBusy] = useState(false);
  const cmd = async (action: "start" | "stop") => { setBusy(true); await saveMode(action, "mapping").catch(() => {}); setBusy(false); };
  return (
    <div className="card p-2.5 flex items-center justify-between flex-wrap gap-2">
      <span className={`pill ${mapping ? "bg-teal-soft text-teal-600" : "bg-surface-2 text-ink-3"}`}>
        <span className={`dot ${mapping ? "bg-teal live-dot" : "bg-ink-3"}`} /> {mapping ? "자율 탐사 중" : "자율 맵 생성 대기"}
      </span>
      {mapping ? (
        <button onClick={() => cmd("stop")} disabled={busy} className="bg-red text-white font-semibold text-[12px] px-3 py-1.5 rounded-lg hover:opacity-90 disabled:opacity-40">중지·저장</button>
      ) : (
        <button onClick={() => cmd("start")} disabled={busy} className="bg-teal text-white font-semibold text-[12px] px-3 py-1.5 rounded-lg hover:bg-teal-600 disabled:opacity-40">자율 맵 생성</button>
      )}
    </div>
  );
}

function AmrPanel({ src, snap, buf }: { src: string; snap?: AmrSnapshot; buf: Buf }) {
  const col = COLOR[src] || "#0ca39a";
  const now = Date.now() / 1000;
  const age = snap?.stamp ? now - snap.stamp : Infinity;
  const online = age < 3;
  const recent = buf.msgTimes.filter((m) => Date.now() - m < 2000).length;
  const hz = (recent / 2).toFixed(1);
  const xs = buf.t.length ? buf.t : [0];
  const battData: [number[], number[]] = [xs, buf.batt.length ? buf.batt : [0]];
  const velData: [number[], number[], number[]] = [xs, buf.lin.length ? buf.lin : [0], buf.ang.length ? buf.ang : [0]];

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <span className="w-3 h-3 rounded-full" style={{ background: col }} />
          <span className="font-bold text-[15px]">{src.toUpperCase()} · 디버그</span>
          <span className="mono text-[11px] text-ink-3">/{src}</span>
        </div>
        <span className={`pill ${online ? "bg-green-soft text-green" : "bg-red-soft text-red"}`}>
          <span className={`dot ${online ? "bg-green" : "bg-red"}`} /> {online ? "LIVE" : "STALE"}
        </span>
      </div>
      <div className="grid grid-cols-3 sm:grid-cols-6 gap-2 mt-4">
        <H label="수신Hz" v={online ? hz : "0.0"} />
        <H label="경과" v={isFinite(age) ? `${(age * 1000).toFixed(0)}ms` : "—"} warn={age >= 3} />
        <H label="모드" v={snap?.mode ?? "—"} />
        <H label="배터리" v={snap?.battery?.pct != null ? `${Math.round(snap.battery.pct > 1 ? snap.battery.pct : snap.battery.pct * 100)}%` : "—"} />
        <H label="도킹" v={snap?.dock?.is_docked ? "Y" : "N"} />
        <H label="속도" v={snap?.vel ? snap.vel.lin.toFixed(2) : "—"} />
      </div>
      <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-4">
        <ChartBox title="배터리 %"><UPlotChart data={battData} series={[{ label: "batt", stroke: col, fill: col + "18" }]} /></ChartBox>
        <ChartBox title="선속/각속"><UPlotChart data={velData} series={[{ label: "lin", stroke: col }, { label: "ang", stroke: "#df8a44" }]} /></ChartBox>
      </div>
      <div className="mt-4 grid grid-cols-1 sm:grid-cols-[160px_1fr] gap-4">
        <LidarMini scan={snap?.scan} col={col} />
        <details className="bg-surface-2 rounded-xl border border-line p-3 overflow-hidden">
          <summary className="text-[12px] font-semibold text-ink-2 cursor-pointer select-none">원시 snapshot JSON</summary>
          <pre className="mono text-[10.5px] text-ink-2 mt-2 overflow-auto max-h-[180px] leading-relaxed">{snap ? JSON.stringify(snap, null, 1) : "데이터 없음"}</pre>
        </details>
      </div>
    </div>
  );
}

function H({ label, v, warn }: { label: string; v: string; warn?: boolean }) {
  return (
    <div className={`rounded-lg px-2.5 py-1.5 border ${warn ? "bg-red-soft border-[#f3c9cb]" : "bg-surface-2 border-line"}`}>
      <div className={`text-[10px] font-semibold ${warn ? "text-red" : "text-ink-3"}`}>{label}</div>
      <div className={`mono text-[14px] font-semibold mt-0.5 ${warn ? "text-red" : "text-ink"} truncate`}>{v}</div>
    </div>
  );
}
function ChartBox({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-surface-2 rounded-xl border border-line p-3">
      <div className="text-[11px] font-semibold text-ink-3 mb-1">{title}</div>{children}
    </div>
  );
}
type Scan = { angle_min: number; angle_inc: number; range_max: number; ranges: (number | null)[] };
function LidarMini({ scan, col }: { scan?: Scan; col: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const cv = ref.current; if (!cv) return;
    const S = 152, dpr = window.devicePixelRatio || 1;
    cv.width = S * dpr; cv.height = S * dpr;
    const ctx = cv.getContext("2d")!; ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, S, S); ctx.fillStyle = "#f4f7f9"; ctx.fillRect(0, 0, S, S);
    const cx = S / 2, cy = S / 2;
    ctx.strokeStyle = "#e5eaf0"; ctx.beginPath(); ctx.arc(cx, cy, S / 2 - 6, 0, Math.PI * 2); ctx.stroke();
    if (scan?.ranges?.length) {
      const { angle_min, angle_inc, range_max, ranges } = scan;
      const sc = (S / 2 - 8) / (range_max || 4);
      ctx.fillStyle = col;
      ranges.forEach((d, i) => {
        if (d == null || !isFinite(d)) return;
        const a = angle_min + i * angle_inc;
        ctx.fillRect(cx + d * sc * Math.cos(a) - 0.8, cy - d * sc * Math.sin(a) - 0.8, 1.6, 1.6);
      });
    }
    ctx.fillStyle = col; ctx.beginPath(); ctx.arc(cx, cy, 3, 0, Math.PI * 2); ctx.fill();
  });
  return <div className="bg-surface-2 rounded-xl border border-line p-2 grid place-items-center"><canvas ref={ref} style={{ width: 152, height: 152 }} /></div>;
}
function AlertLog({ alerts }: { alerts: Alert[] }) {
  return (
    <div className="card p-5">
      <div className="flex items-center justify-between">
        <h2 className="text-[14px] font-bold">순찰 알림 로그</h2>
        <span className="pill bg-surface-2 text-ink-2 border-line">{alerts.length}</span>
      </div>
      <div className="mt-3 flex flex-col gap-1.5 max-h-[420px] overflow-auto">
        {!alerts.length && <p className="text-ink-3 text-[13px]">알림 없음 (순찰 모드 탐지 시 표시)</p>}
        {alerts.map((a, i) => (
          <div key={i} className="flex items-center gap-3 text-[12.5px] bg-surface-2 rounded-lg px-3 py-1.5 border border-line">
            <span className="pill bg-red-soft text-red"><span className="dot bg-red" /> {a.class ?? "탐지"}</span>
            <span className="mono text-ink-3">{a.source}</span>
            {a.distance != null && <span className="text-ink-2">{a.distance}m</span>}
            {a.confidence != null && <span className="mono text-ink-3">conf {a.confidence}</span>}
          </div>
        ))}
      </div>
    </div>
  );
}

function fmtTs(ts?: number) {
  if (!ts) return "—";
  const d = new Date(ts);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}:${String(d.getSeconds()).padStart(2, "0")}`;
}
