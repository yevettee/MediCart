"use client";
import { useEffect, useState } from "react";
import { getPatients, Patient, saveIntake } from "@/lib/api";

type Field =
  | { id: string; label: string; type: "text" | "textarea" | "number" }
  | { id: string; label: string; type: "radio" | "select"; options: string[] }
  | { id: string; label: string; type: "check"; options: string[] }
  | { id: string; label: string; type: "scale"; max: number };

const SECTIONS: { title: string; n: string; fields: Field[] }[] = [
  { n: "01", title: "기본 정보", fields: [
    { id: "name", label: "성명", type: "text" },
    { id: "birth", label: "생년월일", type: "text" },
    { id: "sex", label: "성별", type: "radio", options: ["남", "여"] },
    { id: "contact", label: "연락처", type: "text" },
    { id: "insurance", label: "보험 유형", type: "select", options: ["건강보험", "의료급여", "산재", "자보", "기타"] },
  ]},
  { n: "02", title: "내원 목적 (주호소)", fields: [
    { id: "cc", label: "가장 큰 이유 / 증상", type: "textarea" },
    { id: "onset", label: "증상 시작 시기", type: "text" },
    { id: "pain", label: "통증 정도", type: "scale", max: 10 },
    { id: "assoc", label: "동반 증상 (발열·구토·어지러움 등)", type: "text" },
  ]},
  { n: "03", title: "과거 병력", fields: [
    { id: "pmh", label: "진단받은 질환", type: "check", options: ["고혈압", "당뇨병", "이상지질혈증", "심장질환", "뇌혈관질환", "폐질환", "간질환", "신장질환", "위장관질환", "갑상선질환", "암", "정신건강", "경련/뇌전증", "자가면역질환"] },
    { id: "surgery", label: "수술 및 입원력", type: "text" },
  ]},
  { n: "04", title: "약물 및 알레르기", fields: [
    { id: "meds", label: "현재 복용 중인 약물", type: "textarea" },
    { id: "drugAllergy", label: "약물 알레르기 (약물명/반응)", type: "text" },
    { id: "foodAllergy", label: "음식 알레르기", type: "text" },
    { id: "anticoag", label: "항응고제·항혈소판제 복용", type: "radio", options: ["없음", "있음"] },
  ]},
  { n: "05", title: "가족력", fields: [
    { id: "family", label: "부모·형제·자녀 질환 (관계 기재)", type: "textarea" },
  ]},
  { n: "06", title: "사회력 / 생활습관", fields: [
    { id: "smoke", label: "흡연", type: "radio", options: ["비흡연", "과거흡연", "현재흡연"] },
    { id: "alcohol", label: "음주", type: "radio", options: ["없음", "월 1회 이하", "주 1~2회", "주 3회 이상"] },
    { id: "exercise", label: "운동 / 활동", type: "text" },
  ]},
  { n: "07", title: "계통별 문진", fields: [
    { id: "ros", label: "현재 있는 증상", type: "check", options: ["발열", "체중변화", "두통", "어지러움", "시야이상", "가슴통증", "호흡곤란", "기침", "복통", "소화불량", "배뇨이상", "관절통", "피부발진", "불면", "우울/불안"] },
  ]},
  { n: "10", title: "기능 및 안전 평가", fields: [
    { id: "gait", label: "보행", type: "radio", options: ["독립 보행", "보조 필요", "휠체어/와상"] },
    { id: "fall", label: "최근 낙상 경험", type: "radio", options: ["없음", "있음"] },
    { id: "comm", label: "의사소통 / 통역 필요", type: "text" },
  ]},
  { n: "11", title: "의료진 전달 사항", fields: [
    { id: "note", label: "기타 알림 사항", type: "textarea" },
  ]},
];

export default function IntakePage() {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [pid, setPid] = useState("");
  const [form, setForm] = useState<Record<string, unknown>>({});
  const [saved, setSaved] = useState<null | "ok" | "err">(null);

  useEffect(() => { getPatients().then((ps) => { setPatients(ps); if (ps[0]) setPid(ps[0].id); }).catch(() => {}); }, []);

  const set = (id: string, v: unknown) => { setForm((f) => ({ ...f, [id]: v })); setSaved(null); };
  const toggle = (id: string, opt: string) => setForm((f) => {
    const cur = (f[id] as string[]) || []; setSaved(null);
    return { ...f, [id]: cur.includes(opt) ? cur.filter((x) => x !== opt) : [...cur, opt] };
  });

  async function submit() {
    try { const r = await saveIntake({ patientId: pid, ...form }); setSaved(r?.ok ? "ok" : "err"); }
    catch { setSaved("err"); }
  }

  return (
    <div className="p-7 max-w-[860px] pb-24">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="eyebrow">문진표</div>
          <h1 className="text-[26px] font-bold mt-1">초진 환자 종합 문진표</h1>
        </div>
        <select className="field w-[220px]" value={pid} onChange={(e) => setPid(e.target.value)}>
          {patients.map((p) => <option key={p.id} value={p.id}>{p.성명} · {p.id}</option>)}
        </select>
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
                <div key={f.id} className={f.type === "textarea" || f.type === "check" ? "col-span-2" : ""}>
                  <label className="block text-[12.5px] font-semibold text-ink-2 mb-1.5">{f.label}</label>
                  <FieldInput f={f} value={form[f.id]} set={set} toggle={toggle} />
                </div>
              ))}
            </div>
          </section>
        ))}
      </div>

      {/* 저장 바 */}
      <div className="fixed bottom-0 left-[248px] right-0 bg-surface/90 backdrop-blur border-t border-line px-7 py-3.5 flex items-center justify-end gap-3">
        {saved === "ok" && <span className="pill bg-green-soft text-green"><span className="dot bg-green" /> 저장되었습니다</span>}
        {saved === "err" && <span className="pill bg-red-soft text-red"><span className="dot bg-red" /> 저장 실패</span>}
        <button onClick={submit} disabled={!pid}
          className="bg-teal text-white font-semibold text-[14px] px-6 py-2.5 rounded-xl hover:bg-teal-600 transition-colors disabled:opacity-40 shadow-[0_6px_16px_-6px_rgba(12,163,154,.6)]">
          문진표 저장
        </button>
      </div>
    </div>
  );
}

function FieldInput({ f, value, set, toggle }: { f: Field; value: unknown; set: (id: string, v: unknown) => void; toggle: (id: string, o: string) => void }) {
  if (f.type === "text" || f.type === "number")
    return <input className="field" type={f.type} value={(value as string) || ""} onChange={(e) => set(f.id, e.target.value)} />;
  if (f.type === "textarea")
    return <textarea className="field min-h-[78px] resize-y" value={(value as string) || ""} onChange={(e) => set(f.id, e.target.value)} />;
  if (f.type === "select")
    return (
      <select className="field" value={(value as string) || ""} onChange={(e) => set(f.id, e.target.value)}>
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
  if (f.type === "check")
    return (
      <div className="flex flex-wrap gap-2">
        {f.options.map((o) => {
          const on = ((value as string[]) || []).includes(o);
          return <button key={o} type="button" onClick={() => toggle(f.id, o)}
            className={`px-3 py-1.5 rounded-lg text-[12.5px] font-medium border transition-colors ${on ? "bg-teal-soft text-teal-600 border-teal" : "bg-surface-2 text-ink-2 border-line hover:border-line-strong"}`}>{o}</button>;
        })}
      </div>
    );
  if (f.type === "scale") {
    const cur = Number(value ?? -1);
    return (
      <div className="flex flex-wrap gap-1.5">
        {Array.from({ length: f.max + 1 }, (_, i) => (
          <button key={i} type="button" onClick={() => set(f.id, i)}
            className={`w-8 h-8 rounded-lg mono text-[13px] font-semibold border transition-colors ${cur === i ? "bg-teal text-white border-teal" : "bg-surface-2 text-ink-2 border-line hover:border-teal"}`}>{i}</button>
        ))}
      </div>
    );
  }
  return null;
}
