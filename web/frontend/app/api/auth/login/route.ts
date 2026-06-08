import { NextRequest, NextResponse } from "next/server";

const FLASK = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:5000";
const INTEL_TOKEN = process.env.INTEL_AUTH_TOKEN ?? "";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const resp = await fetch(`${FLASK}/api/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await resp.json();
    if (!data.ok) return NextResponse.json({ ok: false }, { status: 401 });

    // 쿠키를 Next.js(3001)에서 직접 발급 — iOS Safari 크로스포트 쿠키 이슈 해결
    const res = NextResponse.json({ ok: true });
    res.cookies.set("intel_auth", INTEL_TOKEN, {
      httpOnly: true,
      sameSite: "lax",
      maxAge: 60 * 60 * 12,
      path: "/",
    });
    return res;
  } catch {
    return NextResponse.json({ ok: false }, { status: 500 });
  }
}
