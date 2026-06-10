# 순회문진 깨끗한 시작 + 웹 엄격순서 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 순회문진이 stale/경합 `patrol/phase` 때문에 첫 환자를 건너뛰고 "이동 중"을 조기 렌더하는 버그를, 깨끗한 시작(서버 리셋)과 웹 엄격순서로 고친다.

**Architecture:** 백엔드에 `POST /api/patrol/start`(clear_missions+reset_patrol+push)를 추가해 시작을 원자화하고, 프론트는 순수함수 `acceptArrival`로 도착을 엄격순서(`idx===lastArrived+1`)·ready·async잠금으로만 수용한다. 로봇 medicart_ws는 변경하지 않는다(stale 제거를 RTDB write로 처리).

**Tech Stack:** Flask(Python) · firebase_admin · Next.js("use client") · TypeScript · vitest · pytest.

> **검증 한계:** 단위테스트(vitest/pytest) + `npx tsc --noEmit` 까지가 자동 검증. 실제 로봇 순회(undock→병상→복귀)는 사용자가 로봇 구동으로 확인.

**작업 위치:** `/home/rokey/MediCart`, `integration` 브랜치.

---

## File Structure

- **Modify** `web/backend/fb_read.py` — 신규 `reset_patrol(ns)`(patrol stale 리셋). `set_patrol_advance` 인접.
- **Modify** `web/backend/app.py` — 신규 라우트 `POST /api/patrol/start`(clean start). `/api/patrol/advance` 인접.
- **Modify** `web/backend/test/test_fb_read.py` — `reset_patrol` 잘못된 ns 거부 단위테스트.
- **Modify** `web/frontend/lib/patrol.ts` — 신규 순수함수 `acceptArrival`.
- **Modify** `web/frontend/lib/patrol.test.ts` — `acceptArrival` 단위테스트.
- **Modify** `web/frontend/lib/api.ts` — 신규 `startPatrol(ns, body)`.
- **Modify** `web/frontend/components/RoundsIntakeOverlay.tsx` — 시작 호출·poll·arriveAt·finishStop·moving 메시지(readyRef/arrivingRef).

---

## Task 1: 백엔드 — `reset_patrol` + `/api/patrol/start`

**Files:**
- Modify: `web/backend/fb_read.py` (set_patrol_advance 인접, ~463)
- Modify: `web/backend/app.py` (patrol_advance 인접, ~495)
- Test: `web/backend/test/test_fb_read.py`

배경: 시작 시 mission_pool 유령 정리 + `{ns}/patrol` 의 stale `{phase:'arrived',stop:...}` 를 `idle` 로 리셋해야 웹이 첫 환자부터 정상 인식한다. `valid_robot_ns`·`clear_missions`·`push_mission` 은 기존 함수.

- [ ] **Step 1: reset_patrol 잘못된 ns 거부 테스트 작성**

`web/backend/test/test_fb_read.py` 끝에 추가:
```python
def test_reset_patrol_rejects_bad_ns():
    """잘못된 ns 는 firebase 접근 전에 False 로 거부(순수부)."""
    import fb_read
    assert fb_read.reset_patrol("../x") is False
    assert fb_read.reset_patrol("") is False
    assert fb_read.reset_patrol("robot9") is False
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd /home/rokey/MediCart/web/backend && env -i PATH="/usr/bin:/bin" PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 venv/bin/python -m pytest test/test_fb_read.py::test_reset_patrol_rejects_bad_ns -q`
Expected: FAIL — `AttributeError: module 'fb_read' has no attribute 'reset_patrol'`.

- [ ] **Step 3: fb_read.reset_patrol 구현**

`web/backend/fb_read.py` 의 `set_patrol_advance` 함수 정의 바로 아래(다음 함수 정의 직전)에 추가:
```python
def reset_patrol(ns: str = PRIMARY_NS) -> bool:
    """순회 시작 전 stale 제거 — {ns}/patrol 을 idle/미완료로 set(이전 stop 키까지 제거).
    잘못된 ns 는 firebase 접근 전 False."""
    if not valid_robot_ns(ns):
        return False
    _init().reference(f"{ns}/patrol").set({"phase": "idle", "intake_done": False})
    return True
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd /home/rokey/MediCart/web/backend && env -i PATH="/usr/bin:/bin" PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 venv/bin/python -m pytest test/test_fb_read.py::test_reset_patrol_rejects_bad_ns -q`
Expected: PASS.

- [ ] **Step 5: `/api/patrol/start` 라우트 추가**

`web/backend/app.py` 의 `patrol_advance` 함수(라우트 `@app.post("/api/patrol/advance")`) 블록 **바로 아래**에 추가:
```python
@app.post("/api/patrol/start")
def patrol_start():
    """순회 문진 깨끗한 시작 — mission_pool 정리 + patrol stale 리셋 + patrol_intake_mission 발행.
    body {ns, stops, home}. staff(/api/patrol prefix)."""
    ns = _req_ns()
    body = request.get_json(force=True, silent=True) or {}
    try:
        fb_read.clear_missions(ns)
        fb_read.reset_patrol(ns)
        mid, _ = fb_read.push_mission(
            ns, "patrol_intake_mission",
            {"stops": body.get("stops") or [], "home": body.get("home")})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    return jsonify({"ok": True, "id": mid})
```

- [ ] **Step 6: 백엔드 테스트 전체 통과(회귀 가드)**

Run: `cd /home/rokey/MediCart/web/backend && env -i PATH="/usr/bin:/bin" PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 venv/bin/python -m pytest test/ -q`
Expected: 전부 PASS(신규 1건 포함).

- [ ] **Step 7: 커밋**

```bash
cd /home/rokey/MediCart
git add web/backend/fb_read.py web/backend/app.py web/backend/test/test_fb_read.py
git commit -m "feat(web): 순회문진 깨끗한 시작 — /api/patrol/start (clear+reset_patrol+push)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: 프론트 — `acceptArrival` 순수함수 (TDD)

**Files:**
- Modify: `web/frontend/lib/patrol.ts`
- Test: `web/frontend/lib/patrol.test.ts`

배경: 도착 신호 수용 판정을 순수함수로 분리해 엄격순서·ready·잠금을 단위테스트한다.

- [ ] **Step 1: 실패 테스트 추가**

`web/frontend/lib/patrol.test.ts` 의 import 줄을 다음으로 교체:
```ts
import { PATROL_STOPS, decideAfterScan, nextStop, acceptArrival } from "./patrol";
```
그리고 파일 끝(마지막 `});` 다음)에 추가:
```ts
describe("acceptArrival (엄격순서 + ready + async잠금)", () => {
  const base = { polledPhase: "arrived", polledIdx: 0, lastIdx: -1, ready: true, arriving: false };
  it("ready 아니면 거부", () => {
    expect(acceptArrival({ ...base, ready: false })).toBe(false);
  });
  it("arriving(잠금) 중이면 거부", () => {
    expect(acceptArrival({ ...base, arriving: true })).toBe(false);
  });
  it("phase!=='arrived' 거부", () => {
    expect(acceptArrival({ ...base, polledPhase: "idle" })).toBe(false);
  });
  it("idx 누락 거부", () => {
    expect(acceptArrival({ ...base, polledIdx: undefined })).toBe(false);
  });
  it("다음 순번(idx===lastIdx+1)만 수용", () => {
    expect(acceptArrival({ ...base, lastIdx: -1, polledIdx: 0 })).toBe(true);
    expect(acceptArrival({ ...base, lastIdx: 0, polledIdx: 1 })).toBe(true);
  });
  it("중복(같은 idx)·점프(+2) 거부", () => {
    expect(acceptArrival({ ...base, lastIdx: 0, polledIdx: 0 })).toBe(false);
    expect(acceptArrival({ ...base, lastIdx: 0, polledIdx: 2 })).toBe(false);
  });
});
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd /home/rokey/MediCart/web/frontend && npx vitest run lib/patrol.test.ts`
Expected: FAIL — `acceptArrival is not a function` (또는 import 해결 실패).

- [ ] **Step 3: acceptArrival 구현**

`web/frontend/lib/patrol.ts` 끝에 추가:
```ts
// 도착(arrived) 신호를 수용할지 판정 — 엄격순서(다음 순번만) + ready(리셋 관측) + async잠금.
export function acceptArrival(opts: {
  polledPhase: string;
  polledIdx: number | undefined;
  lastIdx: number;
  ready: boolean;
  arriving: boolean;
}): boolean {
  const { polledPhase, polledIdx, lastIdx, ready, arriving } = opts;
  if (!ready || arriving) return false;
  if (polledPhase !== "arrived" || typeof polledIdx !== "number") return false;
  return polledIdx === lastIdx + 1;
}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd /home/rokey/MediCart/web/frontend && npx vitest run lib/patrol.test.ts`
Expected: PASS(신규 6 케이스 포함).

- [ ] **Step 5: 커밋**

```bash
cd /home/rokey/MediCart
git add web/frontend/lib/patrol.ts web/frontend/lib/patrol.test.ts
git commit -m "feat(web): 순회 도착 수용 순수함수 acceptArrival(엄격순서+ready+잠금)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: 프론트 — `startPatrol` API + 오버레이 엄격순서 결선

**Files:**
- Modify: `web/frontend/lib/api.ts` (sendPatrolAdvance 인접, ~138)
- Modify: `web/frontend/components/RoundsIntakeOverlay.tsx`

배경: 오버레이가 시작 시 `startPatrol`(깨끗한 시작)을 호출하고, `readyRef`/`arrivingRef` + `acceptArrival` 로 도착을 엄격순서로만 처리한다. moving 메시지는 직전 환자명 대신 일반 문구.

- [ ] **Step 1: api.startPatrol 추가**

`web/frontend/lib/api.ts` 의 `sendPatrolAdvance` 함수 정의 **바로 아래**에 추가:
```ts
export async function startPatrol(ns: string, body: { stops: unknown[]; home: unknown }) {
  const r = await fetch(`${API_BASE}/api/patrol/start`, {
    method: "POST", credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ns, ...body }),
  });
  return r.json() as Promise<{ ok: boolean; id?: string; error?: string }>;
}
```

- [ ] **Step 2: 오버레이 import 보강**

`web/frontend/components/RoundsIntakeOverlay.tsx` 상단 api import 블록을 다음으로 교체:
```ts
import {
  getRooms, getPatient, pushMission, verifyIdentify, setIntakeStatus,
  getPatrolPhase, sendPatrolAdvance, startPatrol,
} from "@/lib/api";
import { acceptArrival } from "@/lib/patrol";
```
(`QrScanner`·`IntakeForm` import 줄은 그대로 둔다.)

- [ ] **Step 3: ref 2개 추가**

`const advancingRef = useRef(false);` 줄 **바로 아래**에 추가:
```ts
  const readyRef = useRef(false);      // startPatrol 성공/idle 관측 후 도착 수용 허용
  const arrivingRef = useRef(false);   // arriveAt async 동안 poll 재진입 차단(동기 잠금)
```

- [ ] **Step 4: 시작 effect — startPatrol + ready 초기화**

다음 블록(시작 effect 전체):
```ts
  useEffect(() => {
    if (!active) return;
    setPhase("starting"); setIdx(0); setResults([]); setWarn(""); setAborted(false);
    lastArrivedRef.current = -1; advancingRef.current = false;
    let cancelled = false;
    (async () => {
      try {
        const stopsPayload = stops.map((s) => ({
          x: s.x, y: s.y, yaw: s.yaw ?? 0, room: s.room, label: s.label,
        }));
        await pushMission(ns, "patrol_intake_mission", { stops: stopsPayload, home: dock });
      } catch { /* 무시하고 진행 — 로봇 미연결 시 수동 버튼 폴백 */ }
      if (!cancelled) setPhase("moving");
    })();
    return () => { cancelled = true; };
  }, [active, ns]); // eslint-disable-line react-hooks/exhaustive-deps
```
을 아래로 교체:
```ts
  useEffect(() => {
    if (!active) return;
    setPhase("starting"); setIdx(0); setResults([]); setWarn(""); setAborted(false);
    lastArrivedRef.current = -1; advancingRef.current = false;
    readyRef.current = false; arrivingRef.current = false;
    let cancelled = false;
    (async () => {
      const stopsPayload = stops.map((s) => ({
        x: s.x, y: s.y, yaw: s.yaw ?? 0, room: s.room, label: s.label,
      }));
      try {
        const r = await startPatrol(ns, { stops: stopsPayload, home: dock });
        if (r?.ok) readyRef.current = true;   // 백엔드 reset 완료 → 이 시점부터 fresh
        else throw new Error(r?.error || "startPatrol 실패");
      } catch {
        // 폴백: 깨끗한 시작 없이 직접 push — ready 는 idle 관측으로만
        await pushMission(ns, "patrol_intake_mission", { stops: stopsPayload, home: dock }).catch(() => {});
      }
      if (!cancelled) setPhase("moving");
    })();
    return () => { cancelled = true; };
  }, [active, ns]); // eslint-disable-line react-hooks/exhaustive-deps
```

- [ ] **Step 5: arriveAt — 동기 잠금 set/해제**

다음 블록(arriveAt 전체):
```ts
  const arriveAt = useCallback((i: number) => {
    if (i < 0 || i >= stops.length) return;
    lastArrivedRef.current = i;
    setIdx(i);
    setWarn(""); setScanPid("");
    const room = stops[i].room;
    (async () => {
      let apid = "", name = "";
      try {
        // /api/rooms 응답은 { rooms: {...} } 형태 — MapView 와 동일하게 .rooms 로 접근.
        const resp = await getRooms();
        const roomsMap = (resp?.rooms as Record<string, { patient?: string }> | undefined) ?? {};
        apid = roomsMap[room]?.patient ?? "";
        if (apid) { const ap = await getPatient(apid).catch(() => null); name = ap?.성명 ?? ""; }
      } catch { apid = ""; name = ""; }
      setAssigned({ pid: apid, name });
      if (apid) beginScan();           // 배정환자 있음 → QR 스캔
      else setPhase("noassign");       // 배정환자 없음 → 안내 후 자동 다음
    })();
  }, [stops, beginScan]);
```
을 아래로 교체(진입 시 동기 잠금, async 종료 시 해제):
```ts
  const arriveAt = useCallback((i: number) => {
    if (i < 0 || i >= stops.length) { arrivingRef.current = false; return; }
    arrivingRef.current = true;        // 진입 동기 잠금(poll/수동 경로 공통)
    lastArrivedRef.current = i;
    setIdx(i);
    setWarn(""); setScanPid("");
    const room = stops[i].room;
    (async () => {
      let apid = "", name = "";
      try {
        // /api/rooms 응답은 { rooms: {...} } 형태 — MapView 와 동일하게 .rooms 로 접근.
        const resp = await getRooms();
        const roomsMap = (resp?.rooms as Record<string, { patient?: string }> | undefined) ?? {};
        apid = roomsMap[room]?.patient ?? "";
        if (apid) { const ap = await getPatient(apid).catch(() => null); name = ap?.성명 ?? ""; }
      } catch { apid = ""; name = ""; }
      setAssigned({ pid: apid, name });
      if (apid) beginScan();           // 배정환자 있음 → QR 스캔
      else setPhase("noassign");       // 배정환자 없음 → 안내 후 자동 다음
      arrivingRef.current = false;     // phase 안정 후 잠금 해제
    })();
  }, [stops, beginScan]);
```

- [ ] **Step 6: poll — acceptArrival 로 게이팅 + ready(idle 관측)**

다음 블록(poll effect 의 try 본문):
```ts
        const p = await getPatrolPhase(ns);
        if (phaseRef.current === "returning") {
          if (p.phase === "idle") setPhase("summary");
          return;
        }
        if (
          p.phase === "arrived" && typeof p.stop?.idx === "number" &&
          p.stop.idx !== lastArrivedRef.current &&
          (phaseRef.current === "moving" || phaseRef.current === "starting")
        ) {
          arriveAt(p.stop.idx);
        }
```
을 아래로 교체:
```ts
        const p = await getPatrolPhase(ns);
        if (phaseRef.current === "returning") {
          if (p.phase === "idle") setPhase("summary");
          return;
        }
        if (!readyRef.current && p.phase === "idle") readyRef.current = true;   // 리셋 관측(백업)
        if (acceptArrival({
          polledPhase: p.phase, polledIdx: p.stop?.idx,
          lastIdx: lastArrivedRef.current, ready: readyRef.current, arriving: arrivingRef.current,
        })) {
          arriveAt(p.stop!.idx!);      // arriveAt 진입에서 arrivingRef=true 로 잠금
        }
```

- [ ] **Step 7: finishStop — moving 전환 시 assigned 초기화**

다음 블록:
```ts
  const finishStop = useCallback(() => {
    if (advancingRef.current) return;
    advancingRef.current = true;
    sendPatrolAdvance(ns).catch(() => {});
    if (lastArrivedRef.current + 1 >= stops.length) setPhase("returning");
    else setPhase("moving");          // 다음 도착 신호 대기
  }, [stops.length]);
```
을 아래로 교체:
```ts
  const finishStop = useCallback(() => {
    if (advancingRef.current) return;
    advancingRef.current = true;
    sendPatrolAdvance(ns).catch(() => {});
    setAssigned({ pid: "", name: "" });   // 다음 이동 시 직전 환자명 잔상 제거
    if (lastArrivedRef.current + 1 >= stops.length) setPhase("returning");
    else setPhase("moving");          // 다음 도착 신호 대기
  }, [stops.length]); // eslint-disable-line react-hooks/exhaustive-deps
```

- [ ] **Step 8: moving 메시지 — 일반 문구로**

다음 블록(시작/이동/복귀 메시지 렌더):
```tsx
          {phase === "starting" && "순회 문진을 가동합니다"}
          {phase === "moving" && (assigned.name ? `${assigned.name}님께 이동 중` : `${stop?.label ?? ""} 이동 중`)}
          {phase === "returning" && "순회 완료 — 복귀·도킹 중"}
```
을 아래로 교체:
```tsx
          {phase === "starting" && "순회 문진을 가동합니다"}
          {phase === "moving" && (lastArrivedRef.current < 0 ? "첫 병상으로 이동 중" : "다음 병상으로 이동 중")}
          {phase === "returning" && "순회 완료 — 복귀·도킹 중"}
```

- [ ] **Step 9: 타입검사 + 단위테스트**

Run: `cd /home/rokey/MediCart/web/frontend && npx tsc --noEmit && npx vitest run`
Expected: tsc 에러 0, vitest 전부 PASS.

- [ ] **Step 10: 영향도 확인 — startPatrol/pushMission 사용처**

Run: `cd /home/rokey/MediCart/web/frontend && grep -rn "startPatrol\|patrol_intake_mission\|acceptArrival" components/RoundsIntakeOverlay.tsx lib/api.ts lib/patrol.ts`
Expected: 오버레이가 `startPatrol`(시작)+폴백 `pushMission` 사용, `acceptArrival` import·사용 확인. 다른 컴포넌트 영향 없음.

- [ ] **Step 11: 커밋**

```bash
cd /home/rokey/MediCart
git add web/frontend/lib/api.ts web/frontend/components/RoundsIntakeOverlay.tsx
git commit -m "fix(web): 순회문진 엄격순서 — startPatrol(깨끗한 시작)+acceptArrival 게이팅

stale patrol/phase 로 첫 환자 건너뛰고 '이동 중' 조기 렌더되던 버그 해소.
ready(리셋 관측)+arriving(async 잠금)+idx===lastArrived+1 로만 도착 수용.
moving 메시지는 직전 환자명 대신 일반 문구.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: 전체 검증 + 런타임 안내

**Files:** 없음(검증 전용).

- [ ] **Step 1: 프론트 단위테스트 + 타입검사**

Run: `cd /home/rokey/MediCart/web/frontend && npx vitest run && npx tsc --noEmit`
Expected: 전부 PASS, tsc 0.

- [ ] **Step 2: 백엔드 테스트**

Run: `cd /home/rokey/MediCart/web/backend && env -i PATH="/usr/bin:/bin" PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 venv/bin/python -m pytest test/ -q`
Expected: 전부 PASS.

- [ ] **Step 3: 사용자 런타임 확인 안내(출력만, 실행 금지)**

다음을 사용자에게 안내:
  1. `web-restart build` 로 프론트 재빌드·기동.
  2. 로봇3 stack 구동(`loc 3`→`nav 3`→`scenario-a`) 상태에서, **이전 run의 stale `robot3/patrol` 이 남아 있어도** 순회문진 시작 시:
     - 첫 환자에서 "이동 중" 깜빡임 없이 scan→intake 진행
     - 문진 완료해야 "다음 병상으로 이동 중" → 다음 환자
     - mission_pool 유령 goto 가 정리되고 단일 patrol_intake_mission 만 남는지
  3. RTDB `robot3/patrol` 이 시작 직후 `{phase:idle,intake_done:false}` 로 리셋되는지.

---

## Self-Review

**Spec coverage:**
- A 깨끗한 시작(`/api/patrol/start`+`reset_patrol`) → Task 1. ✅
- B 웹 엄격순서(`acceptArrival`+ready+arriving+startPatrol) → Task 2(순수함수)+Task 3(결선). ✅
- C 이동 메시지 정정 → Task 3 Step 7·8. ✅
- E 에러 처리(startPatrol 폴백, 수동 버튼) → Task 3 Step 4(폴백). 수동 버튼/noassign 기존 유지. ✅
- F 테스트(acceptArrival·reset_patrol) → Task 1·2. ✅
- 로봇 medicart_ws 무변경 → 전 태스크 web 한정. ✅

**Placeholder scan:** TBD/TODO 없음. 모든 코드블록 실제 내용. ✅

**Type consistency:** `acceptArrival({polledPhase,polledIdx,lastIdx,ready,arriving})` 시그니처가 Task 2 정의와 Task 3 Step 6 호출 일치. `startPatrol(ns,{stops,home})` Task 3 Step 1 정의·Step 4 호출 일치. `reset_patrol(ns)` Task 1 정의·라우트 호출 일치. ✅
