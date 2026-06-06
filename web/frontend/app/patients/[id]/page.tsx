"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { getPatient, Patient, Visit } from "@/lib/api";

export default function PatientDetail() {
  const { id } = useParams<{ id: string }>();
  const [p, setP] = useState<Patient | null>(null);
  const [err, setErr] = useState(false);
  useEffect(() => { if (id) getPatient(id).then(setP).catch(() => setErr(true)); }, [id]);

  if (err) return <Pad><p className="text-red text-sm">불러오기 실패.</p></Pad>;
  if (!p) return <Pad><p className="text-ink-3 text-sm">불러오는 중…</p></Pad>;

  const v: Visit = p.visits?.[0] || {};
  const drugAllergy = clean(p["약물 알레르기"]);
  const foodAllergy = clean(p["음식/기타 알레르기"]);

  return (
    <Pad>
      <Link href="/patients" className="text-[13px] text-ink-2 hover:text-teal">← 환자 목록</Link>

      {/* 알레르기 경고 — 최상단 강조 */}
      {drugAllergy && (
        <div className="mt-4 flex items-center gap-3 rounded-2xl px-5 py-3.5 bg-red-soft border border-[#f3c9cb] rise">
          <WarnIcon />
          <div>
            <span className="text-red font-bold text-[14px]">약물 알레르기</span>
            <span className="text-ink ml-2.5 font-semibold">{drugAllergy}</span>
          </div>
        </div>
      )}

      {/* 환자 헤더 */}
      <div className="card p-6 mt-4 rise">
        <div className="flex items-start justify-between flex-wrap gap-4">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-[30px] font-bold leading-none">{p.성명}</h1>
              <span className="text-[15px] text-ink-2">{p.성별} · {String(p.나이)}세</span>
            </div>
            <div className="mono text-[12.5px] text-ink-3 mt-2">{p.id} · {p["주 진료과"]} · 주치의 {p.주치의}</div>
          </div>
          <div className="flex gap-2.5">
            <Tag label="혈액형" v={p.혈액형} />
            <Tag label="신장" v={p["신장(cm)"] ? `${p["신장(cm)"]}cm` : "—"} />
            <Tag label="체중" v={p["체중(kg)"] ? `${p["체중(kg)"]}kg` : "—"} />
            <Tag label="BMI" v={String(p.BMI ?? "—")} />
          </div>
        </div>
      </div>

      {/* 최근 생체징후 */}
      <div className="mt-5">
        <SectionTitle>최근 생체징후 {v.방문일 && <span className="text-ink-3 font-normal text-[12px] ml-1">{String(v.방문일)}</span>}</SectionTitle>
        <div className="grid grid-cols-4 gap-3 mt-3 rise">
          <Vital label="혈압" v={`${val(v.수축기혈압)}/${val(v.이완기혈압)}`} unit="mmHg" warn={Number(v.수축기혈압) >= 140} />
          <Vital label="맥박" v={val(v.맥박)} unit="bpm" warn={Number(v.맥박) >= 100 || Number(v.맥박) < 50} />
          <Vital label="호흡" v={val(v.호흡)} unit="/min" />
          <Vital label="체온" v={val(v.체온)} unit="℃" warn={Number(v.체온) >= 37.5} />
          <Vital label="SpO₂" v={val(v.SpO2)} unit="%" warn={Number(v.SpO2) < 95} />
          <Vital label="통증" v={val(v["통증점수"])} unit="/10" warn={Number(v["통증점수"]) >= 7} />
          <Vital label="의식" v={val(v.의식상태)} />
          <Vital label="낙상위험" v={val(v.낙상위험)} warn={String(v.낙상위험).includes("고") || String(v.낙상위험).includes("높")} />
        </div>
      </div>

      {/* 병력 + 외래기록 */}
      <div className="grid grid-cols-[1.1fr_1fr] gap-5 mt-6">
        <div className="card p-5 rise">
          <SectionTitle>병력 / 약물</SectionTitle>
          <dl className="mt-3 flex flex-col">
            <Row k="과거력" v={p["과거력(진단명, 진단연도)"]} />
            <Row k="수술력" v={p.수술력} />
            <Row k="가족력" v={p.가족력} />
            <Row k="복용약물" v={p["현재 복용약물(약명/용량/횟수)"]} />
            <Row k="음식/기타 알레르기" v={foodAllergy || "없음"} alert={!!foodAllergy} />
            <Row k="흡연 / 음주" v={`${p.흡연 ?? "—"} / ${p.음주 ?? "—"}`} />
          </dl>
        </div>
        <div className="card p-5 rise">
          <SectionTitle>외래 방문 기록</SectionTitle>
          <div className="mt-3 flex flex-col gap-3">
            {(p.visits || []).map((vv, i) => (
              <div key={i} className="relative pl-4 border-l-2 border-line">
                <span className="absolute -left-[5px] top-1.5 w-2 h-2 rounded-full bg-teal" />
                <div className="flex items-center gap-2">
                  <span className="mono text-[12px] text-ink-3">{String(vv.방문일)}</span>
                  <span className="pill bg-surface-2 text-ink-2 border-line text-[11px]">{String(vv.진료유형 ?? "")}</span>
                </div>
                <p className="text-[14px] text-ink mt-1 font-medium">{String(vv["주호소(CC)"] ?? "—")}</p>
                {!!vv["증상 발생시기/경과"] && <p className="text-[12.5px] text-ink-2 mt-0.5">{String(vv["증상 발생시기/경과"])}</p>}
                {!!vv["간호 관찰사항"] && <p className="text-[12px] text-ink-3 mt-1">간호: {String(vv["간호 관찰사항"])}</p>}
              </div>
            ))}
            {!(p.visits || []).length && <p className="text-ink-3 text-sm">외래 기록 없음</p>}
          </div>
        </div>
      </div>
    </Pad>
  );
}

const clean = (s?: string | null) => (s && s !== "없음" && String(s).trim() ? String(s) : null);
const val = (v: unknown) => (v == null || v === "" ? "—" : String(v));

function Pad({ children }: { children: React.ReactNode }) { return <div className="p-7 max-w-[1100px]">{children}</div>; }
function SectionTitle({ children }: { children: React.ReactNode }) { return <h2 className="text-[14px] font-bold text-ink">{children}</h2>; }
function Tag({ label, v }: { label: string; v?: unknown }) {
  return <div className="text-center"><div className="text-[10.5px] text-ink-3 font-semibold">{label}</div><div className="text-[15px] font-bold mono">{val(v)}</div></div>;
}
function Vital({ label, v, unit, warn }: { label: string; v: string; unit?: string; warn?: boolean }) {
  return (
    <div className={`rounded-xl px-3.5 py-3 border ${warn ? "bg-red-soft border-[#f3c9cb]" : "bg-surface border-line"}`}>
      <div className={`text-[11px] font-semibold ${warn ? "text-red" : "text-ink-3"}`}>{label}</div>
      <div className={`mono text-[19px] font-semibold mt-0.5 ${warn ? "text-red" : "text-ink"}`}>
        {v}{unit && <span className="text-[10.5px] text-ink-3 ml-1 font-normal">{unit}</span>}
      </div>
    </div>
  );
}
function Row({ k, v, alert }: { k: string; v?: unknown; alert?: boolean }) {
  return (
    <div className="flex gap-3 py-2.5 border-b border-line last:border-0">
      <dt className="text-[12.5px] text-ink-3 font-semibold w-[120px] shrink-0">{k}</dt>
      <dd className={`text-[13.5px] ${alert ? "text-red font-semibold" : "text-ink"}`}>{val(v)}</dd>
    </div>
  );
}
function WarnIcon() {
  return (<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#df4448" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 3 2 20h20L12 3Z" /><path d="M12 10v4M12 17.5v.5" /></svg>);
}
