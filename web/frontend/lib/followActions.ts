import { saveMode, pushMission, API_BASE } from "@/lib/api";

// ns 로봇의 dock.is_docked 가 want이 될 때까지 SSE로 대기. 타임아웃 시 resolve(false).
export function waitDockState(ns: string, want: boolean, timeoutMs = 20000): Promise<boolean> {
  return new Promise((resolve) => {
    const es = new EventSource(`${API_BASE}/api/stream`, { withCredentials: true });
    let done = false;
    const finish = (ok: boolean) => {
      if (done) return;
      done = true;
      es.close();
      clearTimeout(timer);
      resolve(ok);
    };
    const timer = setTimeout(() => finish(false), timeoutMs);
    es.onmessage = (e) => {
      try {
        const d = JSON.parse(e.data);
        if (d?.source === ns && d?.dock && d.dock.is_docked === want) finish(true);
      } catch { /* ignore parse */ }
    };
  });
}

// 회진 시작: docked면 undock(+완료 대기) 후 round 모드 start.
// undock 대기 타임아웃 시 false 반환(round는 이미 시작됨); 정상 시 true.
export async function startFollow(ns: string, isDocked: boolean): Promise<boolean> {
  let undockedOk = true;
  if (isDocked) {
    await pushMission(ns, "undock");
    undockedOk = await waitDockState(ns, false, 20000);
  }
  await saveMode("start", "round");
  return undockedOk;
}

// 홈 복귀: round 중지 → dock 타겟으로 goto(dock_after). nav_executor가 Nav2 이동 후 도킹.
export async function returnHome(
  ns: string,
  dock: { x: number; y: number; yaw?: number },
): Promise<void> {
  await saveMode("stop", "round");
  await pushMission(ns, "goto", { x: dock.x, y: dock.y, yaw: dock.yaw ?? 0, dock_after: true });
}
