import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import Sidebar from "./Sidebar";

vi.mock("@/lib/api", () => ({
  getMe: vi.fn(),
  logout: vi.fn(),
}));
import { getMe } from "@/lib/api";

const renderSidebar = () =>
  render(
    <Sidebar
      collapsed={false}
      mobileOpen={true}
      onCloseMobile={() => {}}
      onToggleCollapse={() => {}}
    />,
  );

describe("Sidebar RBAC 메뉴 노출 (X-RBAC-03)", () => {
  beforeEach(() => vi.clearAllMocks());

  it("staff: 홈·환자정보·문진표·처치실 노출, 관리자 콘솔·QR스캔 미노출", async () => {
    (getMe as ReturnType<typeof vi.fn>).mockResolvedValue({ authed: true, role: "staff" });
    renderSidebar();
    await waitFor(() => expect(screen.getByText("홈")).toBeInTheDocument());
    expect(screen.getByText("환자 정보")).toBeInTheDocument();
    expect(screen.getByText("문진표")).toBeInTheDocument();
    expect(screen.getByText("처치실")).toBeInTheDocument();
    expect(screen.queryByText("관리자 콘솔")).not.toBeInTheDocument();
    expect(screen.queryByText("QR 스캔")).not.toBeInTheDocument();
  });

  it("admin: 관리자 콘솔 포함 전체 노출", async () => {
    (getMe as ReturnType<typeof vi.fn>).mockResolvedValue({ authed: true, role: "admin" });
    renderSidebar();
    await waitFor(() => expect(screen.getByText("관리자 콘솔")).toBeInTheDocument());
    expect(screen.getByText("홈")).toBeInTheDocument();
    expect(screen.getByText("환자 정보")).toBeInTheDocument();
    expect(screen.getByText("문진표")).toBeInTheDocument();
    expect(screen.getByText("처치실")).toBeInTheDocument();
    expect(screen.getByText("QR 스캔")).toBeInTheDocument();
  });

  it("patient: 문진표만 노출, 관리자 콘솔·홈·환자정보·처치실 미노출", async () => {
    (getMe as ReturnType<typeof vi.fn>).mockResolvedValue({ authed: false, role: "patient" });
    renderSidebar();
    await waitFor(() => expect(screen.getByText("문진표")).toBeInTheDocument());
    expect(screen.queryByText("관리자 콘솔")).not.toBeInTheDocument();
    expect(screen.queryByText("홈")).not.toBeInTheDocument();
    expect(screen.queryByText("환자 정보")).not.toBeInTheDocument();
    expect(screen.queryByText("처치실")).not.toBeInTheDocument();
    expect(screen.queryByText("QR 스캔")).not.toBeInTheDocument();
  });
});
