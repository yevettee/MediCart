import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { roleForToken, requiredRoleForRoute, roleAtLeast, landingFor } from "@/lib/auth";

// systemd/기동 env 로 양쪽(Flask·Next)이 동일 토큰 공유. 미설정 시 admin 토큰을 모름 → fail-closed.
const STAFF = process.env.INTEL_AUTH_TOKEN;
const ADMIN = process.env.INTEL_ADMIN_TOKEN;

export function middleware(req: NextRequest) {
  const role = roleForToken(req.cookies.get("intel_auth")?.value, STAFF, ADMIN);
  const need = requiredRoleForRoute(req.nextUrl.pathname);
  if (roleAtLeast(role, need)) return NextResponse.next();

  const url = req.nextUrl.clone();
  if (role === "patient") {
    url.pathname = "/login";
    url.searchParams.set("next", req.nextUrl.pathname);
  } else {
    url.pathname = landingFor(role); // 의료진이 관리자 라우트 접근 → 자기 랜딩으로
    url.search = "";
  }
  return NextResponse.redirect(url);
}

export const config = {
  matcher: ["/((?!login|_next/static|_next/image|favicon.ico|.*\\.).*)"],
};
