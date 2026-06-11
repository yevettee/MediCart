import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import IntakeForm from "./IntakeForm";

// NOTE(B-INTAKE-07): 현재 IntakeForm 은 필수/형식 검증 없음 — 카탈로그 기대(검증)와 차이.
// submit() 내부에서 !pid || busy 만 확인할 뿐, 드롭다운 미입력·수치 필드 비수치 입력을
// 전혀 차단하지 않는다. ④ 문진표 UX 개선 과제와 연계, 검증 추가는 별도 작업으로 남긴다.

vi.mock("@/lib/api", () => ({
  addVisit: vi.fn(),
  // 프리필(a570011): IntakeForm 마운트 시 getPatient(pid) 호출 → null 이면 기본 빈 폼 유지.
  getPatient: vi.fn().mockResolvedValue(null),
}));

import { addVisit } from "@/lib/api";
const mockAddVisit = addVisit as ReturnType<typeof vi.fn>;

describe("IntakeForm 동작 검증 (B-INTAKE-07)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("pid 없으면 저장 버튼이 비활성화되고 addVisit 미호출", async () => {
    // pid가 빈 문자열이면 !pid 가드에 의해 submit이 막힌다.
    const onSaved = vi.fn();
    render(<IntakeForm pid="" patientName="김환자" onSaved={onSaved} />);

    const btn = screen.getByRole("button", { name: /문진 저장 후 다음/ });
    expect(btn).toBeDisabled();

    await userEvent.click(btn);
    expect(mockAddVisit).not.toHaveBeenCalled();
    expect(onSaved).not.toHaveBeenCalled();
  });

  it("유효한 pid 와 필드 미입력 상태로 저장 → addVisit 호출됨(검증 없음)", async () => {
    // NOTE(B-INTAKE-07): 필수 필드가 비어 있어도 addVisit이 호출된다 — 검증 부재 확인.
    mockAddVisit.mockResolvedValue({ ok: true });
    const onSaved = vi.fn();
    render(<IntakeForm pid="P001" patientName="김환자" onSaved={onSaved} />);

    const btn = screen.getByRole("button", { name: /문진 저장 후 다음/ });
    expect(btn).not.toBeDisabled();

    await userEvent.click(btn);
    expect(mockAddVisit).toHaveBeenCalledTimes(1);
    // 첫 번째 인수는 pid
    expect(mockAddVisit.mock.calls[0][0]).toBe("P001");
  });

  it("저장 성공 시 onSaved 콜백 호출", async () => {
    mockAddVisit.mockResolvedValue({ ok: true });
    const onSaved = vi.fn();
    render(<IntakeForm pid="P001" patientName="김환자" onSaved={onSaved} />);

    await userEvent.click(screen.getByRole("button", { name: /문진 저장 후 다음/ }));
    await vi.waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
  });

  it("저장 실패(ok 아님) 시 오류 메시지 표시 및 onSaved 미호출", async () => {
    mockAddVisit.mockResolvedValue({ ok: false });
    const onSaved = vi.fn();
    render(<IntakeForm pid="P001" patientName="김환자" onSaved={onSaved} />);

    await userEvent.click(screen.getByRole("button", { name: /문진 저장 후 다음/ }));
    await vi.waitFor(() => expect(screen.getByText("저장 실패")).toBeInTheDocument());
    expect(onSaved).not.toHaveBeenCalled();
  });

  it("저장 API 예외 시 오류 메시지 표시 및 onSaved 미호출", async () => {
    mockAddVisit.mockRejectedValue(new Error("network error"));
    const onSaved = vi.fn();
    render(<IntakeForm pid="P001" patientName="김환자" onSaved={onSaved} />);

    await userEvent.click(screen.getByRole("button", { name: /문진 저장 후 다음/ }));
    await vi.waitFor(() => expect(screen.getByText("저장 실패")).toBeInTheDocument());
    expect(onSaved).not.toHaveBeenCalled();
  });

  it("onCancel 제공 시 건너뛰기 버튼 노출 → 클릭하면 콜백 호출", async () => {
    const onCancel = vi.fn();
    render(<IntakeForm pid="P001" onCancel={onCancel} />);

    const skipBtn = screen.getByRole("button", { name: /건너뛰기/ });
    expect(skipBtn).toBeInTheDocument();
    await userEvent.click(skipBtn);
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("onCancel 미제공 시 건너뛰기 버튼 미노출", () => {
    render(<IntakeForm pid="P001" />);
    expect(screen.queryByRole("button", { name: /건너뛰기/ })).not.toBeInTheDocument();
  });

  it("patientName 제공 시 헤더에 이름 표시", () => {
    render(<IntakeForm pid="P001" patientName="이영희" />);
    expect(screen.getByText("이영희님 문진표")).toBeInTheDocument();
  });

  it("prefillDept 제공 시 진료과 드롭다운 초기값 반영", () => {
    render(<IntakeForm pid="P001" prefillDept="내과" />);
    // SECTIONS 내 진료과 select 가 prefillDept 값으로 초기화돼야 한다.
    const selects = screen.getAllByRole("combobox") as HTMLSelectElement[];
    const deptSelect = selects.find((s) => s.value === "내과");
    expect(deptSelect).toBeDefined();
    expect(deptSelect!.value).toBe("내과");
  });

  it("NOTE(B-INTAKE-07): 드롭다운 미선택(공백) 상태로 저장 시 addVisit에 빈 값 전달됨 — 검증 없음", async () => {
    // NOTE(B-INTAKE-07): 이 테스트는 현재 검증 부재를 명시적으로 기록한다.
    // 진료유형·진료과 등 드롭다운이 선택되지 않아도 addVisit 이 그대로 호출된다.
    mockAddVisit.mockResolvedValue({ ok: true });
    render(<IntakeForm pid="P002" />);

    await userEvent.click(screen.getByRole("button", { name: /문진 저장 후 다음/ }));
    expect(mockAddVisit).toHaveBeenCalledTimes(1);
    const payload = mockAddVisit.mock.calls[0][1] as Record<string, unknown>;
    // 진료유형·진료과는 초기 form 상태에 설정되지 않으므로 undefined 또는 ""
    expect(payload["진료유형"] === undefined || payload["진료유형"] === "").toBe(true);
    expect(payload["진료과"] === undefined || payload["진료과"] === "").toBe(true);
  });
});
