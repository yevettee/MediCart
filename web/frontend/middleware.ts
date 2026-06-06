import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Flask가 발급하는 쿠키와 동일 토큰. systemd 환경변수 INTEL_AUTH_TOKEN로 양쪽 동기화.
// env 필수 — 소스에 기본 토큰 하드코딩하지 않는다. 미설정이면 모두 차단(fail-closed).
const TOKEN = process.env.INTEL_AUTH_TOKEN;

export function middleware(req: NextRequest) {
  if (TOKEN && req.cookies.get("intel_auth")?.value === TOKEN) return NextResponse.next();
  const url = req.nextUrl.clone();
  url.pathname = "/login";
  url.searchParams.set("next", req.nextUrl.pathname);
  return NextResponse.redirect(url);
}

// /login·정적파일(_next, 확장자 있는 파일)·favicon 제외한 모든 페이지 보호.
export const config = {
  matcher: ["/((?!login|_next/static|_next/image|favicon.ico|.*\\.).*)"],
};
