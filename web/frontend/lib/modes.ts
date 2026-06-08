export type ModeMeta = { label: string; color: string; soft: string };

export const MODE: Record<string, ModeMeta> = {
  round:  { label: "회진보조", color: "#0ca39a", soft: "var(--teal-soft)" },
  patrol: { label: "순찰",    color: "#2f74e0", soft: "var(--blue-soft)" },
  errand: { label: "지시",    color: "#d4870f", soft: "var(--amber-soft)" },
  guide:  { label: "가이드",  color: "#7559d6", soft: "#efeafb" },
  intake: { label: "문진",    color: "#18a259", soft: "var(--green-soft)" },
  idle:   { label: "대기",    color: "#8597a5", soft: "var(--surface-2)" },
};

// 모드/상태 문자열 → 표시 메타 (Phase2 모드명 + 기존 fod state 모두 수용)
export function modeOf(s?: string): ModeMeta {
  if (!s) return MODE.idle;
  const k = String(s).toLowerCase();
  if (MODE[k]) return MODE[k];
  if (k.includes("patrol")) return MODE.patrol;
  if (k.includes("round") || k.includes("follow")) return MODE.round;
  if (["idle", "waiting", "docked", "dock"].includes(k)) return MODE.idle;
  return { label: String(s), color: "#51616f", soft: "var(--surface-2)" };
}
