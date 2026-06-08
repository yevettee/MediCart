"use client";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { getPatients, Patient, addVisit, getMe, submitIntake } from "@/lib/api";
import type { Role } from "@/lib/auth";

// 필드 키는 RTDB visit 레코드 키와 정확히 일치 → 저장 시 환자정보 페이지에 그대로 표시된다.
type Field =
  | { id: string; label: string; type: "text" | "textarea" | "number" | "date" }
  | { id: string; label: string; type: "select" | "radio"; options: string[] }
  | { id: string; label: string; type: "scale"; max: number };

const SECTIONS: { n: string; title: string; fields: Field[] }[] = [
  { n: "01", title: "내원 정보", fields: [
    { id: "방문일", label: "방문일", type: "date" },
    { id: "진료유형", label: "진료유형", type: "radio", options: ["초진", "재진"] },
    { id: "진료과", label: "진료과", type: "text" },
  ]},
  { n: "02", title: "주호소 (CC)", fields: [
    { id: "주호소(CC)", label: "주호소 / 내원 사유", type: "textarea" },
    { id: "증상 발생시기_경과", label: "증상 발생시기 / 경과", type: "text" },
    { id: "통증부위", label: "통증 부위", type: "text" },
    { id: "통증점수", label: "통증 점수 (NRS)", type: "scale", max: 10 },
  ]},
  { n: "03", title: "생체징후", fields: [
    { id: "수축기혈압", label: "수축기혈압 (mmHg)", type: "number" },
    { id: "이완기혈압", label: "이완기혈압 (mmHg)", type: "number" },
    { id: "맥박", label: "맥박 (bpm)", type: "number" },
    { id: "호흡", label: "호흡 (/min)", type: "number" },
    { id: "체온", label: "체온 (℃)", type: "number" },
    { id: "SpO2", label: "SpO₂ (%)", type: "number" },
    { id: "의식상태", label: "의식상태", type: "select", options: ["명료", "기면", "혼미", "반혼수", "혼수"] },
    { id: "낙상위험", label: "낙상위험", type: "select", options: ["하", "중", "고"] },
  ]},
  { n: "04", title: "간호 / 기타", fields: [
    { id: "금일 복약 여부", label: "금일 복약 여부", type: "select", options: ["복용", "미복용", "해당없음"] },
    { id: "최근 발열_감염노출", label: "최근 발열 / 감염 노출", type: "text" },
    { id: "최근 검사_예정 검사", label: "최근 / 예정 검사", type: "text" },
    { id: "보고 필요", label: "의료진 보고 필요", type: "radio", options: ["N", "Y"] },
    { id: "간호 관찰사항", label: "간호 관찰사항", type: "textarea" },
    { id: "작성 간호사", label: "작성 간호사", type: "text" },
  ]},
];

const today = () => new Date().toISOString().slice(0, 10);

export default function IntakePage() {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [pid, setPid] = useState("");
  const [form, setForm] = useState<Record<string, unknown>>({ 방문일: today() });
  const [saved, setSaved] = useState<null | "ok" | "err">(null);
  const [busy, setBusy] = useState(false);
  const [role, setRole] = useState<Role>("patient");
  const [selfName, setSelfName] = useState("");
  const [selfRoom, setSelfRoom] = useState("");

  useEffect(() => {
    getMe().then((m) => {
      setRole(m.role);
      if (m.role !== "patient") {
        getPatients().then((ps) => { setPatients(ps); if (ps[0]) setPid(ps[0].id); }).catch(() => {});
      }
    }).catch(() => setRole("patient"));
  }, []);

  const patient = useMemo(() => patients.find((p) => p.id === pid), [patients, pid]);
  // 환자 선택 시 진료과를 그 환자의 주 진료과로 프리필(미입력 시)
  useEffect(() => {
    if (patient) setForm((f) => ({ ...f, 진료과: f.진료과 || patient["주 진료과"] || "" }));
  }, [patient]);

  const set = (id: string, v: unknown) => { setForm((f) => ({ ...f, [id]: v })); setSaved(null); };

  async function submit() {
    if (role === "patient") {
      if (!selfName.trim()) { setSaved("err"); return; }
      setBusy(true);
      try {
        await submitIntake({ name: selfName, room: selfRoom, sections: form });
        setSaved("ok");
      } catch { setSaved("err"); }
      finally { setBusy(false); }
      return;
    }
    // ↓ 기존 의료진/관리자 로직(addVisit) 그대로
    if (!pid || busy) return;
    setBusy(true);
    try {
      const r = await addVisit(pid, { ...form, 방문일: form.방문일 || today() });
      setSaved(r?.ok ? "ok" : "err");
      if (r?.ok) setForm({ 방문일: today(), 진료과: patient?.["주 진료과"] || "" });
    } catch { setSaved("err"); }
    finally { setBusy(false); }
  }

  return (
    <div className="p-7 max-w-[880px] pb-28">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="eyebrow">문진 · 외래방문</div>
          <h1 className="text-[26px] font-bold mt-1">외래 방문 문진</h1>
          <p className="text-[13px] text-ink-3 mt-1">저장하면 선택한 환자의 새 외래방문 기록으로 추가되고, 환자정보 페이지 최근 생체징후에 반영됩니다.</p>
        </div>
        {role === "patient" ? (
          <div className="card p-4 grid sm:grid-cols-2 gap-3">
            <label className="block">
              <span className="text-[12px] font-semibold text-ink-3">성명 *</span>
              <input value={selfName} onChange={(e) => setSelfName(e.target.value)} className="field" placeholder="본인 성명" />
            </label>
            <label className="block">
              <span className="text-[12px] font-semibold text-ink-3">병실</span>
              <input value={selfRoom} onChange={(e) => setSelfRoom(e.target.value)} className="field" placeholder="예: 101" />
            </label>
          </div>
        ) : (
          <div className="flex flex-col items-end gap-1.5">
            <select className="field w-[240px]" value={pid} onChange={(e) => setPid(e.target.value)}>
              {patients.map((p) => <option key={p.id} value={p.id}>{p.성명} · {p.id}</option>)}
            </select>
            {pid && <Link href={`/patients/${pid}`} className="text-[12.5px] text-teal hover:underline">{patient?.성명} 환자정보 보기 →</Link>}
          </div>
        )}
      </div>

      <div className="flex flex-col gap-4 mt-6">
        {SECTIONS.map((sec) => (
          <section key={sec.n} className="card p-6 rise">
            <div className="flex items-center gap-3 mb-4">
              <span className="mono text-[12px] text-teal-600 bg-teal-soft rounded-md px-2 py-0.5 font-semibold">{sec.n}</span>
              <h2 className="text-[16px] font-bold">{sec.title}</h2>
            </div>
            <div className="grid grid-cols-2 gap-x-5 gap-y-4">
              {sec.fields.map((f) => (
                <div key={f.id} className={f.type === "textarea" ? "col-span-2" : ""}>
                  <label className="block text-[12.5px] font-semibold text-ink-2 mb-1.5">{f.label}</label>
                  <FieldInput f={f} value={form[f.id]} set={set} />
                </div>
              ))}
            </div>
          </section>
        ))}
      </div>

      <div className="fixed bottom-0 left-[248px] right-0 bg-surface/90 backdrop-blur border-t border-line px-7 py-3.5 flex items-center justify-end gap-3">
        {saved === "ok" && <span className="pill bg-green-soft text-green"><span className="dot bg-green" /> 외래방문 기록 추가됨</span>}
        {saved === "err" && <span className="pill bg-red-soft text-red"><span className="dot bg-red" /> 저장 실패</span>}
        <button onClick={submit} disabled={busy || (role === "patient" ? !selfName.trim() : !pid)}
          className="bg-teal text-white font-semibold text-[14px] px-6 py-2.5 rounded-xl hover:bg-teal-600 transition-colors disabled:opacity-40 shadow-[0_6px_16px_-6px_rgba(12,163,154,.6)]">
          {busy ? "저장 중…" : role === "patient" ? "문진표 제출" : "외래방문 기록 저장"}
        </button>
      </div>
    </div>
  );
}

function FieldInput({ f, value, set }: { f: Field; value: unknown; set: (id: string, v: unknown) => void }) {
  if (f.type === "text" || f.type === "number" || f.type === "date")
    return <input className="field" type={f.type} value={(value as string) ?? ""} onChange={(e) => set(f.id, e.target.value)} />;
  if (f.type === "textarea")
    return <textarea className="field min-h-[78px] resize-y" value={(value as string) ?? ""} onChange={(e) => set(f.id, e.target.value)} />;
  if (f.type === "select")
    return (
      <select className="field" value={(value as string) ?? ""} onChange={(e) => set(f.id, e.target.value)}>
        <option value="">선택</option>
        {f.options.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    );
  if (f.type === "radio")
    return (
      <div className="flex flex-wrap gap-2">
        {f.options.map((o) => {
          const on = value === o;
          return <button key={o} type="button" onClick={() => set(f.id, o)}
            className={`px-3.5 py-1.5 rounded-lg text-[13px] font-medium border transition-colors ${on ? "bg-teal text-white border-teal" : "bg-surface-2 text-ink-2 border-line hover:border-teal"}`}>{o}</button>;
        })}
      </div>
    );
  if (f.type === "scale") {
    const cur = Number(value ?? -1);
    return (
      <div className="flex flex-wrap gap-1.5">
        {Array.from({ length: f.max + 1 }, (_, i) => (
          <button key={i} type="button" onClick={() => set(f.id, String(i))}
            className={`w-8 h-8 rounded-lg mono text-[13px] font-semibold border transition-colors ${cur === i ? "bg-teal text-white border-teal" : "bg-surface-2 text-ink-2 border-line hover:border-teal"}`}>{i}</button>
        ))}
      </div>
    );
  }
  return null;
}
