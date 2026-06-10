import { render, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import RoundOverlay from "./RoundOverlay";

vi.mock("@/lib/api", () => ({
  getNurseCartPhase: vi.fn().mockResolvedValue({ phase: "idle" }),
  nurseCartRoundDone: vi.fn().mockResolvedValue({ ok: true }),
}));

import { getNurseCartPhase } from "@/lib/api";

// Using real timers: fake timers proved unreliable with waitFor+promise polling in this jsdom setup.
// RoundOverlay calls tick() immediately on mount then every 2000ms — the immediate call
// is detectable within a short waitFor timeout without advancing any timer.

describe("RoundOverlay phase 폴링 (A-PHASE-01)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("active=true → ns로 phase 폴링 호출 (즉시)", async () => {
    // Component calls tick() synchronously in useEffect on mount (before the interval fires)
    render(<RoundOverlay active={true} ns="robot6" onExit={() => {}} />);
    await waitFor(() => expect(getNurseCartPhase).toHaveBeenCalledWith("robot6"), {
      timeout: 1000,
    });
  });

  it("active=false → 폴링 안 함", async () => {
    render(<RoundOverlay active={false} ns="robot6" onExit={() => {}} />);
    // Wait a tick to confirm the effect guard prevents any call
    await new Promise((r) => setTimeout(r, 50));
    expect(getNurseCartPhase).not.toHaveBeenCalled();
  });

  it("active=true → 항상 지정된 ns 로만 호출", async () => {
    render(<RoundOverlay active={true} ns="robot6" onExit={() => {}} />);
    await waitFor(() => expect(getNurseCartPhase).toHaveBeenCalled(), { timeout: 1000 });
    const calls = (getNurseCartPhase as ReturnType<typeof vi.fn>).mock.calls;
    calls.forEach((call) => expect(call[0]).toBe("robot6"));
  });
});
