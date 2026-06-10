# 로봇별 분기 + 맵/텔레메트리 정확성 (하위 프로젝트 A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 웹이 RTDB에서 각 로봇(robot3·robot6)의 데이터를 per-robot로 끌어다, ⑥ 경과/LIVE를 정확히 계산하고 ① 순회 문진 홈을 robot3 실제 도크로 보내며 ⑤ 미니맵에 침상·약품실·호실·로봇별 도크를 오버레이한다.

**Architecture:** 순수 헬퍼 모듈 `lib/telemetry.ts`(stamp 나이·LIVE 판정·로봇 홈 도출)를 신설하고, 이를 콘솔/디버그/홈/맵 컴포넌트에 결선한다. 백엔드·DB·로봇 스키마는 변경하지 않는다(웹 단독). stamp는 RTDB에서 **밀리초**로 들어오므로 `Date.now()`(ms)와 같은 단위로 비교한다. 로봇 홈은 **도킹 중인 로봇의 `amcl_pose`**(RTDB `{ns}/pose`)에서 도출한다.

**Tech Stack:** Next.js(App Router, "use client" 컴포넌트) · TypeScript · vitest · 기존 `lib/api.ts`(`getAmrs`/`getTargets`/`getMapMeta`/`getRooms`).

> **Next.js 주의:** 모든 변경 대상은 기존 "use client" 컴포넌트와 순수 lib 모듈이다. **새로운 Next.js API(서버 컴포넌트·라우트 핸들러·데이터 패칭 API 등)를 도입하지 말 것** — 기존 파일의 React `useState`/`useEffect` 패턴을 그대로 따른다. Next API가 꼭 필요해 보이면 `node_modules/next/dist/docs/` 를 먼저 읽는다.

> **런타임 검증은 사용자 몫:** 로봇 구동(undock·순회·도킹)·실제 미니맵 표시는 사용자가 로봇을 띄워 확인한다. 본 플랜의 자동 검증은 vitest 단위테스트 + `npx tsc --noEmit` 타입검사까지다.

**작업 위치:** `/home/rokey/MediCart`, `integration` 브랜치, 작업 디렉토리 `web/frontend`.

---

## File Structure

- **Create** `web/frontend/lib/telemetry.ts` — 스냅샷 파생 순수 헬퍼: `snapAgeMs`(stamp 나이 ms), `isLive`(LIVE 판정), `robotHome`(도킹 pose→홈). 한 가지 책임: "RTDB 스냅샷에서 파생값 계산".
- **Create** `web/frontend/lib/telemetry.test.ts` — 위 헬퍼 vitest 단위테스트.
- **Modify** `web/frontend/app/console/page.tsx` (≈254–277) — ⑥ 경과/online 을 `snapAgeMs`/`isLive` 로 교체.
- **Modify** `web/frontend/app/debug/page.tsx` (≈79–106) — ⑥ 동일 교체.
- **Modify** `web/frontend/app/page.tsx` (≈31–63, 143–149) — ⑥ online 카운트 교체 + ① amrs 보관 + robot3 홈을 `RoundsIntakeOverlay` `dock` 로 전달.
- **Modify** `web/frontend/components/MapView.tsx` — ⑤ `targets` 구독 + 침상·약품실·호실 마커 + 로봇별 도크(`robotHome`) 마커.

---

## Task 1: `lib/telemetry.ts` — 스냅샷 파생 순수 헬퍼 (TDD)

**Files:**
- Create: `web/frontend/lib/telemetry.ts`
- Test: `web/frontend/lib/telemetry.test.ts`

배경: RTDB `{ns}/stamp` 는 **밀리초**(예: `1781056366312`). 기존 코드는 `Date.now()/1000`(초)와 빼서 거대 음수가 나와 항상 LIVE로 오판했다. 홈 좌표는 도킹 중 로봇의 `pose`(=`amcl_pose`)가 곧 그 로봇의 홈이다(로봇별로 다름: robot3≈(-7.4,-3.1), robot6≈(0.016,-0.078)).

`AmrSnapshot` 타입은 `lib/api.ts` 에 이미 정의되어 있고 `{ source; pose?:{x,y,yaw}; dock?:{is_docked}; stamp?; ... } | null` 형태다(즉 null 포함 유니온).

- [ ] **Step 1: 실패하는 테스트 작성**

`web/frontend/lib/telemetry.test.ts`:
```ts
import { describe, it, expect } from "vitest";
import { snapAgeMs, isLive, robotHome } from "./telemetry";

describe("snapAgeMs (stamp ms 기준 나이)", () => {
  it("미존재/0/음수 stamp → Infinity(STALE)", () => {
    expect(snapAgeMs(undefined)).toBe(Infinity);
    expect(snapAgeMs(0)).toBe(Infinity);
    expect(snapAgeMs(-5)).toBe(Infinity);
    expect(snapAgeMs(Number.NaN)).toBe(Infinity);
  });
  it("최근 stamp(ms) → 0 이상 작은 값", () => {
    const age = snapAgeMs(Date.now() - 1000);
    expect(age).toBeGreaterThanOrEqual(900);
    expect(age).toBeLessThan(1500);
  });
  it("미래 stamp(시계 스큐) → 0 으로 클램프(STALE 아님)", () => {
    expect(snapAgeMs(Date.now() + 10_000)).toBe(0);
  });
});

describe("isLive (임계 비교)", () => {
  it("3s 이내 → LIVE, 그 밖 → STALE", () => {
    expect(isLive(Date.now() - 500)).toBe(true);
    expect(isLive(Date.now() - 9000)).toBe(false);
    expect(isLive(undefined)).toBe(false);
  });
  it("임계값 인자 적용(5s)", () => {
    expect(isLive(Date.now() - 4000, 5000)).toBe(true);
    expect(isLive(Date.now() - 6000, 5000)).toBe(false);
  });
});

describe("robotHome (도킹 pose → 홈)", () => {
  const base = { source: "robot3", stamp: 1 };
  it("도킹+pose → 그 pose", () => {
    expect(robotHome({ ...base, dock: { is_docked: true }, pose: { x: -7.4, y: -3.1, yaw: 0 } }))
      .toEqual({ x: -7.4, y: -3.1, yaw: 0 });
  });
  it("미도킹 → null", () => {
    expect(robotHome({ ...base, dock: { is_docked: false }, pose: { x: 1, y: 2, yaw: 0 } })).toBeNull();
  });
  it("pose 없음 → null", () => {
    expect(robotHome({ ...base, dock: { is_docked: true } })).toBeNull();
  });
  it("null 스냅샷 → null", () => {
    expect(robotHome(null)).toBeNull();
  });
});
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd /home/rokey/MediCart/web/frontend && npx vitest run lib/telemetry.test.ts`
Expected: FAIL — `Failed to resolve import "./telemetry"` (모듈 미존재).

- [ ] **Step 3: 최소 구현 작성**

`web/frontend/lib/telemetry.ts`:
```ts
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
export function robotHome(snap: AmrSnapshot): { x: number; y: number; yaw: number } | null {
  if (snap && snap.dock?.is_docked && snap.pose) {
    return { x: snap.pose.x, y: snap.pose.y, yaw: snap.pose.yaw };
  }
  return null;
}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd /home/rokey/MediCart/web/frontend && npx vitest run lib/telemetry.test.ts`
Expected: PASS — 3 describe 블록 전부 통과.

- [ ] **Step 5: 커밋**

```bash
cd /home/rokey/MediCart
git add web/frontend/lib/telemetry.ts web/frontend/lib/telemetry.test.ts
git commit -m "feat(web): RTDB 스냅샷 파생 헬퍼(snapAgeMs/isLive/robotHome)

stamp ms 단위 나이·LIVE 판정·도킹 pose→홈 도출 순수 헬퍼.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: ⑥ 콘솔·디버그 경과/LIVE 단위 버그 수정

**Files:**
- Modify: `web/frontend/app/console/page.tsx:254-277`
- Modify: `web/frontend/app/debug/page.tsx:79-106`

배경: 두 파일의 패널이 `const now = Date.now()/1000; const age = snap?.stamp ? now - snap.stamp : Infinity; const online = age < 3;` 으로 초·밀리초를 섞어 항상 LIVE로 표시한다. Task 1 헬퍼로 교체한다.

- [ ] **Step 1: `app/console/page.tsx` import 에 헬퍼 추가**

`web/frontend/app/console/page.tsx` 3번째 줄의 import 바로 아래에 추가:
```ts
import { snapAgeMs, isLive } from "@/lib/telemetry";
```

- [ ] **Step 2: `app/console/page.tsx` 경과/online 계산 교체**

다음 블록(≈254–256):
```ts
  const now = Date.now() / 1000;
  const age = snap?.stamp ? now - snap.stamp : Infinity;
  const online = age < 3;
```
을 아래로 교체:
```ts
  const ageMs = snapAgeMs(snap?.stamp);
  const online = isLive(snap?.stamp);
```

- [ ] **Step 3: `app/console/page.tsx` 경과 표시 줄 교체**

다음 줄(≈277):
```tsx
        <H label="경과" v={isFinite(age) ? `${(age * 1000).toFixed(0)}ms` : "—"} warn={age >= 3} />
```
을 아래로 교체:
```tsx
        <H label="경과" v={isFinite(ageMs) ? `${ageMs.toFixed(0)}ms` : "—"} warn={ageMs >= 3000} />
```

- [ ] **Step 4: `app/debug/page.tsx` import 에 헬퍼 추가**

`web/frontend/app/debug/page.tsx` 상단 import 구역에 추가:
```ts
import { snapAgeMs, isLive } from "@/lib/telemetry";
```

- [ ] **Step 5: `app/debug/page.tsx` 경과/online 계산 교체**

다음 블록(≈79–81):
```ts
  const now = Date.now() / 1000;
  const age = snap?.stamp ? now - snap.stamp : Infinity;
  const online = age < 3;
```
을 아래로 교체:
```ts
  const ageMs = snapAgeMs(snap?.stamp);
  const online = isLive(snap?.stamp);
```

- [ ] **Step 6: `app/debug/page.tsx` 경과 표시 줄 교체**

다음 줄(≈106):
```tsx
        <H label="경과" v={isFinite(age) ? `${(age * 1000).toFixed(0)}ms` : "—"} warn={age >= 3} />
```
을 아래로 교체:
```tsx
        <H label="경과" v={isFinite(ageMs) ? `${ageMs.toFixed(0)}ms` : "—"} warn={ageMs >= 3000} />
```

- [ ] **Step 7: 타입검사**

Run: `cd /home/rokey/MediCart/web/frontend && npx tsc --noEmit`
Expected: 에러 없음(0 출력). (`now`/`age` 미사용 변수 잔존 없음 — 모두 교체됨.)

- [ ] **Step 8: 커밋**

```bash
cd /home/rokey/MediCart
git add web/frontend/app/console/page.tsx web/frontend/app/debug/page.tsx
git commit -m "fix(web): 경과/LIVE stamp 단위 버그(ms) — 콘솔·디버그

stamp(ms)를 Date.now()/1000(초)와 비교하던 오류로 항상 LIVE 오판.
snapAgeMs/isLive 로 ms 단위 통일.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: ① 홈 페이지 — robot3 홈을 RTDB 도킹 pose 에서 + online 단위 수정

**Files:**
- Modify: `web/frontend/app/page.tsx:4` (import)
- Modify: `web/frontend/app/page.tsx:31-32` (state)
- Modify: `web/frontend/app/page.tsx:44-55` (load effect)
- Modify: `web/frontend/app/page.tsx:61-63` (dock 도출)

배경: `RoundsIntakeOverlay` 가 `pushMission(ns,"patrol_intake_mission",{ home: dock })` 로 홈 좌표를 robot3 에 전달하는데, 현재 `dock` 은 단일 `targets.dock`(=robot6 도크)이라 robot3 가 엉뚱한 위치로 복귀한다. robot3 의 홈은 도킹 중 `amrs[PATROL_NS].pose` 다. 또한 `online` 카운트(line 48–49)도 `Date.now()/1000` 초·ms 혼용 버그가 있다.

`PATROL_NS`("robot3")·`AmrSnapshot`·`GotoTarget` 은 이미 import 되어 있다.

- [ ] **Step 1: import 에 telemetry 헬퍼 추가**

`web/frontend/app/page.tsx` 의 `import { getAmrs, getTargets, ... } from "@/lib/api";` 줄(4번째) 아래에 추가:
```ts
import { isLive, robotHome } from "@/lib/telemetry";
```

- [ ] **Step 2: amrs 상태 추가**

다음 줄(≈31–32):
```ts
  const [stat, setStat] = useState({ online: 0, total: 2 });
  const [targets, setTargets] = useState<Record<string, GotoTarget>>({});
```
바로 아래에 추가:
```ts
  const [amrs, setAmrs] = useState<Record<string, AmrSnapshot>>({});
```

- [ ] **Step 3: load effect — amrs 보관 + online 단위 수정**

다음 블록(≈45–51):
```ts
    const load = () =>
      getAmrs().then((a: Record<string, AmrSnapshot>) => {
        const vals = Object.values(a);
        const now = Date.now() / 1000;
        const online = vals.filter((s) => s && s.stamp && now - s.stamp < 5).length;
        setStat({ online, total: Math.max(vals.length, 2) });
      }).catch(() => {});
```
을 아래로 교체:
```ts
    const load = () =>
      getAmrs().then((a: Record<string, AmrSnapshot>) => {
        setAmrs(a);
        const vals = Object.values(a);
        const online = vals.filter((s) => isLive(s?.stamp, 5000)).length;
        setStat({ online, total: Math.max(vals.length, 2) });
      }).catch(() => {});
```

- [ ] **Step 4: dock 도출 — robot3 도킹 pose 우선**

다음 블록(≈61–63):
```ts
  const dock = targets["dock"]
    ? { x: targets.dock.x, y: targets.dock.y, yaw: targets.dock.yaw }
    : { x: -8, y: -6, yaw: 0 };
```
을 아래로 교체:
```ts
  // 순회 문진(robot3) 복귀 홈: 도킹 중인 robot3 의 실제 pose(=amcl_pose)를 우선 사용.
  // 미도킹/미수신이면 targets.dock → 기본값 순으로 폴백.
  const dock =
    robotHome(amrs[PATROL_NS]) ??
    (targets["dock"]
      ? { x: targets.dock.x, y: targets.dock.y, yaw: targets.dock.yaw }
      : { x: -8, y: -6, yaw: 0 });
```

- [ ] **Step 5: 타입검사**

Run: `cd /home/rokey/MediCart/web/frontend && npx tsc --noEmit`
Expected: 에러 없음. (`amrs` 사용처 존재, `AmrSnapshot` 이미 import.)

- [ ] **Step 6: 영향도 확인 — dock 소비처 grep**

Run: `cd /home/rokey/MediCart/web/frontend && grep -rn "patrol_intake_mission\|home: dock\|dock={" components/RoundsIntakeOverlay.tsx app/page.tsx`
Expected: `RoundsIntakeOverlay.tsx` 가 `home: dock`(현재 prop) 사용, `page.tsx` 가 `dock={dock}` 전달 — 시그니처 변화 없음(`{x,y,yaw?}` 동일), robot3 도킹 시 값만 정확해짐.

- [ ] **Step 7: 커밋**

```bash
cd /home/rokey/MediCart
git add web/frontend/app/page.tsx
git commit -m "fix(web): 순회 문진 홈을 robot3 도킹 pose(RTDB)에서 도출 + online 단위

단일 targets.dock(robot6) 대신 robotHome(amrs[robot3]) 사용 →
robot3 가 자기 도크로 복귀. online 카운트 stamp ms 단위도 수정.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: ⑤ 미니맵 — targets + 로봇별 도크 오버레이

**Files:**
- Modify: `web/frontend/components/MapView.tsx:3` (import)
- Modify: `web/frontend/components/MapView.tsx:18-19` (state)
- Modify: `web/frontend/components/MapView.tsx:31-32` (init fetch)
- Modify: `web/frontend/components/MapView.tsx:108-109` (마커 렌더 삽입)
- Modify: `web/frontend/components/MapView.tsx:134` (effect deps)

배경: `MapView` 는 저장맵이 있으면 이미 `mapMeta`(origin·resolution) 기준 변환을 쓴다(좌표 정렬 OK). 문제는 **`targets`(침상·약품실·호실)와 로봇별 도크를 전혀 안 그린다**는 것 — `rooms` 만 그리는데 그건 시드가 비어 거의 안 보인다. `X`/`Y` 변환 클로저는 mapMeta·폴백 양쪽 분기에서 정의되므로, 그 클로저로 targets·도크 마커를 그리면 둘 다에서 동작한다.

`getTargets`·`GotoTarget` 은 `lib/api.ts` 에 있고, `robotHome` 은 Task 1 에서 추가했다. `AMR_COLOR`·`roundRect` 는 파일에 이미 있다.

- [ ] **Step 1: import 추가**

`web/frontend/components/MapView.tsx` 3번째 줄:
```ts
import { API_BASE, AmrSnapshot, getAmrs, getRooms, saveMode, getMapMeta, MapMeta, pushMission } from "@/lib/api";
```
을 아래로 교체(`getTargets`·`GotoTarget` 추가):
```ts
import { API_BASE, AmrSnapshot, getAmrs, getRooms, saveMode, getMapMeta, MapMeta, pushMission, getTargets, GotoTarget } from "@/lib/api";
```
그리고 그 아래(5번째 줄 `import { PRIMARY_NS, ... }` 다음 줄)에 추가:
```ts
import { robotHome } from "@/lib/telemetry";
```

- [ ] **Step 2: targets 상태 추가**

다음 줄(≈18):
```ts
  const [rooms, setRooms] = useState<Rooms>({});
```
바로 아래에 추가:
```ts
  const [targets, setTargets] = useState<Record<string, GotoTarget>>({});
```

- [ ] **Step 3: 초기 fetch 에 getTargets 추가**

다음 줄(≈32):
```ts
    getRooms().then(setRooms).catch(() => {});
```
바로 아래에 추가:
```ts
    getTargets().then((r) => setTargets(r.targets || {})).catch(() => {});
```

- [ ] **Step 4: targets·로봇 도크 마커 렌더 삽입**

병실 마커 블록의 닫는 `});`(≈108, `ctx.fillText(name, px, py + 3.5);` 다음의 `});`) **바로 아래**, AMR 마커 블록(`// AMR 마커` 주석) **위**에 삽입:
```ts
    // targets 오버레이 (침상·약품실·호실) — "dock" 키는 로봇별 마커로 별도 처리
    Object.entries(targets).forEach(([key, t]) => {
      if (key === "dock") return;
      const px = X(t.x), py = Y(t.y);
      ctx.beginPath(); ctx.arc(px, py, 6, 0, Math.PI * 2);
      ctx.fillStyle = "#fff4e6"; ctx.strokeStyle = "#f0b274"; ctx.lineWidth = 1.5;
      ctx.fill(); ctx.stroke();
      ctx.fillStyle = "#b9772e"; ctx.font = "600 10px 'Pretendard Variable'"; ctx.textAlign = "center";
      ctx.fillText(t.label || key, px, py - 10);
    });

    // 로봇별 홈/도크 마커 — 도킹 중인 로봇의 pose(=amcl_pose)에서 도출
    Object.entries(amrs).forEach(([src, a]) => {
      const home = robotHome(a);
      if (!home) return;
      const px = X(home.x), py = Y(home.y);
      const col = AMR_COLOR[src] || "#0ca39a";
      roundRect(ctx, px - 7, py - 7, 14, 14, 3);
      ctx.fillStyle = "#fff"; ctx.strokeStyle = col; ctx.lineWidth = 2; ctx.fill(); ctx.stroke();
      ctx.fillStyle = col; ctx.font = "600 9px 'Pretendard Variable'"; ctx.textAlign = "center";
      ctx.fillText(`${src} home`, px, py + 18);
    });
```

- [ ] **Step 5: effect 의존성에 targets 추가**

렌더 effect 의 의존성 배열(≈134):
```ts
  }, [amrs, rooms, mapMeta, mapReady]);
```
을 아래로 교체:
```ts
  }, [amrs, rooms, targets, mapMeta, mapReady]);
```

- [ ] **Step 6: 타입검사**

Run: `cd /home/rokey/MediCart/web/frontend && npx tsc --noEmit`
Expected: 에러 없음. (`targets`/`GotoTarget`/`robotHome` 모두 정의·import 됨.)

- [ ] **Step 7: 영향도 확인 — MapView 사용처**

Run: `cd /home/rokey/MediCart/web/frontend && grep -rn "MapView" app components`
Expected: `app/console/page.tsx`·`app/map/page.tsx` 등에서 `<MapView .../>` 사용. props 시그니처(`embedded`/`ns`/`amrs`/`live`) 변경 없음 — 신규 오버레이는 내부 동작이라 호출부 영향 없음.

- [ ] **Step 8: 커밋**

```bash
cd /home/rokey/MediCart
git add web/frontend/components/MapView.tsx
git commit -m "feat(web): 미니맵에 targets(침상·약품실·호실)+로봇별 도크 오버레이

기존 mapMeta 좌표 변환 위에 targets 마커와 robotHome(도킹 pose) 기반
로봇별 홈 마커를 추가. rooms만 그리던 한계 해소.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: 전체 검증 + 런타임 확인 안내

**Files:** 없음(검증 전용).

- [ ] **Step 1: 단위테스트 전체 통과**

Run: `cd /home/rokey/MediCart/web/frontend && npx vitest run`
Expected: 기존 테스트(`follow`/`patrol`/`ocrQr`) + 신규 `telemetry` 전부 PASS.

- [ ] **Step 2: 타입검사 전체**

Run: `cd /home/rokey/MediCart/web/frontend && npx tsc --noEmit`
Expected: 에러 0.

- [ ] **Step 3: 잔존 stamp 단위 버그 없음 확인(회귀 가드)**

Run: `cd /home/rokey/MediCart/web/frontend && grep -rn "Date.now() / 1000\|now - s.stamp\|now - snap.stamp" app components lib`
Expected: 매치 0 — 초·ms 혼용 패턴이 모두 제거됨.

- [ ] **Step 4: 사용자 런타임 확인 안내(출력만, 실행 금지)**

다음을 사용자에게 안내한다(직접 실행하지 말 것):
  1. `web-restart build` 로 프론트 재빌드·기동.
  2. **⑥**: 관리자 콘솔/디버그에서 로봇이 실제 송신 중이면 LIVE+경과 수백 ms, 끊기면 STALE 로 바뀌는지.
  3. **①**: robot3 도킹 상태에서 순회 문진 시작 → RTDB `robot3/mission_pool` 의 `patrol_intake_mission.params.home` 이 robot3 도크 좌표(≈ -7.4, -3.1)인지.
  4. **⑤**: 콘솔 미니맵에 침상·약품실·호실 마커와 `robot3 home`·`robot6 home` 도크 마커가 맵 위 올바른 위치에 뜨는지. 안 뜨면 `/api/map` 이 ninety 맵 메타(resolution 0.05, origin [-5.59,-4.58])를 반환하는지 확인 — 아니면 배포 env `MAP_YAML`/`MAP_PNG` 가 ninety 를 가리키도록 수정(코드 아닌 설정).

---

## Self-Review

**1. Spec coverage:**
- ⑥ stamp ms 버그 → Task 1(헬퍼)+Task 2(콘솔·디버그)+Task 3 Step 3(홈 online). ✅
- ① 로봇별 홈 RTDB 소싱 → Task 1(`robotHome`)+Task 3(홈 페이지 dock). ✅
- ⑤ 미니맵 오버레이(targets+per-robot dock) → Task 4. mapMeta 변환은 기존 코드에 이미 존재(스펙 A3#1)이라 신규 작업 불요 — Task 5 Step 4 에서 ninety 맵 메타 일치 런타임 점검으로 커버. ✅
- 스펙 "백엔드·DB·로봇 스키마 변경 없음" → 전 태스크 프론트 단독. ✅

**2. Placeholder scan:** TBD/TODO/"적절히 처리" 류 없음. 모든 코드 블록 실제 내용 포함. ✅

**3. Type consistency:** `snapAgeMs(stamp?: number)`, `isLive(stamp?, thresholdMs=3000)`, `robotHome(snap: AmrSnapshot): {x,y,yaw?}|null` — Task 2·3·4 사용처 모두 동일 시그니처. `dock`/`home` 객체 형태 `{x,y,yaw?}` 일관(RoundsIntakeOverlay prop 과 동일). ✅
