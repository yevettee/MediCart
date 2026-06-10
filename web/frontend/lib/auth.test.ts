import { describe, it, expect } from "vitest";
import { requiredRoleForRoute, NAV_ROLES, roleAtLeast } from "./auth";

describe("home '/' 라우트는 의료진(staff)부터 접근 가능", () => {
  it("requiredRoleForRoute('/') === 'staff' (관리자 전용 아님)", () => {
    expect(requiredRoleForRoute("/")).toBe("staff");
  });
  it("NAV_ROLES['/'] === 'staff' — 사이드바 홈 메뉴가 의료진에게 노출", () => {
    expect(NAV_ROLES["/"]).toBe("staff");
  });
  it("staff 가 홈 라우트 가드를 통과 (간호사 투약·순회 문진 진입)", () => {
    expect(roleAtLeast("staff", requiredRoleForRoute("/"))).toBe(true);
  });
});

describe("관리자 전용 라우트는 그대로 admin 유지", () => {
  it("/console 은 admin", () => {
    expect(requiredRoleForRoute("/console")).toBe("admin");
    expect(roleAtLeast("staff", requiredRoleForRoute("/console"))).toBe(false);
  });
});
