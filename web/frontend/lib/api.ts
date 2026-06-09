// 백엔드(Flask) 호출 헬퍼.
// NEXT_PUBLIC_API_BASE 미설정 → dev 기본 :5000. ""(빈문자열) → 같은 오리진(/api, 프로덕션 터널).
import type { Role } from "@/lib/auth";

const _envBase = process.env.NEXT_PUBLIC_API_BASE;
export const API_BASE = _envBase === undefined ? "http://localhost:5000" : _envBase;

async function getJSON<T>(path: string): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, { cache: "no-store", credentials: "include" });
  if (!r.ok) throw new Error(`${path} → ${r.status}`);
  return r.json();
}

export async function login(password: string): Promise<Role | null> {
  const r = await fetch(`${API_BASE}/api/login`, {
    method: "POST", credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });
  if (!r.ok) return null;
  const d = await r.json().catch(() => ({}));
  return (d.role as Role) ?? null;
}

export async function getMe(): Promise<{ authed: boolean; role: Role }> {
  try {
    const r = await fetch(`${API_BASE}/api/me`, { cache: "no-store", credentials: "include" });
    if (!r.ok) return { authed: false, role: "patient" };
    return await r.json();
  } catch {
    return { authed: false, role: "patient" };
  }
}

export async function submitIntake(payload: { name: string; room?: string; sections: Record<string, unknown> }) {
  const r = await fetch(`${API_BASE}/api/intake`, {
    method: "POST", credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new Error(`POST /api/intake → ${r.status}`);
  return r.json();
}

export async function logout() {
  // 로그인과 동일 오리진(Flask)으로 — Flask set_cookie 와 같은 속성으로 delete_cookie 해야
  // intel_auth 가 실제로 지워진다. (Next 자체 라우트로 지우면 다른 오리진이라 안 지워짐 → 즉시 재로그인 버그)
  await fetch(`${API_BASE}/api/logout`, { method: "POST", credentials: "include" }).catch(() => {});
}

export type Patient = {
  id: string;
  성명: string;
  나이?: number | string;
  성별?: string;
  혈액형?: string;
  "약물 알레르기"?: string | null;
  "음식/기타 알레르기"?: string | null;
  주치의?: string;
  "주 진료과"?: string;
  visits?: Visit[];
  intake?: unknown;
  intake_done?: boolean;
  [k: string]: unknown;
};

export type Visit = {
  방문일?: string;
  "주호소(CC)"?: string;
  수축기혈압?: number | string;
  이완기혈압?: number | string;
  맥박?: number | string;
  호흡?: number | string;
  체온?: number | string;
  SpO2?: number | string;
  통증점수?: number | string;
  낙상위험?: string;
  의식상태?: string;
  [k: string]: unknown;
};

export type AmrSnapshot = {
  source: string;
  pose?: { x: number; y: number; yaw: number };
  vel?: { lin: number; ang: number };
  battery?: { pct: number; voltage: number };
  dock?: { is_docked: boolean };
  imu?: { yaw_rate: number };
  mode?: string;
  state?: string;
  online?: boolean;
  scan?: { angle_min: number; angle_inc: number; range_max: number; ranges: (number | null)[] };
  stamp?: number;
} | null;

export const getPatients = () => getJSON<Patient[]>("/api/patients");
export const getPatient = (id: string) => getJSON<Patient>(`/api/patients/${id}`);
export const getAmrs = () => getJSON<Record<string, AmrSnapshot>>("/api/amrs");
export const getRooms = () => getJSON<Record<string, unknown>>("/api/rooms");
export const getMapMeta = () => getJSON<MapMeta>("/api/map");

export async function saveMode(action: "start" | "stop" | "clear", mode: string, params?: Record<string, unknown>) {
  const r = await fetch(`${API_BASE}/api/mode`, {
    method: "POST", credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, mode, params: params || {} }),
  });
  return r.json();
}

// ── 순회 문진 회차 플래그 ────────────────────────────────────────────────────
export async function resetIntakeRound(): Promise<{ ok: boolean; count: number }> {
  const r = await fetch(`${API_BASE}/api/patrol/reset`, {
    method: "POST", credentials: "include",
  });
  if (!r.ok) throw new Error(`/api/patrol/reset → ${r.status}`);
  return r.json();
}

export async function markIntakeDone(pid: string): Promise<{ ok: boolean }> {
  const r = await fetch(`${API_BASE}/api/patrol/intake-done`, {
    method: "POST", credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pid }),
  });
  if (!r.ok) throw new Error(`/api/patrol/intake-done → ${r.status}`);
  return r.json();
}

export type MapMeta = { available: boolean; resolution?: number; origin?: number[] };

// 문진 입력 → 새 외래방문 기록 추가(visits[0]에 prepend, 최근 생체징후도 갱신)
export async function addVisit(pid: string, data: Record<string, unknown>) {
  const r = await fetch(`${API_BASE}/api/patients/${pid}/visits`, {
    method: "POST", credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return r.json();
}

// 환자 정보 직접 수정(info/vitals 부분 갱신) → 갱신된 환자 반환
export async function updatePatient(
  pid: string,
  patch: { info?: Record<string, unknown>; vitals?: Record<string, unknown> },
): Promise<Patient> {
  const r = await fetch(`${API_BASE}/api/patients/${pid}`, {
    method: "PUT", credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!r.ok) throw new Error(`PUT /api/patients/${pid} → ${r.status}`);
  return r.json();
}

// ── 로봇 명령 하달 (mission_pool) ──────────────────────────────────────────
export type Mission = { id: string; action: string; mode?: string; params?: Record<string, unknown>; status: string; ts: number };
export type GotoTarget = { label: string; x: number; y: number; yaw?: number; dock_after?: boolean };
export const getTargets = () => getJSON<{ targets: Record<string, GotoTarget> }>("/api/targets");

// 시스템 액션(dock/undock…)은 mode 생략, 모드 액션(start/stop)은 mode 지정, clear는 mode 불요.
// params: goto 등 좌표 기반 미션에 {x,y,yaw,dock_after,label} 전달.
export async function pushMission(
  ns: string, action: string,
  params?: Record<string, unknown>, mode?: string,
) {
  const r = await fetch(`${API_BASE}/api/robots/${ns}/missions`, {
    method: "POST", credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, params: params || {}, mode }),
  });
  return r.json() as Promise<{ ok: boolean; id?: string; error?: string }>;
}

export const getMissions = (ns: string) => getJSON<{ missions: Mission[] }>(`/api/robots/${ns}/missions`);

export async function clearMissions(ns: string) {
  const r = await fetch(`${API_BASE}/api/robots/${ns}/missions/clear`, {
    method: "POST", credentials: "include",
  });
  return r.json() as Promise<{ ok: boolean; error?: string }>;
}

export type RobotHealth = {
  ping_ok?: boolean; ping_ms?: number | null;
  create3?: boolean; turtlebot4?: boolean; ip?: string; ts?: number;
};
export const getRobotsHealth = () => getJSON<Record<string, RobotHealth>>("/api/robots/health");

export async function cameraRequest(ns: string, on: boolean) {
  await fetch(`${API_BASE}/api/camera/${ns}/request`, {
    method: "POST", credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ on }),
  }).catch(() => {});
}

export async function ocr(blob: Blob): Promise<{ text: string }> {
  const fd = new FormData();
  fd.append("image", blob, "capture.png");
  const r = await fetch(`${API_BASE}/api/ocr`, { method: "POST", credentials: "include", body: fd });
  if (!r.ok) throw new Error(`/api/ocr → ${r.status}`);
  return r.json();
}

/** OCR 완료 → RTDB {ns}/nurse_cart/ocr_done = true (기본 robot6). */
export async function setOcrDone(ns = "robot6"): Promise<void> {
  const r = await fetch(`${API_BASE}/api/ocr/done`, {
    method: "POST", credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ns }),
  });
  if (!r.ok) throw new Error(`/api/ocr/done → ${r.status}`);
}

export type Injection = {
  약품명?: string;
  약물명?: string;
  용량?: string;
  투약경로?: string;
  투약시간?: string;
  status?: "pending" | "confirmed" | "mismatch";
  verified_at?: number;
  ocr_text?: string;
  [k: string]: unknown;
};

export const getInjections = (pid: string) =>
  getJSON<Record<string, Injection>>(`/api/patients/${pid}/injections`);

export const getDisplayPatient = () =>
  getJSON<{ pid: string }>("/api/display/current");

export async function setDisplayPatient(pid: string): Promise<{ ok: boolean; pid: string }> {
  const r = await fetch(`${API_BASE}/api/display/current`, {
    method: "POST", credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pid }),
  });
  if (!r.ok) throw new Error(`/api/display/current → ${r.status}`);
  return r.json();
}


export async function verifyInjection(
  pid: string,
  inj_id: string,
  ocr_text: string,
  prescription: string,
): Promise<{ ok: boolean; match: boolean; status: string; reason: string }> {
  const r = await fetch(`${API_BASE}/api/patients/${pid}/injections/${inj_id}/verify`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ocr_text, prescription }),
  });
  if (!r.ok) throw new Error(`/api/patients/${pid}/injections/${inj_id}/verify → ${r.status}`);
  return r.json();
}

export async function confirmInjection(
  pid: string,
  inj_id: string,
): Promise<{ ok: boolean; status: string }> {
  const r = await fetch(`${API_BASE}/api/patients/${pid}/injections/${inj_id}/confirm`, {
    method: "POST",
    credentials: "include",
  });
  if (!r.ok) throw new Error(`/api/patients/${pid}/injections/${inj_id}/confirm → ${r.status}`);
  return r.json();
}
