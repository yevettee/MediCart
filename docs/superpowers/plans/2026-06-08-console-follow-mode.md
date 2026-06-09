# 회진(추종) 풀스크린 모드 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 홈(`/`) 최상단 배너 → 재확인 → 회진(추종) 모드 시작(docked면 자동 undock), 풀스크린 안내 + 약품실/101호 1·2번 1m 근접 시 "OO에 도착" 표시 + 우하단 '홈 위치로 복귀'(→ dock).

**Architecture:** `web/frontend` 전용. 로봇/백엔드 무변경 — 기존 `saveMode`(round 모드, `{PRIMARY_NS}/cmd`에 기록)·`pushMission(ns,…)`(undock/goto)·`getTargets`·SSE `/api/stream`(`{source,pose,dock}`) 재사용. 순수 근접판정(`nearestArrival`)은 vitest 단위테스트, 부작용 헬퍼·UI는 수동 E2E.

**Tech Stack:** Next.js(App Router) + React + TypeScript + Tailwind, vitest(신규, 순수함수 테스트용).

스펙: `docs/superpowers/specs/2026-06-08-console-follow-mode-design.md`

---

## File Structure

- **Create** `web/frontend/lib/follow.ts` — 순수: 타입(`Pt`,`ArrivalTarget`) + `nearestArrival`(의존성 0).
- **Create** `web/frontend/lib/follow.test.ts` — vitest 단위테스트(순수함수만).
- **Create** `web/frontend/lib/followActions.ts` — 부작용: `waitDockState`/`startFollow`/`returnHome`(api 호출·SSE).
- **Create** `web/frontend/components/FollowOverlay.tsx` — 풀스크린(자가 SSE 구독, 텍스트, 복귀 버튼).
- **Modify** `web/frontend/app/page.tsx` — 최상단 '회진 모드' 배너 + 재확인 + FollowOverlay 마운트.
- **Modify** `web/frontend/package.json` — `vitest` devDep + `"test":"vitest run"`.

---

## Task 1: vitest 도입 + 순수 근접판정 `nearestArrival`

**Files:**
- Modify: `web/frontend/package.json`
- Create: `web/frontend/lib/follow.ts`
- Test: `web/frontend/lib/follow.test.ts`

- [ ] **Step 1: vitest 설치 + test 스크립트 추가**

```bash
cd /home/rokey/MediCart/web/frontend
npm install -D vitest@^2
```

`web/frontend/package.json` 의 `"scripts"` 에 `"test"` 한 줄 추가(기존 dev/build/start/lint 유지):

```json
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "eslint",
    "test": "vitest run"
  },
```

- [ ] **Step 2: 실패하는 테스트 작성**

Create `web/frontend/lib/follow.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { nearestArrival, type ArrivalTarget } from "./follow";

const T: ArrivalTarget[] = [
  { key: "pharmacy", label: "약품실", x: -9, y: -9 },
  { key: "t101_1", label: "101호 1번", x: -12, y: -5 },
];

describe("nearestArrival", () => {
  it("pose 없으면 null", () => {
    expect(nearestArrival(undefined, T, null)).toBeNull();
  });
  it("타겟 비면 null", () => {
    expect(nearestArrival({ x: -9, y: -9 }, [], null)).toBeNull();
  });
  it("1.0m 이내면 도착(최근접)", () => {
    expect(nearestArrival({ x: -9.5, y: -9 }, T, null)?.key).toBe("pharmacy"); // 0.5m
  });
  it("1.0m 초과 + 직전 미도착이면 null", () => {
    expect(nearestArrival({ x: -9, y: -7.9 }, T, null)).toBeNull(); // 1.1m
  });
  it("히스테리시스: 도착 후 1.2m까지 유지", () => {
    expect(nearestArrival({ x: -9, y: -7.85 }, T, "pharmacy")?.key).toBe("pharmacy"); // 1.15m
  });
  it("히스테리시스: 1.2m 초과 시 해제", () => {
    expect(nearestArrival({ x: -9, y: -7.7 }, T, "pharmacy")).toBeNull(); // 1.3m
  });
  it("여러 타겟 중 가장 가까운 것 선택", () => {
    expect(nearestArrival({ x: -12, y: -5.4 }, T, null)?.key).toBe("t101_1"); // 0.4m
  });
});
```

- [ ] **Step 3: 실패 확인**

Run: `cd /home/rokey/MediCart/web/frontend && npm test`
Expected: FAIL — `Failed to resolve import "./follow"` (또는 nearestArrival is not a function).

- [ ] **Step 4: 순수 구현 작성**

Create `web/frontend/lib/follow.ts`:

```ts
// 회진 근접판정 순수 로직(의존성 0 — vitest로 단위테스트).
export type Pt = { x: number; y: number };
export type ArrivalTarget = { key: string; label: string; x: number; y: number };

// pose에 가장 가까운 타겟 1개를 히스테리시스로 판정.
// prevKey와 같은 타겟이면 exitR(이탈 반경), 아니면 enterR(진입 반경) 기준.
// 도착이면 그 타겟, 아니면 null.
export function nearestArrival(
  pose: Pt | undefined,
  targets: ArrivalTarget[],
  prevKey: string | null,
  enterR = 1.0,
  exitR = 1.2,
): ArrivalTarget | null {
  if (!pose || targets.length === 0) return null;
  let best: ArrivalTarget | null = null;
  let bestD = Infinity;
  for (const t of targets) {
    const d = Math.hypot(pose.x - t.x, pose.y - t.y);
    if (d < bestD) { bestD = d; best = t; }
  }
  if (!best) return null;
  const r = best.key === prevKey ? exitR : enterR;
  return bestD <= r ? best : null;
}
```

- [ ] **Step 5: 통과 확인**

Run: `cd /home/rokey/MediCart/web/frontend && npm test`
Expected: PASS — 7 passed.

- [ ] **Step 6: 커밋**

```bash
cd /home/rokey/MediCart
git add web/frontend/package.json web/frontend/package-lock.json web/frontend/lib/follow.ts web/frontend/lib/follow.test.ts
git commit -m "feat(web): 회진 근접판정 nearestArrival + vitest"
```

---

## Task 2: 부작용 헬퍼 `followActions.ts` (start/return/waitDock)

**Files:**
- Create: `web/frontend/lib/followActions.ts`

기존 `lib/api.ts` 의 `saveMode(action,mode,params?)`, `pushMission(ns,action,params?,mode?)`, `API_BASE`,
그리고 SSE 메시지 형식 `{source:ns, dock:{is_docked}}` 을 사용한다. 네트워크/SSE 의존이라 단위테스트
없이 수동 E2E(Task 5)로 검증한다.

- [ ] **Step 1: 구현 작성**

Create `web/frontend/lib/followActions.ts`:

```ts
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
export async function startFollow(ns: string, isDocked: boolean): Promise<void> {
  if (isDocked) {
    await pushMission(ns, "undock");
    await waitDockState(ns, false, 20000);
  }
  await saveMode("start", "round");
}

// 홈 복귀: round 중지 → dock 타겟으로 goto(dock_after). nav_executor가 Nav2 이동 후 도킹.
export async function returnHome(
  ns: string,
  dock: { x: number; y: number; yaw?: number },
): Promise<void> {
  await saveMode("stop", "round");
  await pushMission(ns, "goto", { x: dock.x, y: dock.y, yaw: dock.yaw ?? 0, dock_after: true });
}
```

- [ ] **Step 2: 타입체크(빌드 일부) 확인**

Run: `cd /home/rokey/MediCart/web/frontend && npx tsc --noEmit`
Expected: 에러 없음(또는 기존 코드 무관 에러만 — 이 파일 관련 에러 0).

- [ ] **Step 3: 커밋**

```bash
cd /home/rokey/MediCart
git add web/frontend/lib/followActions.ts
git commit -m "feat(web): 회진 오케스트레이션 헬퍼(startFollow/returnHome/waitDockState)"
```

---

## Task 3: 풀스크린 `FollowOverlay` 컴포넌트

**Files:**
- Create: `web/frontend/components/FollowOverlay.tsx`

자가 SSE 구독으로 `ns` 로봇의 `pose`·`dock.is_docked` 수신 → `nearestArrival` 로 도착 텍스트 →
복귀 버튼 → `returnHome` → 도킹 완료(`is_docked===true`) 시 `onExit`.

- [ ] **Step 1: 구현 작성**

Create `web/frontend/components/FollowOverlay.tsx`:

```tsx
"use client";
import { useEffect, useRef, useState } from "react";
import { API_BASE } from "@/lib/api";
import { nearestArrival, type ArrivalTarget, type Pt } from "@/lib/follow";
import { returnHome } from "@/lib/followActions";

type Props = {
  active: boolean;
  ns: string;
  targets: ArrivalTarget[];
  dock: { x: number; y: number; yaw?: number };
  onExit: () => void;
};

export default function FollowOverlay({ active, ns, targets, dock, onExit }: Props) {
  const [pose, setPose] = useState<Pt | undefined>(undefined);
  const [isDocked, setIsDocked] = useState<boolean | undefined>(undefined);
  const [phase, setPhase] = useState<"following" | "returning">("following");
  const [arrivalLabel, setArrivalLabel] = useState<string | null>(null);
  const prevKey = useRef<string | null>(null);

  // active일 때만 SSE 자가 구독
  useEffect(() => {
    if (!active) return;
    setPhase("following");
    prevKey.current = null;
    setArrivalLabel(null);
    const es = new EventSource(`${API_BASE}/api/stream`, { withCredentials: true });
    es.onmessage = (e) => {
      try {
        const d = JSON.parse(e.data);
        if (d?.source !== ns) return;
        if (d.pose) setPose({ x: d.pose.x, y: d.pose.y });
        if (d.dock) setIsDocked(d.dock.is_docked);
      } catch { /* ignore */ }
    };
    return () => es.close();
  }, [active, ns]);

  // pose 갱신마다 근접판정(히스테리시스)
  useEffect(() => {
    if (phase !== "following") return;
    const a = nearestArrival(pose, targets, prevKey.current);
    prevKey.current = a ? a.key : null;
    setArrivalLabel(a ? a.label : null);
  }, [pose, targets, phase]);

  // 복귀 중 도킹 완료 → 종료
  useEffect(() => {
    if (phase === "returning" && isDocked === true) onExit();
  }, [phase, isDocked, onExit]);

  if (!active) return null;

  let text: string;
  if (phase === "returning") text = "복귀 중…";
  else if (!pose) text = "위치 수신 대기…";
  else if (arrivalLabel) text = `${arrivalLabel}에 도착`;
  else text = "회진 중 — 안내를 따라오세요";

  const onReturn = async () => {
    setPhase("returning");
    try { await returnHome(ns, dock); } catch { /* feedback로 추적 */ }
  };

  return (
    <div className="fixed inset-0 z-50 bg-[#0b1f1d] text-white grid place-items-center">
      <div className="text-center px-8">
        <div className="text-[clamp(40px,9vw,120px)] font-bold leading-tight">{text}</div>
        <div className="text-[clamp(14px,2vw,22px)] text-white/60 mt-4">
          {ns.toUpperCase()} · 회진 모드
        </div>
      </div>
      <button
        onClick={onReturn}
        disabled={phase === "returning"}
        className="fixed bottom-8 right-8 px-7 py-4 rounded-2xl text-[18px] font-semibold bg-white text-[#0b1f1d] shadow-lg disabled:opacity-50"
      >
        홈 위치로 복귀
      </button>
    </div>
  );
}
```

- [ ] **Step 2: 타입체크 확인**

Run: `cd /home/rokey/MediCart/web/frontend && npx tsc --noEmit`
Expected: 이 파일 관련 에러 0.

- [ ] **Step 3: 커밋**

```bash
cd /home/rokey/MediCart
git add web/frontend/components/FollowOverlay.tsx
git commit -m "feat(web): FollowOverlay 풀스크린(자가 SSE·근접 도착·복귀 버튼)"
```

---

## Task 4: 홈 배너 + 재확인 + 마운트 (`app/page.tsx`)

**Files:**
- Modify: `web/frontend/app/page.tsx`

최상단(eyebrow 위)에 풀폭 '회진 모드' 배너 → 클릭 시 재확인(확인/취소) → 확인 시 현재 docked 조회 후
`startFollow` + `FollowOverlay` 활성화.

- [ ] **Step 1: import 추가**

`web/frontend/app/page.tsx` 상단 import 교체:

```tsx
"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { getAmrs, getTargets, type AmrSnapshot, type GotoTarget } from "@/lib/api";
import { PRIMARY_NS } from "@/lib/config";
import { startFollow } from "@/lib/followActions";
import { type ArrivalTarget } from "@/lib/follow";
import FollowOverlay from "@/components/FollowOverlay";
```

- [ ] **Step 2: Home() 내부 상태 + 타겟 로드 추가**

`export default function Home() {` 직후, 기존 `const [stat, ...]` 옆에 추가:

```tsx
  const [confirming, setConfirming] = useState(false);
  const [followActive, setFollowActive] = useState(false);
  const [targets, setTargets] = useState<Record<string, GotoTarget>>({});

  useEffect(() => {
    getTargets().then((r) => setTargets(r.targets || {})).catch(() => {});
  }, []);

  const arrivalTargets: ArrivalTarget[] = (["pharmacy", "t101_1", "t101_2"] as const)
    .map((k) => {
      const t = targets[k];
      return t ? { key: k, label: t.label, x: t.x, y: t.y } : null;
    })
    .filter((t): t is ArrivalTarget => t !== null);
  const dock = targets["dock"]
    ? { x: targets.dock.x, y: targets.dock.y, yaw: targets.dock.yaw }
    : { x: -8, y: -6, yaw: 0 };

  async function confirmStart() {
    setConfirming(false);
    let docked = true;
    try {
      const a = await getAmrs();
      docked = a[PRIMARY_NS]?.dock?.is_docked ?? true;
    } catch { /* 기본 docked 가정 */ }
    setFollowActive(true);
    startFollow(PRIMARY_NS, docked).catch(() => {});
  }
```

- [ ] **Step 3: 최상단 배너 + 오버레이 JSX 삽입**

`return (` 직후 `<div className="p-7 ...">` 내부 **맨 처음**(`<div className="eyebrow">` 위)에 삽입:

```tsx
      {!confirming ? (
        <button
          onClick={() => setConfirming(true)}
          className="w-full rounded-2xl px-7 py-6 mb-6 text-left text-white shadow-md flex items-center justify-between"
          style={{ background: "linear-gradient(90deg,#0ca39a,#0b7d76)" }}
        >
          <div>
            <div className="text-[20px] font-bold">회진 모드 시작</div>
            <div className="text-[13px] text-white/80 mt-1">AMR이 앞의 대상을 따라 병동을 회진합니다</div>
          </div>
          <span className="text-[26px]">▶</span>
        </button>
      ) : (
        <div
          className="w-full rounded-2xl px-7 py-6 mb-6 text-white shadow-md flex items-center justify-between gap-4"
          style={{ background: "linear-gradient(90deg,#0ca39a,#0b7d76)" }}
        >
          <div className="text-[15px] font-semibold">회진 모드를 시작할까요? (도크 상태면 자동 undock)</div>
          <div className="flex gap-2 shrink-0">
            <button onClick={confirmStart} className="px-5 py-2.5 rounded-xl bg-white text-[#0b7d76] font-semibold">확인</button>
            <button onClick={() => setConfirming(false)} className="px-5 py-2.5 rounded-xl bg-white/20 font-semibold">취소</button>
          </div>
        </div>
      )}
      <FollowOverlay
        active={followActive}
        ns={PRIMARY_NS}
        targets={arrivalTargets}
        dock={dock}
        onExit={() => setFollowActive(false)}
      />
```

- [ ] **Step 4: 타입체크 + 린트**

Run: `cd /home/rokey/MediCart/web/frontend && npx tsc --noEmit && npm run lint`
Expected: 이 변경 관련 에러 0.

- [ ] **Step 5: 커밋**

```bash
cd /home/rokey/MediCart
git add web/frontend/app/page.tsx
git commit -m "feat(web): 홈 최상단 회진 모드 배너 + 재확인 + FollowOverlay 마운트"
```

---

## Task 5: 빌드 + 수동 E2E (사용자 실행 — 로봇 구동 포함)

**Files:** (없음 — 검증 단계)

- [ ] **Step 1: 프로덕션 빌드**

Run: `cd /home/rokey/MediCart/web/frontend && NEXT_PUBLIC_API_BASE="" NEXT_PUBLIC_PRIMARY_NS=robot6 NEXT_PUBLIC_SECONDARY_NS=robot3 npm run build`
Expected: 빌드 성공(에러 0). 새 페이지/청크에 `/` 포함.

- [ ] **Step 2: 웹 재기동**

(어시스턴트가 안내) 터미널에서: `web-restart`
Expected: `:5000 LISTEN`, `:3000 LISTEN`, `tunnel UP`.

- [ ] **Step 3: 로봇 스택 가동 (사용자 직접 — 로봇 구동)**

전제: robot6 측 `loc` → `nav` → `medicart-bringup` + **`nurse_tracker` 노드 기동**(추종 cmd_vel 소스).
nurse_tracker 미기동 시 round 모드여도 로봇이 안 움직임.

- [ ] **Step 4: E2E 시나리오 검증**

1. `https://intel.thatshoon.com/` 접속 → 최상단 "회진 모드 시작" 배너 확인.
2. 클릭 → "회진 모드를 시작할까요?" 재확인 → **확인**.
   - 로봇이 docked면 자동 undock 후 추종 시작. 화면이 풀스크린 "회진 중 — 안내를 따라오세요"로 전환.
3. 사람이 로봇 앞에서 이동 → 로봇이 추종.
4. 약품실(-9,-9) / 101호1(-12,-5) / 101호2(-12,-6) 1m 이내 접근 → 풀스크린 텍스트 "약품실에 도착" 등으로 변경(로봇은 계속 추종).
5. 우하단 **"홈 위치로 복귀"** 클릭 → "복귀 중…" → 로봇이 dock(-8,-6)으로 Nav2 이동 후 도킹 → 도킹 완료 시 오버레이 종료(홈 복귀).

Expected: 각 단계 동작. 실패 시 mission_feedback 로그·브라우저 콘솔 확인.

---

## 참고 (구현 시 주의)

- **로봇/백엔드 무변경**: 신규 백엔드 라우트·ROS 코드 없음. 전부 기존 엔드포인트 재사용.
- `saveMode`는 ns 인자 없음 — 백엔드가 `{PRIMARY_NS}/cmd`에 기록하므로 자동으로 primary 로봇 대상. 그래서 undock/goto도 `PRIMARY_NS`로 맞춰야 일관됨(Task 4에서 `PRIMARY_NS` 사용).
- `pushMission`은 `{ok,id?,error?}` 반환 — 실패해도 오버레이는 유지(수동 복귀/재시도).
- vitest는 순수 `follow.ts`만 테스트(의존성 0). 부작용/UI는 수동 E2E.
