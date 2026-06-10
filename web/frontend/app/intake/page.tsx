"use client";
import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import { getPatients, Patient, addVisit, getMe, submitIntake } from "@/lib/api";
import type { Role } from "@/lib/auth";
import { today, IntakeFields, prefillFromVisit } from "@/components/IntakeForm";

function IntakeInner() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const qrPid = searchParams.get("pid") ?? "";

  const [patients, setPatients] = useState<Patient[]>([]);
  const [pid, setPid] = useState(qrPid);
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
        getPatients().then((ps) => {
          setPatients(ps);
          if (!qrPid && ps[0]) setPid(ps[0].id);
        }).catch(() => {});
      }
    }).catch(() => setRole("patient"));
  }, [qrPid]);

  /* qrPid가 바뀌면(새 QR 스캔) pid·폼 즉시 리셋 */
  useEffect(() => {
    if (qrPid) {
      setPid(qrPid);
      setForm({ 방문일: today() });
      setSaved(null);
    }
  }, [qrPid]);

  /* QR 경유 진입 시 새 환자 스캔 감지 → 해당 환자 문진표로 자동 전환 */
  useEffect(() => {
    if (!qrPid) return;
    let initialized = false;
    let currentPid = qrPid;

    async function poll() {
      try {
        const r = await fetch("/api/display/patient", { cache: "no-store" });
        if (!r.ok) return;
        const { pid: newPid } = await r.json();
        if (!initialized) { initialized = true; currentPid = newPid ?? qrPid; return; }
        if (newPid && newPid !== currentPid) {
          currentPid = newPid;
          // router.push는 같은 페이지에서 리마운트를 보장하지 않으므로 강제 이동
          window.location.href = `/intake?pid=${newPid}`;
        }
      } catch { /* ignore */ }
    }

    const timer = setInterval(poll, 2000);
    return () => clearInterval(timer);
  }, [qrPid, router]);

  const patient = useMemo(() => patients.find((p) => p.id === pid), [patients, pid]);
  // 기존 환자 선택 시 최근 외래방문 값으로 폼 프리필(기존 상태 수정 — 매번 새로 안 써도 됨).
  useEffect(() => {
    if (patient) setForm(prefillFromVisit(patient));
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
      if (r?.ok) {
        setSaved("ok");
        setForm({ 방문일: today(), 진료과: patient?.["주 진료과"] || "" });
        // QR 경유로 왔으면 저장 후 대기 화면으로 복귀
        if (qrPid) setTimeout(() => { window.location.href = "/display"; }, 1500);
      } else {
        setSaved("err");
      }
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

      <IntakeFields form={form} set={set} />

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

export default function IntakePage() {
  return (
    <Suspense fallback={null}>
      <IntakeInner />
    </Suspense>
  );
}
