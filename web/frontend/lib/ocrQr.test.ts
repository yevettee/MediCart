import { describe, expect, it } from "vitest";
import { decideQr } from "./ocrQr";

const inj = (id: string, status?: string, 약품명?: string) => ({ id, status, 약품명 });

describe("decideQr", () => {
  it("스캔 PID가 선택 환자와 다르면 blocked_patient", () => {
    const d = decideQr("P-2024-0002", "P-2024-0001", [inj("a", "confirmed")]);
    expect(d).toEqual({ kind: "blocked_patient", scannedPid: "P-2024-0002" });
  });

  it("미confirmed 약품이 있으면 blocked_meds (미준비 목록)", () => {
    const d = decideQr("P-2024-0001", "P-2024-0001", [
      inj("a", "confirmed", "세파졸린"),
      inj("b", "pending", "수액"),
      inj("c", "mismatch", "포도당"),
    ]);
    expect(d).toEqual({
      kind: "blocked_meds",
      unready: [
        { name: "수액", status: "pending" },
        { name: "포도당", status: "mismatch" },
      ],
    });
  });

  it("status 없으면 pending 으로 표시", () => {
    const d = decideQr("P-2024-0001", "P-2024-0001", [inj("a")]);
    expect(d).toEqual({ kind: "blocked_meds", unready: [{ name: "a", status: "pending" }] });
  });

  it("전부 confirmed 면 complete (injCount)", () => {
    const d = decideQr("P-2024-0001", "P-2024-0001", [inj("a", "confirmed"), inj("b", "confirmed")]);
    expect(d).toEqual({ kind: "complete", injCount: 2 });
  });

  it("주사 목록이 비면 complete injCount 0", () => {
    const d = decideQr("P-2024-0001", "P-2024-0001", []);
    expect(d).toEqual({ kind: "complete", injCount: 0 });
  });
});
