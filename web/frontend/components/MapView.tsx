"use client";
import { useEffect, useRef, useState } from "react";
import { API_BASE, AmrSnapshot, getAmrs, getRooms, saveMode, getMapMeta, MapMeta } from "@/lib/api";
import { modeOf } from "@/lib/modes";
import { PRIMARY_NS, SECONDARY_NS } from "@/lib/config";

type Rooms = { rooms?: Record<string, { x: number; y: number; yaw?: number; patient?: string }> };
const AMR_COLOR: Record<string, string> = { robot3: "#0ca39a", robot6: "#2f74e0" };

export default function MapView() {
  const [amrs, setAmrs] = useState<Record<string, AmrSnapshot>>({});
  const [rooms, setRooms] = useState<Rooms>({});
  const [mapMeta, setMapMeta] = useState<MapMeta>({ available: false });
  const mapImg = useRef<HTMLImageElement | null>(null);
  const [mapReady, setMapReady] = useState(0); // 이미지 로드 트리거(리렌더)
  const [live, setLive] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  // 초기 + SSE
  useEffect(() => {
    getAmrs().then(setAmrs).catch(() => {});
    getRooms().then(setRooms).catch(() => {});
    getMapMeta().then((m) => {
      setMapMeta(m);
      if (m.available) {
        const img = new Image();
        img.onload = () => { mapImg.current = img; setMapReady((n) => n + 1); };
        img.src = `${API_BASE}/api/map.png?t=${Date.now()}`;
      }
    }).catch(() => {});
    const es = new EventSource(`${API_BASE}/api/stream`, { withCredentials: true });
    es.onopen = () => setLive(true);
    es.onerror = () => setLive(false);
    es.onmessage = (e) => {
      try {
        const d = JSON.parse(e.data);
        if (d?.source) setAmrs((p) => ({ ...p, [d.source]: d }));
      } catch {}
    };
    return () => es.close();
  }, []);

  // 캔버스 렌더
  useEffect(() => {
    const cv = canvasRef.current, wrap = wrapRef.current;
    if (!cv || !wrap) return;
    const dpr = window.devicePixelRatio || 1;
    const W = wrap.clientWidth, H = wrap.clientHeight;
    cv.width = W * dpr; cv.height = H * dpr; cv.style.width = W + "px"; cv.style.height = H + "px";
    const ctx = cv.getContext("2d")!; ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);

    // 저장된 SLAM 맵이 있으면 그 범위로 좌표계 고정, 없으면 기존 자동핏
    let X: (wx: number) => number, Y: (wy: number) => number;
    const img = mapImg.current;
    if (mapMeta.available && img && mapMeta.resolution && mapMeta.origin) {
      const res = mapMeta.resolution, [ox, oy] = mapMeta.origin;
      const iw = img.naturalWidth, ih = img.naturalHeight;
      const s = Math.min((W - 24 * 2) / iw, (H - 24 * 2) / ih);
      const offx = (W - iw * s) / 2, offy = (H - ih * s) / 2;
      ctx.drawImage(img, offx, offy, iw * s, ih * s);
      // 맵 픽셀(좌하단 origin, y-up) → 화면. world(wx,wy)→맵픽셀→화면.
      X = (wx: number) => offx + ((wx - ox) / res) * s;
      Y = (wy: number) => offy + (ih - (wy - oy) / res) * s;
    } else {
      const pts: [number, number][] = [];
      Object.values(rooms.rooms || {}).forEach((r) => pts.push([r.x, r.y]));
      Object.values(amrs).forEach((a) => a?.pose && pts.push([a.pose.x, a.pose.y]));
      if (!pts.length) pts.push([0, 0], [4, 4]);
      const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
      const pad = 1.6;
      const minX = Math.min(...xs) - pad, maxX = Math.max(...xs) + pad;
      const minY = Math.min(...ys) - pad, maxY = Math.max(...ys) + pad;
      const wWorld = Math.max(maxX - minX, 1), hWorld = Math.max(maxY - minY, 1);
      const m = 24;
      const s = Math.min((W - m * 2) / wWorld, (H - m * 2) / hWorld);
      const offx = (W - wWorld * s) / 2, offy = (H - hWorld * s) / 2;
      X = (wx: number) => offx + (wx - minX) * s;
      Y = (wy: number) => H - (offy + (wy - minY) * s);
      // 그리드(맵 없을 때만)
      ctx.strokeStyle = "#eef2f6"; ctx.lineWidth = 1;
      for (let gx = Math.ceil(minX); gx <= maxX; gx++) { ctx.beginPath(); ctx.moveTo(X(gx), 0); ctx.lineTo(X(gx), H); ctx.stroke(); }
      for (let gy = Math.ceil(minY); gy <= maxY; gy++) { ctx.beginPath(); ctx.moveTo(0, Y(gy)); ctx.lineTo(W, Y(gy)); ctx.stroke(); }
    }

    // 병실 마커
    Object.entries(rooms.rooms || {}).forEach(([name, r]) => {
      const px = X(r.x), py = Y(r.y);
      ctx.fillStyle = "#eef4f8"; ctx.strokeStyle = "#d4dde5"; ctx.lineWidth = 1.5;
      roundRect(ctx, px - 16, py - 12, 32, 24, 6); ctx.fill(); ctx.stroke();
      ctx.fillStyle = "#8597a5"; ctx.font = "600 10px 'Pretendard Variable'"; ctx.textAlign = "center";
      ctx.fillText(name, px, py + 3.5);
    });

    // AMR 마커 (+ LiDAR + 헤딩)
    Object.entries(amrs).forEach(([src, a]) => {
      if (!a?.pose) return;
      const col = AMR_COLOR[src] || "#0ca39a";
      const px = X(a.pose.x), py = Y(a.pose.y), yaw = a.pose.yaw || 0;
      // 라이다
      if (a.scan?.ranges?.length) {
        const { angle_min, angle_inc, ranges } = a.scan;
        ctx.fillStyle = col + "26";
        ranges.forEach((d, i) => {
          if (d == null || !isFinite(d)) return;
          const ang = yaw + angle_min + i * angle_inc;
          const lx = X(a.pose!.x + d * Math.cos(ang)), ly = Y(a.pose!.y + d * Math.sin(ang));
          ctx.fillRect(lx - 1, ly - 1, 2, 2);
        });
      }
      // 헤딩
      ctx.strokeStyle = col; ctx.lineWidth = 2.5; ctx.beginPath();
      ctx.moveTo(px, py); ctx.lineTo(px + Math.cos(-yaw) * 0 + Math.cos(yaw) * 16, py - Math.sin(yaw) * 16); ctx.stroke();
      // 본체
      ctx.beginPath(); ctx.arc(px, py, 9, 0, Math.PI * 2);
      ctx.fillStyle = col; ctx.fill();
      ctx.lineWidth = 3; ctx.strokeStyle = "#fff"; ctx.stroke();
    });
  }, [amrs, rooms, mapMeta, mapReady]);

  const sources = Object.keys(amrs).length ? Object.keys(amrs) : [PRIMARY_NS, SECONDARY_NS];

  return (
    <div className="p-7">
      <Header live={live} />
      <MappingControl amrs={amrs} />
      <div className="grid grid-cols-[1fr_320px] gap-5 mt-5 rise">
        {/* 맵 */}
        <div ref={wrapRef} className="card relative overflow-hidden h-[calc(100vh-150px)] min-h-[420px]">
          <canvas ref={canvasRef} className="absolute inset-0" />
          <div className="absolute left-4 top-4 pill bg-surface/90 border-line text-ink-2 backdrop-blur">
            <span className="dot bg-teal" /> 2D 병동 맵 · 실시간
          </div>
        </div>
        {/* AMR 카드 */}
        <div className="flex flex-col gap-4 h-[calc(100vh-150px)] overflow-auto pr-1">
          {sources.map((src) => <AmrCard key={src} src={src} a={amrs[src]} />)}
        </div>
      </div>
    </div>
  );
}

function Header({ live }: { live: boolean }) {
  return (
    <div className="flex items-end justify-between">
      <div>
        <div className="eyebrow">실시간 관제</div>
        <h1 className="text-[26px] font-bold text-ink mt-1 leading-tight">병동 통합 관제</h1>
      </div>
      <span className={`pill ${live ? "bg-green-soft text-green" : "bg-surface-2 text-ink-3"}`}>
        <span className={`dot ${live ? "bg-green live-dot" : "bg-ink-3"}`} />
        {live ? "텔레메트리 수신 중" : "연결 대기"}
      </span>
    </div>
  );
}

function MappingControl({ amrs }: { amrs: Record<string, AmrSnapshot> }) {
  const mapping = (amrs[PRIMARY_NS]?.mode || "") === "mapping";
  const [busy, setBusy] = useState(false);
  const cmd = async (action: "start" | "stop") => {
    setBusy(true);
    await saveMode(action, "mapping").catch(() => {});
    setBusy(false);
  };
  return (
    <div className="mt-3 card p-3 flex items-center justify-between flex-wrap gap-3">
      <div className="flex items-center gap-2.5">
        <span className={`pill ${mapping ? "bg-teal-soft text-teal-600" : "bg-surface-2 text-ink-3"}`}>
          <span className={`dot ${mapping ? "bg-teal live-dot" : "bg-ink-3"}`} />
          {mapping ? "자율 탐사 중" : "자율 맵 생성 대기"}
        </span>
        <span className="text-[12.5px] text-ink-3">2D LiDAR로 장애물 회피하며 탐사 → 완료 시 자동 저장</span>
      </div>
      {mapping ? (
        <button onClick={() => cmd("stop")} disabled={busy}
          className="bg-red text-white font-semibold text-[13px] px-4 py-2 rounded-xl hover:opacity-90 disabled:opacity-40">
          중지 · 저장
        </button>
      ) : (
        <button onClick={() => cmd("start")} disabled={busy}
          className="bg-teal text-white font-semibold text-[13px] px-4 py-2 rounded-xl hover:bg-teal-600 disabled:opacity-40">
          자율 맵 생성 시작
        </button>
      )}
    </div>
  );
}

function AmrCard({ src, a }: { src: string; a: AmrSnapshot }) {
  const col = AMR_COLOR[src] || "#0ca39a";
  const mode = modeOf(a?.mode || a?.state);
  const off = !a;
  return (
    <div className="card card-hover p-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <span className="w-3 h-3 rounded-full" style={{ background: col }} />
          <span className="font-bold text-[15px]">{src.toUpperCase()}</span>
        </div>
        <span className="pill" style={{ background: mode.soft, color: mode.color }}>
          <span className="dot" style={{ background: mode.color }} /> {mode.label}
        </span>
      </div>
      {off ? (
        <p className="text-[13px] text-ink-3 mt-3">데이터 수신 없음</p>
      ) : (
        <div className="mt-3 grid grid-cols-2 gap-2.5">
          <Stat label="위치 X·Y" v={`${fmt(a.pose?.x)}, ${fmt(a.pose?.y)}`} unit="m" mono />
          <Stat label="방향" v={fmt((a.pose?.yaw ?? 0))} unit="rad" mono />
          <Stat label="배터리" v={a.battery?.pct != null ? Math.round(a.battery.pct > 1 ? a.battery.pct : a.battery.pct * 100).toString() : "—"} unit="%" />
          <Stat label="속도" v={fmt(a.vel?.lin)} unit="m/s" mono />
        </div>
      )}
    </div>
  );
}

function Stat({ label, v, unit, mono }: { label: string; v: string; unit?: string; mono?: boolean }) {
  return (
    <div className="bg-surface-2 rounded-xl px-3 py-2 border border-line">
      <div className="text-[10.5px] text-ink-3 font-semibold">{label}</div>
      <div className={`text-[15px] font-semibold text-ink mt-0.5 ${mono ? "mono" : ""}`}>
        {v}{unit && <span className="text-[11px] text-ink-3 ml-1 font-normal">{unit}</span>}
      </div>
    </div>
  );
}

const fmt = (n?: number) => (n == null || isNaN(n) ? "—" : (Math.round(n * 100) / 100).toFixed(2));
function roundRect(c: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  c.beginPath(); c.moveTo(x + r, y);
  c.arcTo(x + w, y, x + w, y + h, r); c.arcTo(x + w, y + h, x, y + h, r);
  c.arcTo(x, y + h, x, y, r); c.arcTo(x, y, x + w, y, r); c.closePath();
}
