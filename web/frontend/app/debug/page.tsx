"use client";
import { useEffect, useRef, useState } from "react";
import { API_BASE, getAmrs, AmrSnapshot } from "@/lib/api";
import { PRIMARY_NS, SECONDARY_NS } from "@/lib/config";
import UPlotChart from "@/components/UPlotChart";

const SOURCES = [PRIMARY_NS, SECONDARY_NS];
const COLOR: Record<string, string> = { robot3: "#0ca39a", robot6: "#2f74e0" };
const CAP = 600; // 롤링 버퍼 상한(≈ 10fps·1분)

type Buf = { t: number[]; batt: number[]; lin: number[]; ang: number[]; msgTimes: number[] };
const newBuf = (): Buf => ({ t: [], batt: [], lin: [], ang: [], msgTimes: [] });
const push = (a: number[], v: number) => { a.push(v); if (a.length > CAP) a.shift(); };

type Alert = { source?: string; class?: string; distance?: number; confidence?: number; stamp?: number };

export default function DebugPage() {
  const snaps = useRef<Record<string, AmrSnapshot>>({});
  const bufs = useRef<Record<string, Buf>>({ [PRIMARY_NS]: newBuf(), [SECONDARY_NS]: newBuf() });
  const [, setTick] = useState(0);
  const [live, setLive] = useState(false);
  const [alerts, setAlerts] = useState<Alert[]>([]);

  useEffect(() => {
    getAmrs().then((a) => { snaps.current = { ...snaps.current, ...a }; }).catch(() => {});

    const es = new EventSource(`${API_BASE}/api/stream`, { withCredentials: true });
    es.onopen = () => setLive(true);
    es.onerror = () => setLive(false);
    es.onmessage = (e) => {
      try {
        const d = JSON.parse(e.data);
        const src = d?.source;
        if (!src || !bufs.current[src]) return;
        snaps.current[src] = d;
        const b = bufs.current[src];
        const n = b.t.length;
        push(b.t, n);
        push(b.batt, d.battery?.pct ?? 0);
        push(b.lin, d.vel?.lin ?? 0);
        push(b.ang, d.vel?.ang ?? 0);
        b.msgTimes.push(Date.now());
        if (b.msgTimes.length > 100) b.msgTimes.shift();
      } catch {}
    };

    const ea = new EventSource(`${API_BASE}/api/alerts`, { withCredentials: true });
    ea.onmessage = (e) => {
      try { setAlerts((p) => [{ ...JSON.parse(e.data) }, ...p].slice(0, 50)); } catch {}
    };

    const t = setInterval(() => setTick((x) => x + 1), 500); // 렌더 2Hz(수집과 분리)
    return () => { es.close(); ea.close(); clearInterval(t); };
  }, []);

  return (
    <div className="p-5 md:p-7">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="eyebrow">디버그</div>
          <h1 className="text-[clamp(20px,3.5vw,26px)] font-bold mt-1">PC1·PC2 Redis 종합</h1>
        </div>
        <span className={`pill ${live ? "bg-green-soft text-green" : "bg-surface-2 text-ink-3"}`}>
          <span className={`dot ${live ? "bg-green live-dot" : "bg-ink-3"}`} /> {live ? "스트림 수신 중" : "연결 대기"}
        </span>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 md:gap-5 mt-5 rise">
        {SOURCES.map((src) => <AmrPanel key={src} src={src} snap={snaps.current[src]} buf={bufs.current[src]} />)}
      </div>

      <AlertLog alerts={alerts} />
    </div>
  );
}

function AmrPanel({ src, snap, buf }: { src: string; snap: AmrSnapshot; buf: Buf }) {
  const col = COLOR[src] || "#0ca39a";
  const now = Date.now() / 1000;
  const age = snap?.stamp ? now - snap.stamp : Infinity;
  const online = age < 3;
  // 최근 2초 수신 메시지로 Hz 추정
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
          <span className="font-bold text-[15px]">{src.toUpperCase()}</span>
          <span className="mono text-[11px] text-ink-3">/{src}</span>
        </div>
        <span className={`pill ${online ? "bg-green-soft text-green" : "bg-red-soft text-red"}`}>
          <span className={`dot ${online ? "bg-green" : "bg-red"}`} /> {online ? "LIVE" : "STALE"}
        </span>
      </div>

      {/* 헬스 */}
      <div className="grid grid-cols-3 sm:grid-cols-6 gap-2 mt-4">
        <H label="수신Hz" v={online ? hz : "0.0"} />
        <H label="경과" v={isFinite(age) ? `${(age * 1000).toFixed(0)}ms` : "—"} warn={age >= 3} />
        <H label="모드" v={snap?.mode ?? "—"} />
        <H label="배터리" v={snap?.battery?.pct != null ? `${Math.round(snap.battery.pct)}%` : "—"} />
        <H label="도킹" v={snap?.dock?.is_docked ? "Y" : "N"} />
        <H label="속도" v={snap?.vel ? snap.vel.lin.toFixed(2) : "—"} />
      </div>

      {/* 차트 */}
      <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-4">
        <ChartBox title="배터리 %">
          <UPlotChart data={battData} series={[{ label: "batt", stroke: col, fill: col + "18" }]} />
        </ChartBox>
        <ChartBox title="선속/각속">
          <UPlotChart data={velData} series={[{ label: "lin", stroke: col }, { label: "ang", stroke: "#df8a44" }]} />
        </ChartBox>
      </div>

      {/* LiDAR + 원시 JSON */}
      <div className="mt-4 grid grid-cols-1 sm:grid-cols-[160px_1fr] gap-4">
        <LidarMini scan={snap?.scan} col={col} />
        <details className="bg-surface-2 rounded-xl border border-line p-3 overflow-hidden">
          <summary className="text-[12px] font-semibold text-ink-2 cursor-pointer select-none">원시 snapshot JSON</summary>
          <pre className="mono text-[10.5px] text-ink-2 mt-2 overflow-auto max-h-[180px] leading-relaxed">
{snap ? JSON.stringify(snap, null, 1) : "데이터 없음"}
          </pre>
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
      <div className="text-[11px] font-semibold text-ink-3 mb-1">{title}</div>
      {children}
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
    ctx.clearRect(0, 0, S, S);
    ctx.fillStyle = "#f4f7f9"; ctx.fillRect(0, 0, S, S);
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
  return (
    <div className="bg-surface-2 rounded-xl border border-line p-2 grid place-items-center">
      <canvas ref={ref} style={{ width: 152, height: 152 }} />
    </div>
  );
}

function AlertLog({ alerts }: { alerts: Alert[] }) {
  return (
    <div className="card p-5 mt-5">
      <div className="flex items-center justify-between">
        <h2 className="text-[14px] font-bold">순찰 알림 로그</h2>
        <span className="pill bg-surface-2 text-ink-2 border-line">{alerts.length}</span>
      </div>
      <div className="mt-3 flex flex-col gap-1.5 max-h-[260px] overflow-auto">
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
