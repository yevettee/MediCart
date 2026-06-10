import { describe, expect, it } from "vitest";
import { PATROL_STOPS, decideAfterScan, nextStop } from "./patrol";

describe("decideAfterScan", () => {
  it("needs intake when not done", () => {
    expect(decideAfterScan({ intake_done: false })).toBe("intake");
  });
  it("skips when already done", () => {
    expect(decideAfterScan({ intake_done: true })).toBe("skip");
  });
  it("treats missing flag as needing intake", () => {
    expect(decideAfterScan({})).toBe("intake");
  });
  it("unknown when patient missing", () => {
    expect(decideAfterScan(null)).toBe("unknown");
  });
});

describe("nextStop", () => {
  it("advances to next index", () => {
    expect(nextStop(0, 2)).toBe(1);
  });
  it("returns 'return' after last stop", () => {
    expect(nextStop(1, 2)).toBe("return");
  });
});

describe("PATROL_STOPS", () => {
  it("is the two 101호 beds in order", () => {
    expect(PATROL_STOPS).toEqual(["t101_1", "t101_2"]);
  });
});
