import { describe, it, expect } from "vitest";
import { nearestArrival, type ArrivalTarget } from "./follow";

const T: ArrivalTarget[] = [
  { key: "pharmacy", label: "약품실", x: -9, y: -9 },
  { key: "t101_1", label: "101호 1번", x: -12, y: -5 },
];

describe("nearestArrival", () => {
  it("pose 없으면 null", () => {
    expect(nearestArrival(undefined, T, null)).toBeNull();
  });
  it("타겟 비면 null", () => {
    expect(nearestArrival({ x: -9, y: -9 }, [], null)).toBeNull();
  });
  it("1.0m 이내면 도착(최근접)", () => {
    expect(nearestArrival({ x: -9.5, y: -9 }, T, null)?.key).toBe("pharmacy");
  });
  it("1.0m 초과 + 직전 미도착이면 null", () => {
    expect(nearestArrival({ x: -9, y: -7.9 }, T, null)).toBeNull();
  });
  it("히스테리시스: 도착 후 1.2m까지 유지", () => {
    expect(nearestArrival({ x: -9, y: -7.85 }, T, "pharmacy")?.key).toBe("pharmacy");
  });
  it("히스테리시스: 1.2m 초과 시 해제", () => {
    expect(nearestArrival({ x: -9, y: -7.7 }, T, "pharmacy")).toBeNull();
  });
  it("여러 타겟 중 가장 가까운 것 선택", () => {
    expect(nearestArrival({ x: -12, y: -5.4 }, T, null)?.key).toBe("t101_1");
  });
});
