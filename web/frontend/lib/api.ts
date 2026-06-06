// 백엔드(Flask) 호출 헬퍼.
// NEXT_PUBLIC_API_BASE 미설정 → dev 기본 :5000. ""(빈문자열) → 같은 오리진(/api, 프로덕션 터널).
const _envBase = process.env.NEXT_PUBLIC_API_BASE;
export const API_BASE = _envBase === undefined ? "http://localhost:5000" : _envBase;

async function getJSON<T>(path: string): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, { cache: "no-store", credentials: "include" });
  if (!r.ok) throw new Error(`${path} → ${r.status}`);
  return r.json();
}

export async function login(password: string): Promise<boolean> {
  const r = await fetch(`${API_BASE}/api/login`, {
    method: "POST", credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });
  return r.ok;
}

export async function logout() {
  await fetch(`${API_BASE}/api/logout`, { method: "POST", credentials: "include" });
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
  mode?: string;
  state?: string;
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

export type MapMeta = { available: boolean; resolution?: number; origin?: number[] };

export async function saveIntake(payload: Record<string, unknown>) {
  const r = await fetch(`${API_BASE}/api/intake`, {
    method: "POST", credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return r.json();
}
