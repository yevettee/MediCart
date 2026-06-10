"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { getPatients, Patient } from "@/lib/api";
import { ageFrom } from "@/lib/patient";

export default function PatientsPage() {
  const [list, setList] = useState<Patient[]>([]);
  const [err, setErr] = useState(false);
  useEffect(() => { getPatients().then(setList).catch(() => setErr(true)); }, []);

  return (
    <div className="p-7 max-w-[1100px]">
      <div className="eyebrow">회진 보조</div>
      <h1 className="text-[26px] font-bold mt-1">환자 정보</h1>
      <p className="text-[13.5px] text-ink-2 mt-1.5">로봇이 환자 위치에 도착하면 해당 환자 상세가 표시됩니다.</p>

      {err && <p className="mt-6 text-red text-sm">백엔드 연결 실패 — Flask(:5000)가 실행 중인지 확인하세요.</p>}

      <div className="grid grid-cols-2 gap-4 mt-6 rise">
        {list.map((p) => {
          const allergy = (p["약물 알레르기"] && p["약물 알레르기"] !== "없음") ? p["약물 알레르기"] : null;
          const age = ageFrom(p.생년월일);
          return (
            <Link key={p.id} href={`/patients/${p.id}`} className="card card-hover p-5 block">
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-2.5">
                    <span className="text-[18px] font-bold">{p.성명}</span>
                    <span className="text-[13px] text-ink-3">{p.성별}{age != null && ` · ${age}세`} · {p.혈액형}</span>
                  </div>
                  <div className="mono text-[12px] text-ink-3 mt-1">{p.id}</div>
                </div>
                {allergy && (
                  <span className="pill bg-red-soft text-red"><span className="dot bg-red" /> 알레르기</span>
                )}
              </div>
              <div className="flex gap-2 mt-4 text-[12.5px]">
                <span className="pill bg-teal-soft text-teal-600">{p["주 진료과"]}</span>
                <span className="pill bg-surface-2 text-ink-2 border-line">주치의 {p.주치의}</span>
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
