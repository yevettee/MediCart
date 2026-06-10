# 순회문진 깨끗한 시작 + 웹 엄격 순서 — 설계

- **작성일**: 2026-06-10 · 대상: `MediCart/web` (Next.js 프론트 + Flask 백엔드 + RTDB)
- **문제**: 웹 순회문진에서 첫 환자 도착 직후, 문진 완료 전에 `OOO님께 이동 중`(moving) 메시지가 떠 다음 환자로 넘어간 것처럼 렌더링된다.
- **근본 원인(확정)**: 웹이 `{ns}/patrol`(phase·stop) 을 **stale/경합 상태로 신뢰**한다.
  - 이전 run의 잔여 `patrol = {phase:'arrived', stop:{idx:N}}` 가 남아 있으면, 시작 직후 poll이 그 stale `arrived idx N` 을 읽어 `lastArrived(-1) !== N` → `arriveAt(N)` 으로 **첫 환자(idx 0)를 건너뛰고** 그 환자에게 "이동 중"을 띄운다.
  - `arriveAt` 의 배정환자 로드가 async라 그 사이 phase 가 여전히 `moving` → poll 재진입(경합) 여지.
  - 덤으로 mission_pool 에 유령 `goto`(홈복귀·맵클릭)가 쌓여 순회 후 로봇이 엉뚱하게 움직인다.
- **접근(승인)**: ① 깨끗한 시작 + 웹 엄격 순서. 웹/백엔드만 수정(로봇 medicart_ws 재빌드 불필요 — RTDB write 로 stale 제거).

---

## A. 깨끗한 시작 — 백엔드 신규 엔드포인트

순회문진 시작을 **하나의 원자적 동작**으로 묶는다.

- **신규 라우트** `POST /api/patrol/start` (staff 등급, `_req_ns()` 로 ns) — body `{stops, home}`:
  1. `fb_read.clear_missions(ns)` — mission_pool 정리(유령 goto 제거).
  2. `fb_read.reset_patrol(ns)` — `{ns}/patrol` 을 `{"phase":"idle","intake_done":False}` 로 **set**(이전 stop 제거).
  3. `fb_read.push_mission(ns, "patrol_intake_mission", {stops, home})` — 새 미션 발행. 반환 `{ok, id}`.
- **신규 fb_read 함수** `reset_patrol(ns)`:
  ```python
  def reset_patrol(ns=PRIMARY_NS):
      """순회 시작 전 stale 상태 제거 — patrol 노드를 idle/미완료로 set."""
      if not valid_robot_ns(ns):
          return False
      _init().reference(f"{ns}/patrol").set({"phase": "idle", "intake_done": False})
      return True
  ```
  (`set` 으로 stop 키까지 제거. 순수 검증부 `valid_robot_ns` 는 단위테스트 가능.)
- **프론트 api.ts** 신규:
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
- **RoundsIntakeOverlay 시작부**: 기존 `pushMission(ns,"patrol_intake_mission",{stops,home})` → `startPatrol(ns,{stops:stopsPayload, home:dock})`.

---

## B. 웹 엄격 순서 — RoundsIntakeOverlay

도착 수용 판정을 **순수 함수로 추출**해 테스트하고, 오버레이에서 그 함수로 게이팅한다.

- **신규 순수 함수** `lib/patrol.ts` 에 `acceptArrival`:
  ```ts
  // 도착(arrived) 신호를 수용할지 판정. 엄격 순서 + ready(idle 관측) + async 잠금.
  export function acceptArrival(opts: {
    polledPhase: string; polledIdx: number | undefined;
    lastIdx: number; ready: boolean; arriving: boolean;
  }): boolean {
    const { polledPhase, polledIdx, lastIdx, ready, arriving } = opts;
    if (!ready || arriving) return false;
    if (polledPhase !== "arrived" || typeof polledIdx !== "number") return false;
    return polledIdx === lastIdx + 1;     // 엄격: 다음 순번만
  }
  ```
- **오버레이 상태/ref 추가**:
  - `readyRef`(ref, boolean): **`startPatrol` 가 성공 반환하면 즉시 `true`**(백엔드 reset_patrol 이 동기적으로 patrol=idle 을 만든 뒤 반환하므로, 이 시점부터의 arrived 는 fresh). 백업으로 poll 이 `patrol.phase === "idle"` 을 관측해도 `true`. 그 전엔 어떤 arrived 도 무시(stale 차단, 클록 스큐 무관). startPatrol 폴백(직접 push) 경로에선 idle 관측으로만 ready.
  - `arrivingRef`(ref, boolean): `arriveAt` 진입 즉시 동기 `true`, 배정환자 로드(async) 완료해 phase(scanning/noassign) 세팅 직후 `false`. async 창 동안 poll 재진입 차단.
- **poll 교체**(현재 `phaseRef==="moving"|"starting"` 조건 → `acceptArrival` 로):
  ```ts
  const p = await getPatrolPhase(ns);
  if (phaseRef.current === "returning") { if (p.phase === "idle") setPhase("summary"); return; }
  if (!readyRef.current && p.phase === "idle") readyRef.current = true;   // 리셋 관측
  if (acceptArrival({ polledPhase: p.phase, polledIdx: p.stop?.idx,
                      lastIdx: lastArrivedRef.current, ready: readyRef.current,
                      arriving: arrivingRef.current })) {
    arrivingRef.current = true;            // 동기 잠금
    arriveAt(p.stop!.idx!);
  }
  ```
- **arriveAt**: `arrivingRef.current = true`(진입 동기 — 위 poll 에서 이미 set), async 로드 후 `beginScan()`/`setPhase("noassign")` 직후 `arrivingRef.current = false`.
- **start effect**: `readyRef.current=false`, `arrivingRef.current=false`, `lastArrivedRef.current=-1` 초기화. `startPatrol` 호출.

---

## C. 이동 메시지 정정

- `moving` 단계 텍스트:
  - 첫 도착 전(`lastArrived < 0`): "순회 시작 — 첫 병상으로 이동 중".
  - 정차 종료 후 다음으로(`lastArrived >= 0`): **"다음 병상으로 이동 중"** (직전 환자명 표시 금지).
- `finishStop()` 에서 `moving` 전환 시 `setAssigned({pid:"",name:""})` 로 초기화 → 이전 환자명 잔상 제거.

---

## D. 데이터 흐름

```
[시작] startPatrol → clear_missions + reset_patrol(idle) + push(patrol_intake_mission)
로봇: idle→undock→stop0 도착 → patrol={arrived, idx0}
웹: idle 관측(ready=true) → arrived idx0(=lastArrived+1, !arriving) → 잠금 → arriveAt(0) → scan→intake
   → 완료 → sendPatrolAdvance(intake_done=true) → assigned 초기화 → moving("다음 병상…")
로봇: stop1 도착 → 웹 arrived idx1(=0+1) 수용 → … → 마지막 후 home(-0.89,-0.66)+dock → patrol idle → 웹 summary
```

stale `arrived idx N`(이전 run)은 reset 으로 idle 이 된 뒤에야 ready 가 되고, 그마저 `idx===lastIdx+1` 이 아니면 무시 → 첫 환자 건너뜀 제거.

---

## E. 에러 처리

- `startPatrol` 실패(네트워크/4xx) → 기존 `pushMission` 직접 호출로 폴백 + 인라인 경고(로봇 미연결 시에도 수동 진행 가능).
- 로봇 미도착(patrol 갱신 없음) → 기존 "도착했어요 — 스캔 시작" 수동 버튼(`manualArrive`) 유지. 수동 도착도 `acceptArrival` 우회(직접 arriveAt) — 단 `arrivingRef` 잠금은 적용.
- `ready` 가 일정 시간(예: 8s) 미관측 → 콘솔 경고 + 수동 버튼만으로 진행 허용(고착 방지). (구현은 수동 버튼이 이미 ready 무관하게 동작하므로 자연 충족.)

---

## F. 테스트

- **백엔드**(`test/test_fb_read.py`): `reset_patrol` 는 firebase 의존이라 순수부만 — `valid_robot_ns` 거부 케이스. 라우트는 기존 패턴(통합은 사용자).
- **프론트**(`lib/patrol.test.ts`): `acceptArrival` 단위테스트:
  - ready=false → false; arriving=true → false.
  - phase!=="arrived" → false; idx 누락 → false.
  - idx === lastIdx+1 → true; idx === lastIdx(중복) → false; idx === lastIdx+2(점프) → false.
- **런타임**(사용자): 로봇 구동 후 첫 환자에서 "이동 중" 깜빡임 없이 scan→intake 진행, 완료해야 다음으로, stale 잔여 상태에서 시작해도 첫 환자부터 정상.

---

## 영향도
- 신규: 백엔드 `/api/patrol/start` + `fb_read.reset_patrol`; 프론트 `api.startPatrol` + `lib/patrol.acceptArrival`(+test).
- 수정: `RoundsIntakeOverlay.tsx`(시작 호출·poll·arriveAt·moving 메시지·assigned 초기화).
- 로봇 medicart_ws **무변경**(stale 제거를 RTDB write 로 처리). 기존 `sendPatrolAdvance`·`getPatrolPhase` 계약 유지.
