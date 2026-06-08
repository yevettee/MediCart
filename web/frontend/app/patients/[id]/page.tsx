"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { getPatient, updatePatient, Patient, Visit } from "@/lib/api";

// RTDB 키(마이그레이션에서 / → _ 로 정제됨)와 정확히 일치시켜 읽는다.
const K_FOOD = "음식_기타 알레르기";
const K_MEDS = "현재 복용약물(약명_용량_횟수)";
const K_PMH = "과거력(진단명, 진단연도)";
const K_ONSET = "증상 발생시기_경과";

// 편집 대상 — info(정적정보) / vitals(최근 생체징후)
const INFO_HEAD = ["성명", "성별", "생년월일", "혈액형", "신장(cm)", "체중(kg)", "주 진료과", "주치의", "연락처", "보험유형"];
const INFO_HISTORY: [string, string, boolean][] = [
  // [키, 라벨, textarea?]
  [K_PMH, "과거력", true],
  ["수술력", "수술력", false],
  ["가족력", "가족력", true],
  [K_MEDS, "복용약물", true],
  ["약물 알레르기", "약물 알레르기", false],
  [K_FOOD, "음식/기타 알레르기", false],
  ["흡연", "흡연", false],
  ["음주", "음주", false],
];
const VITALS: [string, string, string?][] = [
  // [키, 라벨, 단위]
  ["수축기혈압", "수축기", "mmHg"], ["이완기혈압", "이완기", "mmHg"], ["맥박", "맥박", "bpm"],
  ["호흡", "호흡", "/min"], ["체온", "체온", "℃"], ["SpO2", "SpO₂", "%"],
  ["통증점수", "통증", "/10"], ["의식상태", "의식", undefined], ["낙상위험", "낙상위험", undefined],
];

export default function PatientDetail() {
  const { id } = useParams<{ id: string }>();
  const [p, setP] = useState<Patient | null>(null);
  const [err, setErr] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Record<string, unknown>>({});
  const [saving, setSaving] = useState(false);

  useEffect(() => { if (id) getPatient(id).then(setP).catch(() => setErr(true)); }, [id]);

  function startEdit() {
    if (!p) return;
    const d: Record<string, unknown> = {};
    [...INFO_HEAD, ...INFO_HISTORY.map((r) => r[0]), ...VITALS.map((v) => v[0])].forEach((k) => { d[k] = p[k] ?? ""; });
    setDraft(d);
    setEditing(true);
  }
  const setF = (k: string, v: unknown) => setDraft((d) => ({ ...d, [k]: v }));

  async function save() {
    if (!p || saving) return;
    setSaving(true);
    const info: Record<string, unknown> = {}, vitals: Record<string, unknown> = {};
    INFO_HEAD.forEach((k) => (info[k] = draft[k]));
    INFO_HISTORY.forEach((r) => (info[r[0]] = draft[r[0]]));
    VITALS.forEach((v) => (vitals[v[0]] = draft[v[0]]));
    try {
      const updated = await updatePatient(p.id, { info, vitals });
      setP(updated);
      setEditing(false);
    } catch { /* 저장 실패 시 편집 유지 */ }
    finally { setSaving(false); }
  }

  if (err) return <Pad><p className="text-red text-sm">불러오기 실패.</p></Pad>;
  if (!p) return <Pad><p className="text-ink-3 text-sm">불러오는 중…</p></Pad>;

  const v: Visit = p.visits?.[0] || {};
  const drugAllergy = clean(p["약물 알레르기"]);
  const foodAllergy = clean(p[K_FOOD]);
  const age = ageFrom(p.생년월일 as string | undefined);
  const bmi = bmiFrom(p["신장(cm)"], p["체중(kg)"]);

  return (
    <Pad>
      <Link href="/patients" className="text-[13px] text-ink-2 hover:text-teal">← 환자 목록</Link>

      {/* 약물 알레르기 경고 — 최상단 강조 */}
      {drugAllergy && !editing && (
        <div className="mt-4 flex items-center gap-3 rounded-2xl px-5 py-3.5 bg-red-soft border border-[#f3c9cb] rise">
          <WarnIcon />
          <div><span className="text-red font-bold text-[14px]">약물 알레르기</span>
            <span className="text-ink ml-2.5 font-semibold">{drugAllergy}</span></div>
        </div>
      )}

      {/* 환자 헤더 */}
      <div className="card p-6 mt-4 rise">
        {editing ? (
          <div className="grid grid-cols-2 md:grid-cols-3 gap-x-5 gap-y-3.5">
            {INFO_HEAD.map((k) => (
              <div key={k}>
                <label className="block text-[11.5px] font-semibold text-ink-3 mb-1">{k}</label>
                <input className="field" type={k === "생년월일" ? "date" : "text"}
                  value={(draft[k] as string) ?? ""} onChange={(e) => setF(k, e.target.value)} />
              </div>
            ))}
          </div>
        ) : (
          <div className="flex items-start justify-between flex-wrap gap-4">
            <div>
              <div className="flex items-center gap-3">
                <h1 className="text-[30px] font-bold leading-none">{p.성명}</h1>
                <span className="text-[15px] text-ink-2">{p.성별}{age != null && ` · ${age}세`}</span>
              </div>
              <div className="mono text-[12.5px] text-ink-3 mt-2">{p.id} · {p["주 진료과"]} · 주치의 {p.주치의}</div>
            </div>
            <div className="flex gap-2.5">
              <Tag label="혈액형" v={p.혈액형} />
              <Tag label="신장" v={p["신장(cm)"] ? `${p["신장(cm)"]}cm` : "—"} />
              <Tag label="체중" v={p["체중(kg)"] ? `${p["체중(kg)"]}kg` : "—"} />
              <Tag label="BMI" v={bmi ?? "—"} />
            </div>
          </div>
        )}
      </div>

      {/* 최근 생체징후 */}
      <div className="mt-5">
        <SectionTitle>최근 생체징후 {v.방문일 && <span className="text-ink-3 font-normal text-[12px] ml-1">{String(v.방문일)} 기준</span>}</SectionTitle>
        <div className="grid grid-cols-3 sm:grid-cols-5 gap-3 mt-3 rise">
          {VITALS.map(([k, label, unit]) =>
            editing ? (
              <div key={k} className="rounded-xl px-3 py-2.5 border bg-surface border-line">
                <div className="text-[11px] font-semibold text-ink-3 mb-1">{label}</div>
                <input className="field !py-1 !px-2 text-[14px]" value={(draft[k] as string) ?? ""} onChange={(e) => setF(k, e.target.value)} />
              </div>
            ) : (
              <Vital key={k} label={label} unit={unit} v={val(p[k])} warn={vitalWarn(k, p[k])} />
            )
          )}
        </div>
      </div>

      {/* 병력 + 외래기록 */}
      <div className="grid grid-cols-1 lg:grid-cols-[1.1fr_1fr] gap-5 mt-6">
        <div className="card p-5 rise">
          <SectionTitle>병력 / 약물</SectionTitle>
          {editing ? (
            <div className="mt-3 flex flex-col gap-3">
              {INFO_HISTORY.map(([k, label, area]) => (
                <div key={k}>
                  <label className="block text-[11.5px] font-semibold text-ink-3 mb-1">{label}</label>
                  {area
                    ? <textarea className="field min-h-[58px] resize-y" value={(draft[k] as string) ?? ""} onChange={(e) => setF(k, e.target.value)} />
                    : <input className="field" value={(draft[k] as string) ?? ""} onChange={(e) => setF(k, e.target.value)} />}
                </div>
              ))}
            </div>
          ) : (
            <dl className="mt-3 flex flex-col">
              <Row k="과거력" v={p[K_PMH]} />
              <Row k="수술력" v={p.수술력} />
              <Row k="가족력" v={p.가족력} />
              <Row k="복용약물" v={p[K_MEDS]} />
              <Row k="음식/기타 알레르기" v={foodAllergy || "없음"} alert={!!foodAllergy} />
              <Row k="흡연 / 음주" v={`${p.흡연 ?? "—"} / ${p.음주 ?? "—"}`} />
            </dl>
          )}
        </div>
        <div className="card p-5 rise">
          <SectionTitle>외래 방문 기록 <span className="text-ink-3 font-normal text-[12px] ml-1">{(p.visits || []).length}건</span></SectionTitle>
          <div className="mt-3 flex flex-col gap-3 max-h-[420px] overflow-auto">
            {(p.visits || []).map((vv, i) => (
              <div key={i} className="relative pl-4 border-l-2 border-line">
                <span className="absolute -left-[5px] top-1.5 w-2 h-2 rounded-full bg-teal" />
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="mono text-[12px] text-ink-3">{String(vv.방문일 ?? "")}</span>
                  {!!vv.진료유형 && <span className="pill bg-surface-2 text-ink-2 border-line text-[11px]">{String(vv.진료유형)}</span>}
                  {!!vv.진료과 && <span className="text-[11px] text-ink-3">{String(vv.진료과)}</span>}
                </div>
                <p className="text-[14px] text-ink mt-1 font-medium">{String(vv["주호소(CC)"] ?? "—")}</p>
                {!!vv[K_ONSET] && <p className="text-[12.5px] text-ink-2 mt-0.5">{String(vv[K_ONSET])}</p>}
                {!!vv["간호 관찰사항"] && <p className="text-[12px] text-ink-3 mt-1">간호: {String(vv["간호 관찰사항"])}</p>}
              </div>
            ))}
            {!(p.visits || []).length && <p className="text-ink-3 text-sm">외래 기록 없음 — <Link href="/intake" className="text-teal hover:underline">문진 작성</Link></p>}
          </div>
        </div>
      </div>

      {/* 우측 하단 편집 액션 */}
      <div className="fixed bottom-6 right-7 flex items-center gap-2.5 z-10">
        {editing ? (
          <>
            <button onClick={() => setEditing(false)} disabled={saving}
              className="bg-surface text-ink-2 font-semibold text-[14px] px-5 py-2.5 rounded-xl border border-line hover:bg-surface-2 transition-colors disabled:opacity-40">취소</button>
            <button onClick={save} disabled={saving}
              className="bg-teal text-white font-semibold text-[14px] px-6 py-2.5 rounded-xl hover:bg-teal-600 transition-colors disabled:opacity-40 shadow-[0_6px_16px_-6px_rgba(12,163,154,.6)]">
              {saving ? "저장 중…" : "저장"}</button>
          </>
        ) : (
          <button onClick={startEdit}
            className="flex items-center gap-2 bg-teal text-white font-semibold text-[14px] px-5 py-2.5 rounded-xl hover:bg-teal-600 transition-colors shadow-[0_8px_20px_-6px_rgba(12,163,154,.6)]">
            <EditIcon /> 편집</button>
        )}
      </div>
    </Pad>
  );
}

const clean = (s?: unknown) => { const t = s == null ? "" : String(s); return t && t !== "없음" && t.trim() ? t : null; };
const val = (v: unknown) => (v == null || v === "" ? "—" : String(v));
function ageFrom(birth?: string) {
  if (!birth) return null;
  const b = new Date(birth); if (isNaN(b.getTime())) return null;
  const n = new Date(); let a = n.getFullYear() - b.getFullYear();
  if (n.getMonth() < b.getMonth() || (n.getMonth() === b.getMonth() && n.getDate() < b.getDate())) a--;
  return a >= 0 && a < 150 ? a : null;
}
function bmiFrom(h?: unknown, w?: unknown) {
  const H = Number(h), W = Number(w);
  if (!H || !W) return null;
  return (W / ((H / 100) ** 2)).toFixed(1);
}
function vitalWarn(k: string, v: unknown): boolean {
  const n = Number(v);
  if (k === "수축기혈압") return n >= 140;
  if (k === "맥박") return n >= 100 || (n > 0 && n < 50);
  if (k === "체온") return n >= 37.5;
  if (k === "SpO2") return n > 0 && n < 95;
  if (k === "통증점수") return n >= 7;
  if (k === "낙상위험") return String(v).includes("고") || String(v).includes("높");
  return false;
}

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
function EditIcon() {
  return (<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 20h9" /><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z" /></svg>);
}
