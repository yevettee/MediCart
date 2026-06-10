"use client";
import { useState } from "react";
import { addVisit } from "@/lib/api";

type Field =
  | { id: string; label: string; type: "text" | "textarea" | "number" | "date" }
  | { id: string; label: string; type: "select" | "radio"; options: string[] }
  | { id: string; label: string; type: "scale"; max: number };

export const SECTIONS: { n: string; title: string; fields: Field[] }[] = [
  { n: "01", title: "내원 정보", fields: [
    { id: "방문일", label: "방문일", type: "date" },
    { id: "진료유형", label: "진료유형", type: "select", options: ["초진", "재진"] },
    { id: "진료과", label: "진료과", type: "select", options: [
      "내과", "외과", "정형외과", "신경외과", "신경과", "흉부외과", "성형외과",
      "소아청소년과", "산부인과", "정신건강의학과", "피부과", "안과", "이비인후과",
      "비뇨의학과", "가정의학과", "응급의학과", "재활의학과", "마취통증의학과",
      "영상의학과", "진단검사의학과",
    ] },
  ]},
  { n: "02", title: "주요 증상", fields: [
    { id: "주호소(CC)", label: "주요 증상 / 내원 사유", type: "textarea" },
    { id: "증상 발생시기_경과", label: "증상 발생시기 / 경과", type: "text" },
    { id: "통증부위", label: "통증 부위", type: "text" },
    { id: "통증점수", label: "통증 점수 (0~10)", type: "scale", max: 10 },
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
    { id: "최근 검사_예정 검사", label: "최근 / 예정 검사", type: "date" },
    { id: "보고 필요", label: "의료진 보고 필요", type: "select", options: ["예", "아니오"] },
    { id: "간호 관찰사항", label: "간호 관찰사항", type: "textarea" },
    { id: "작성 간호사", label: "작성 간호사", type: "text" },
  ]},
];

// 구 코드 호환 별칭(main RoundsIntakeOverlay 계열에서 참조 가능).
export const INTAKE_SECTIONS = SECTIONS;

export const today = () => new Date().toISOString().slice(0, 10);

export function FieldInput(
  { f, value, set }: { f: Field; value: unknown; set: (id: string, v: unknown) => void },
) {
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

// 공유 폼 본문(섹션 카드) — /intake 페이지가 자체 레이아웃에서 사용.
export function IntakeFields(
  { form, set }: { form: Record<string, unknown>; set: (id: string, v: unknown) => void },
) {
  return (
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
  );
}

type Props = {
  pid: string;
  patientName?: string;
  prefillDept?: string;
  onSaved?: () => void;    // 저장 성공 시 (순회: 다음 호실)
  onCancel?: () => void;   // 건너뛰기(선택)
};

/** 오버레이용 자기완결 의료진 문진 폼(카드 모달) — pid 의 새 외래방문 기록 추가. */
export default function IntakeForm({ pid, patientName, prefillDept, onSaved, onCancel }: Props) {
  const [form, setForm] = useState<Record<string, unknown>>({ 방문일: today(), 진료과: prefillDept || "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(false);
  const set = (id: string, v: unknown) => { setForm((f) => ({ ...f, [id]: v })); setErr(false); };

  async function submit() {
    if (!pid || busy) return;
    setBusy(true); setErr(false);
    try {
      const r = await addVisit(pid, { ...form, 방문일: form.방문일 || today() });
      if (r?.ok) onSaved?.();
      else setErr(true);
    } catch { setErr(true); }
    finally { setBusy(false); }
  }

  return (
    <div className="w-full max-w-[820px] mx-auto bg-surface text-ink rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[88vh]">
      <div className="px-6 py-4 border-b border-line flex items-center justify-between shrink-0">
        <div>
          <div className="eyebrow">문진 · 외래방문</div>
          <h2 className="text-[20px] font-bold mt-0.5">{patientName ? `${patientName}님 문진표` : "외래 방문 문진"}</h2>
        </div>
        <span className="text-[12.5px] text-ink-3 font-mono">{pid}</span>
      </div>

      <div className="px-6 py-4 overflow-y-auto">
        <div className="flex flex-col gap-4">
          {SECTIONS.map((sec) => (
            <section key={sec.n} className="card p-5">
              <div className="flex items-center gap-3 mb-3.5">
                <span className="mono text-[12px] text-teal-600 bg-teal-soft rounded-md px-2 py-0.5 font-semibold">{sec.n}</span>
                <h3 className="text-[15px] font-bold">{sec.title}</h3>
              </div>
              <div className="grid grid-cols-2 gap-x-5 gap-y-3.5">
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
      </div>

      <div className="px-6 py-3.5 border-t border-line flex items-center justify-end gap-3 shrink-0">
        {err && <span className="pill bg-red-soft text-red"><span className="dot bg-red" /> 저장 실패</span>}
        {onCancel && (
          <button onClick={onCancel} disabled={busy}
            className="px-5 py-2.5 rounded-xl border border-line text-ink-2 font-semibold text-[14px] disabled:opacity-40">
            건너뛰기
          </button>
        )}
        <button onClick={submit} disabled={busy || !pid}
          className="bg-teal text-white font-semibold text-[14px] px-6 py-2.5 rounded-xl hover:bg-teal-600 transition-colors disabled:opacity-40">
          {busy ? "저장 중…" : "문진 저장 후 다음"}
        </button>
      </div>
    </div>
  );
}
