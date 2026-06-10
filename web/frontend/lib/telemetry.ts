import type { AmrSnapshot } from "./api";

/** RTDB 스냅샷의 나이(ms). stamp 는 밀리초로 들어온다(Date.now() 와 같은 단위).
 *  미존재·비수치·0 이하 → Infinity(STALE). 미래 stamp(시계 스큐) → 0 으로 클램프. */
export function snapAgeMs(stamp?: number): number {
  if (typeof stamp !== "number" || !Number.isFinite(stamp) || stamp <= 0) return Infinity;
  return Math.max(0, Date.now() - stamp);
}

/** thresholdMs(기본 3s) 이내 수신이면 LIVE. */
export function isLive(stamp?: number, thresholdMs = 3000): boolean {
  return snapAgeMs(stamp) < thresholdMs;
}

/** 도킹 중인 로봇의 pose(=amcl_pose) 가 그 로봇의 홈. 미도킹·pose 없음·null → null. */
export function robotHome(snap: AmrSnapshot): { x: number; y: number; yaw?: number } | null {
  if (snap && snap.dock?.is_docked && snap.pose) {
    return { x: snap.pose.x, y: snap.pose.y, yaw: snap.pose.yaw };
  }
  return null;
}
