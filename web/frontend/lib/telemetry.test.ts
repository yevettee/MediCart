import { describe, it, expect } from "vitest";
import { snapAgeMs, isLive, robotHome } from "./telemetry";

describe("snapAgeMs (stamp ms 기준 나이)", () => {
  it("미존재/0/음수 stamp → Infinity(STALE)", () => {
    expect(snapAgeMs(undefined)).toBe(Infinity);
    expect(snapAgeMs(0)).toBe(Infinity);
    expect(snapAgeMs(-5)).toBe(Infinity);
    expect(snapAgeMs(Number.NaN)).toBe(Infinity);
  });
  it("최근 stamp(ms) → 0 이상 작은 값", () => {
    const age = snapAgeMs(Date.now() - 1000);
    expect(age).toBeGreaterThanOrEqual(900);
    expect(age).toBeLessThan(1500);
  });
  it("미래 stamp(시계 스큐) → 0 으로 클램프(STALE 아님)", () => {
    expect(snapAgeMs(Date.now() + 10_000)).toBe(0);
  });
});

describe("isLive (임계 비교)", () => {
  it("3s 이내 → LIVE, 그 밖 → STALE", () => {
    expect(isLive(Date.now() - 500)).toBe(true);
    expect(isLive(Date.now() - 9000)).toBe(false);
    expect(isLive(undefined)).toBe(false);
  });
  it("임계값 인자 적용(5s)", () => {
    expect(isLive(Date.now() - 4000, 5000)).toBe(true);
    expect(isLive(Date.now() - 6000, 5000)).toBe(false);
  });
});

describe("robotHome (도킹 pose → 홈)", () => {
  const base = { source: "robot3", stamp: 1 };
  it("도킹+pose → 그 pose", () => {
    expect(robotHome({ ...base, dock: { is_docked: true }, pose: { x: -7.4, y: -3.1, yaw: 0 } }))
      .toEqual({ x: -7.4, y: -3.1, yaw: 0 });
  });
  it("미도킹 → null", () => {
    expect(robotHome({ ...base, dock: { is_docked: false }, pose: { x: 1, y: 2, yaw: 0 } })).toBeNull();
  });
  it("pose 없음 → null", () => {
    expect(robotHome({ ...base, dock: { is_docked: true } })).toBeNull();
  });
  it("null 스냅샷 → null", () => {
    expect(robotHome(null)).toBeNull();
  });
});
