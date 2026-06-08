"use client";
import { useEffect, useRef } from "react";
import uPlot from "uplot";

type SeriesDef = { label: string; stroke: string; fill?: string };

/** 라이브 시계열용 경량 uPlot 래퍼. data 변경 시 setData(재생성 없음). */
export default function UPlotChart({
  data, series, height = 110,
}: {
  data: uPlot.AlignedData;   // [xs, ...ys]
  series: SeriesDef[];
  height?: number;
}) {
  const host = useRef<HTMLDivElement>(null);
  const plot = useRef<uPlot | null>(null);

  useEffect(() => {
    if (!host.current) return;
    const opts: uPlot.Options = {
      width: host.current.clientWidth || 300,
      height,
      legend: { show: false },
      cursor: { show: false },
      scales: { x: { time: false } },
      axes: [
        { show: false },
        { stroke: "#8597a5", grid: { stroke: "#eef2f6", width: 1 }, ticks: { show: false },
          size: 34, font: "11px 'IBM Plex Mono'" },
      ],
      series: [
        {},
        ...series.map((s) => ({ label: s.label, stroke: s.stroke, fill: s.fill, width: 1.6, points: { show: false } })),
      ],
    };
    const u = new uPlot(opts, data, host.current);
    plot.current = u;
    const ro = new ResizeObserver(() => {
      if (host.current) u.setSize({ width: host.current.clientWidth, height });
    });
    ro.observe(host.current);
    return () => { ro.disconnect(); u.destroy(); plot.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => { plot.current?.setData(data); }, [data]);

  return <div ref={host} className="w-full" />;
}
