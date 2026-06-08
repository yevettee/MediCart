import { NextResponse } from "next/server";

const FLASK = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:5000";
const TOKEN = process.env.INTEL_AUTH_TOKEN ?? "";

export async function GET() {
  try {
    // 1. Firebase에서 현재 표시 환자 ID 가져오기 (인증 불필요 엔드포인트)
    const pidResp = await fetch(`${FLASK}/api/display/current`, {
      cache: "no-store",
    });
    if (!pidResp.ok) return NextResponse.json({ pid: "", patient: null });
    const { pid } = await pidResp.json();
    if (!pid) return NextResponse.json({ pid: "", patient: null });

    // 2. 환자 데이터 가져오기 — Cookie 대신 Authorization 사용 (Next.js fetch가 Cookie 헤더를 차단할 수 있음)
    const patResp = await fetch(`${FLASK}/api/patients/${pid}`, {
      headers: { Authorization: `Bearer ${TOKEN}` },
      cache: "no-store",
    });
    if (!patResp.ok) return NextResponse.json({ pid, patient: null });
    const patient = await patResp.json();

    return NextResponse.json({ pid, patient });
  } catch {
    return NextResponse.json({ pid: "", patient: null }, { status: 500 });
  }
}
