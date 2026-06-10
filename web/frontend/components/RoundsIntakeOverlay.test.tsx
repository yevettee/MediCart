// 커버리지 경계(이 파일):
//   검증됨 — B-TRIG-03(patrol_intake_mission {stops,home} 발행), B-PHASE-01(진입 시 ns로 patrol phase 폴링).
//   DEFERRED(후속 태스크) — B-INTAKE-06(스캔 타임아웃 부재중 결과), B-PHASE-05(요약 집계),
//     그리고 전체 phase 전이 시퀀스(starting→moving→scanning→intake/absent→returning→summary).
//     사유: QR 스캔 이벤트·RTDB 'arrived' 신호로 상태머신을 다단계 구동해야 해 brittle.
//     ABSENT_SECONDS·results·advancingRef 경로는 컴포넌트 통합/수동 검증으로 이관.
import { render, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import RoundsIntakeOverlay from "./RoundsIntakeOverlay";

// Mock @/lib/api — all names the component imports
vi.mock("@/lib/api", () => ({
  pushMission: vi.fn().mockResolvedValue({ ok: true }),
  startPatrol: vi.fn().mockResolvedValue({ ok: true, id: "m1" }),
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

import { pushMission, startPatrol, getPatrolPhase } from "@/lib/api";

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
      expect(startPatrol).toHaveBeenCalledWith(
        "robot3",
        expect.objectContaining({
          stops: expect.any(Array),
          home: dock,
        })
      )
    );
    // 해피패스: startPatrol(깨끗한 시작) 1회, fallback pushMission 은 호출 안 됨
    expect(startPatrol).toHaveBeenCalledTimes(1);
    expect(pushMission).not.toHaveBeenCalled();
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
    await waitFor(() => expect(startPatrol).toHaveBeenCalled());
    const callArgs = (startPatrol as ReturnType<typeof vi.fn>).mock.calls[0];
    const payload = callArgs[1] as { stops: unknown[]; home: unknown };
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
    expect(startPatrol).not.toHaveBeenCalled();
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
