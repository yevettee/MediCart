// RBAC 순수 로직 — 백엔드 auth.py 와 동일 표(미들웨어·사이드바·로그인·문진 공용).
export type Role = "patient" | "staff" | "admin";

export const ROLE_RANK: Record<Role, number> = { patient: 0, staff: 1, admin: 2 };

export function roleAtLeast(role: Role, min: Role): boolean {
  return ROLE_RANK[role] >= ROLE_RANK[min];
}

// 라우트별 최소 등급 (백엔드 required_role_for_path 와 일치)
export function requiredRoleForRoute(path: string): Role {
  if (path === "/intake" || path.startsWith("/intake/")) return "patient";
  if (path === "/") return "staff"; // 홈(간호사 투약·순회 문진) — 의료진부터
  if (path.startsWith("/patients") || path.startsWith("/ocr")) return "staff";
  return "admin"; // "/console", 그 외 보호 라우트
}

// 사이드바 메뉴 노출용(각 href 의 최소 등급)
export const NAV_ROLES: Record<string, Role> = {
  "/": "staff",
  "/console": "admin",
  "/control": "admin",
  "/map": "admin",
  "/debug": "admin",
  "/patients": "staff",
  "/intake": "patient",
  "/ocr": "staff",
};

export function landingFor(role: Role): string {
  return role === "admin" ? "/" : role === "staff" ? "/patients" : "/intake";
}

// 쿠키 토큰 → 역할 (미들웨어용). 토큰은 호출측이 env에서 주입.
export function roleForToken(token: string | undefined, staffTok?: string, adminTok?: string): Role {
  if (adminTok && token === adminTok) return "admin";
  if (staffTok && token === staffTok) return "staff";
  return "patient";
}

export const ROLE_LABEL: Record<Role, string> = { patient: "환자", staff: "의료진", admin: "관리자" };
