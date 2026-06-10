import { describe, it, expect } from "vitest";
import { ageFrom } from "./patient";

describe("ageFrom (생년월일 → 만 나이)", () => {
  it("미존재/빈값/비문자열 → null", () => {
    expect(ageFrom(undefined)).toBeNull();
    expect(ageFrom("")).toBeNull();
    expect(ageFrom(123 as unknown)).toBeNull();
  });
  it("잘못된 날짜 → null", () => {
    expect(ageFrom("not-a-date")).toBeNull();
  });
  it("미래 생년월일 → null (음수 가드)", () => {
    expect(ageFrom("2999-01-01")).toBeNull();
  });
  it("정상 생년월일 → 합리적 양수 나이", () => {
    const age = ageFrom("1958-03-15");
    expect(age).not.toBeNull();
    expect(age!).toBeGreaterThanOrEqual(60);
    expect(age!).toBeLessThan(120);
  });
});
