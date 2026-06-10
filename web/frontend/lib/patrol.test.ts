import { describe, expect, it } from "vitest";
import { PATROL_STOPS, decideAfterScan, nextStop, acceptArrival } from "./patrol";

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

describe("acceptArrival (엄격순서 + ready + async잠금)", () => {
  const base = { polledPhase: "arrived", polledIdx: 0, lastIdx: -1, ready: true, arriving: false };
  it("ready 아니면 거부", () => {
    expect(acceptArrival({ ...base, ready: false })).toBe(false);
  });
  it("arriving(잠금) 중이면 거부", () => {
    expect(acceptArrival({ ...base, arriving: true })).toBe(false);
  });
  it("phase!=='arrived' 거부", () => {
    expect(acceptArrival({ ...base, polledPhase: "idle" })).toBe(false);
  });
  it("idx 누락 거부", () => {
    expect(acceptArrival({ ...base, polledIdx: undefined })).toBe(false);
  });
  it("다음 순번(idx===lastIdx+1)만 수용", () => {
    expect(acceptArrival({ ...base, lastIdx: -1, polledIdx: 0 })).toBe(true);
    expect(acceptArrival({ ...base, lastIdx: 0, polledIdx: 1 })).toBe(true);
  });
  it("중복(같은 idx)·점프(+2) 거부", () => {
    expect(acceptArrival({ ...base, lastIdx: 0, polledIdx: 0 })).toBe(false);
    expect(acceptArrival({ ...base, lastIdx: 0, polledIdx: 2 })).toBe(false);
  });
});
