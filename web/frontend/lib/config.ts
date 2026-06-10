// 빌드 시 common/robot.env 의 ROBOT_NAMESPACE → NEXT_PUBLIC_PRIMARY_NS 로 주입.
export const PRIMARY_NS = process.env.NEXT_PUBLIC_PRIMARY_NS || "robot3";
// 웹은 두 AMR을 보여주므로 SECONDARY는 PRIMARY의 나머지(robot3↔robot6).
export const SECONDARY_NS =
  process.env.NEXT_PUBLIC_SECONDARY_NS || (PRIMARY_NS === "robot6" ? "robot3" : "robot6");

// 모드별 전담 로봇 (고정 배정).
export const NURSE_CART_NS = "robot6";   // 간호사 투약(시나리오 B) — robot6 전담
export const PATROL_NS = "robot3";       // 순회 문진 — robot3 전담
