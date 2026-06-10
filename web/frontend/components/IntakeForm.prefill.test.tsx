import { describe, it, expect } from "vitest";
import { prefillFromVisit, today } from "./IntakeForm";
import type { Patient } from "@/lib/api";

describe("prefillFromVisit (기존 방문 값 프리필)", () => {
  it("방문이력 없으면 방문일=오늘 + 진료과 빈값", () => {
    const f = prefillFromVisit(null);
    expect(f.방문일).toBe(today());
    expect(f.진료과).toBe("");
  });

  it("진료과 폴백: 주 진료과", () => {
    const p = { id: "P-2026-0001", 성명: "x", "주 진료과": "내과" } as Patient;
    expect(prefillFromVisit(p).진료과).toBe("내과");
  });

  it("prefillDept 우선", () => {
    const p = { id: "P-2026-0001", 성명: "x", "주 진료과": "내과" } as Patient;
    expect(prefillFromVisit(p, "외과").진료과).toBe("외과");
  });

  it("최근 visit 값 복사 · 방문일은 오늘 · 등록번호 제외", () => {
    const p = {
      id: "P-2026-0001", 성명: "x",
      visits: [{ 방문일: "2026-01-01", 등록번호: "P-2026-0001", "주호소(CC)": "기침", 수축기혈압: 120 }],
    } as unknown as Patient;
    const f = prefillFromVisit(p);
    expect(f["주호소(CC)"]).toBe("기침");
    expect(f.수축기혈압).toBe(120);
    expect(f.방문일).toBe(today());          // 옛 방문일 아님
    expect(f.등록번호).toBeUndefined();      // 제어키 제외
  });
});
