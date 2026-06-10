// 환자 파생값 — 생년월일(YYYY-MM-DD)에서 만 나이 계산. 목록·상세 공용.
export function ageFrom(birth?: unknown): number | null {
  if (typeof birth !== "string" || !birth) return null;
  const b = new Date(birth);
  if (isNaN(b.getTime())) return null;
  const n = new Date();
  let a = n.getFullYear() - b.getFullYear();
  if (n.getMonth() < b.getMonth() || (n.getMonth() === b.getMonth() && n.getDate() < b.getDate())) a--;
  return a >= 0 && a < 150 ? a : null;
}
