import { render, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import RoundsIntakeOverlay from "./RoundsIntakeOverlay";

// Mock @/lib/api — all names the component imports
vi.mock("@/lib/api", () => ({
  pushMission: vi.fn().mockResolvedValue({ ok: true }),
  getPatrolPhase: vi.fn().mockResolvedValue({ phase: "starting", stop: {} }),
  sendPatrolAdvance: vi.fn().mockResolvedValue({ ok: true }),
  getRooms: vi.fn().mockResolvedValue({ rooms: {} }),
  getPatient: vi.fn().mockResolvedValue({ id: "P-2026-0001", 성명: "홍길동" }),
  verifyIdentify: vi.fn().mockResolvedValue({ status: "identified", match: true }),
  setIntakeStatus: vi.fn().mockResolvedValue({ ok: true }),
}));

// Mock child components that use browser APIs (camera, etc.)
vi.mock("@/components/QrScanner", () => ({
  default: () => <div data-testid="qr-scanner-stub" />,
}));

vi.mock("@/components/IntakeForm", () => ({
  default: () => <div data-testid="intake-form-stub" />,
}));

import { pushMission, getPatrolPhase } from "@/lib/api";

const stops = [
  { key: "t101_1", label: "101-1", room: "101-1", x: -4.2, y: -1.5, yaw: 0 },
];
const dock = { x: -7.4, y: -3.1, yaw: 0 };

describe("RoundsIntakeOverlay (B-TRIG-03 / B-PHASE-01)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("B-TRIG-03: 시작 시 patrol_intake_mission {stops, home} 1회 발행", async () => {
    render(
      <RoundsIntakeOverlay
        active={true}
        ns="robot3"
        stops={stops}
        dock={dock}
        onExit={() => {}}
      />
    );
    await waitFor(() =>
      expect(pushMission).toHaveBeenCalledWith(
        "robot3",
        "patrol_intake_mission",
        expect.objectContaining({
          stops: expect.any(Array),
          home: dock,
        })
      )
    );
    // Should only be called once for the mission trigger
    expect(pushMission).toHaveBeenCalledTimes(1);
  });

  it("B-TRIG-03: stops 페이로드는 {x,y,yaw,room,label} 형태로 매핑됨", async () => {
    render(
      <RoundsIntakeOverlay
        active={true}
        ns="robot3"
        stops={stops}
        dock={dock}
        onExit={() => {}}
      />
    );
    await waitFor(() => expect(pushMission).toHaveBeenCalled());
    const callArgs = (pushMission as ReturnType<typeof vi.fn>).mock.calls[0];
    const payload = callArgs[2] as { stops: unknown[]; home: unknown };
    expect(payload.stops).toHaveLength(1);
    expect(payload.stops[0]).toMatchObject({
      x: -4.2,
      y: -1.5,
      yaw: 0,
      room: "101-1",
      label: "101-1",
    });
  });

  it("B-PHASE-01: ns로 patrol phase 폴링 (POLL_MS=1000ms interval)", async () => {
    render(
      <RoundsIntakeOverlay
        active={true}
        ns="robot3"
        stops={stops}
        dock={dock}
        onExit={() => {}}
      />
    );
    await waitFor(() => expect(getPatrolPhase).toHaveBeenCalledWith("robot3"), {
      timeout: 2000,
    });
  });

  it("active=false → pushMission 안 함", async () => {
    render(
      <RoundsIntakeOverlay
        active={false}
        ns="robot3"
        stops={stops}
        dock={dock}
        onExit={() => {}}
      />
    );
    // Wait a tick to confirm no async calls were dispatched
    await new Promise((r) => setTimeout(r, 50));
    expect(pushMission).not.toHaveBeenCalled();
  });

  it("active=false → getPatrolPhase 안 함", async () => {
    render(
      <RoundsIntakeOverlay
        active={false}
        ns="robot3"
        stops={stops}
        dock={dock}
        onExit={() => {}}
      />
    );
    await new Promise((r) => setTimeout(r, 1200));
    expect(getPatrolPhase).not.toHaveBeenCalled();
  });
});
