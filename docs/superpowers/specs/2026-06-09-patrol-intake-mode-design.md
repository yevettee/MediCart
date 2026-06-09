# 순회 문진 모드 (Patrol Intake Mode) — 설계

> 작성일: 2026-06-09 · 대상: `MediCart/web` (Next.js 프론트 + Flask 백엔드 + RTDB) · 브랜치: integration

## 1. 목적

의료진 이상 등급이 홈에서 **"순회 문진 시작"** 버튼을 누르면, 로봇이 101호 1번·2번 병상으로
순차 이동하며 각 병상에서 환자 QR을 스캔받아 **순회당 1회 문진**을 자동으로 수행한다.
스캔이 없으면 1분 후 다음 호실로 넘어가고, 두 병상을 모두 마치면 홈으로 복귀해 도킹한다.

전체 흐름은 **단일 풀스크린 오버레이 상태머신**(기존 `FollowOverlay` 패턴)으로 브라우저가
오케스트레이션한다. 라우트 이동 없이 한 컴포넌트 안에서 단계(step)를 전환한다.

## 2. 핵심 결정 (브레인스토밍 확정)

- **데이터 모델**: 순회 회차 기반. 순회 시작 시 전체 환자 `intake_done = false` 일괄 리셋 →
  QR 스캔 시 `intake_done`이 false면 문진, true면 다음 호실. 문진 제출 성공 시 true.
- **아키텍처**: 단일 풀스크린 오버레이 상태머신(라우트 이동 없음, 상태·복귀 한 곳에 응집).
- **도착 판정**: 로봇 pose가 타겟 반경 내 진입 시 도착(`lib/follow.ts` `nearestArrival` 재사용).
- **로그인 게이트**: staff 이상(`roleAtLeast(role, "staff")`).
- **정류장**: `t101_1`, `t101_2` 두 곳 고정(상수). 추후 확장 여지만 남김.

## 3. 데이터 모델 (RTDB)

환자 노드에 완료 플래그를 추가한다. 기존 노드 구조와 형제 레벨:

```
patients/{pid}/
  info: {...}
  vitals: {...}
  intake: {...}        # 기존 자가문진 노드 (그대로)
  visits: [...]        # 기존 외래방문 (그대로)
  intake_done: <bool>  # 신규: 이번 순회에서 문진 완료 여부
```

- **순회 시작**: 전 환자 `intake_done = false` 일괄 set. 환자 컬렉션이 작아 1회 bulk write로 충분.
  룸→환자 명부가 없어도 "순회당 1회"가 보장된다(스캔된 환자의 플래그만으로 분기).
- **분기**: `intake_done == false` → 문진 필요(문진표), `true` → 다음 호실.
- **완료**: 문진표 제출 성공 시 해당 pid `intake_done = true`.

> 기존 자가문진/외래방문 흐름과 독립. `intake_done`은 순회 문진 전용 회차 플래그다.

## 4. 백엔드 (Flask, 최소 추가)

### 4.1 `web/backend/fb_read.py`
```python
def reset_intake_flags():
    """순회 시작 — 전 환자 intake_done=False 일괄 리셋. 갱신된 pid 수 반환."""
    ref = _init().reference("patients")
    raw = ref.get() or {}
    updates = {f"{pid}/intake_done": False for pid in raw.keys()}
    if updates:
        ref.update(updates)
    return len(updates)

def mark_intake_done(pid):
    """문진 완료 — 해당 환자 intake_done=True."""
    if not valid_pid(pid):
        return False
    _init().reference(f"patients/{pid}/intake_done").set(True)
    return True
```

### 4.2 `web/backend/patients.py`
`patient_node_to_api`에 `intake_done` 노출(기본 False):
```python
out["intake_done"] = bool(node.get("intake_done"))
```

### 4.3 `web/backend/app.py`
staff 이상 인증(`_require_auth` 기존 패턴) 라우트 2개:
```python
@app.post("/api/patrol/reset")          # → {"ok": True, "count": n}
@app.post("/api/patrol/intake-done")    # body {pid} → {"ok": True}
```

## 5. 프론트엔드 (App Router, 화이트테마)

> `web/frontend/AGENTS.md`: 이 Next.js는 일반 지식과 다름 — 코드 작성 전
> `node_modules/next/dist/docs/` 의 해당 가이드를 먼저 확인하고 App Router 규칙을 따른다.

### 5.1 재사용 추출 (DRY)
- **`lib/useQrScanner.ts`** — `app/qr/page.tsx`의 웹캠 + jsQR 디코드 루프를 훅으로 추출.
  반환: `{ videoRef, camOn, camErr, start, stop }` + `onDecode(raw)` 콜백.
  `/qr` 페이지와 오버레이가 공유. (PID 형식 검증/쿨다운은 호출측 책임으로 유지)
- **`components/IntakeForm.tsx`** — `app/intake/page.tsx`의 `SECTIONS`·`FieldInput`·제출 로직을
  컴포넌트로 추출. props: `{ pid, onSaved?(): void, embedded?: boolean }`.
  기존 `app/intake/page.tsx`는 이 컴포넌트를 쓰는 얇은 래퍼가 된다(환자/의료진 분기·라우팅은 페이지에 유지).

### 5.2 신규 순수 로직 — `lib/patrol.ts`
```ts
export type PatrolStop = { key: string; label: string };
export const PATROL_STOPS = ["t101_1", "t101_2"] as const;

// 스캔된 환자 → 다음 동작
export function decideAfterScan(p: { intake_done?: boolean } | null):
  "intake" | "skip" | "unknown" {
  if (!p) return "unknown";
  return p.intake_done ? "skip" : "intake";
}

// 현재 인덱스 → 다음 인덱스 또는 복귀 신호
export function nextStop(idx: number, total: number): number | "return" {
  return idx + 1 < total ? idx + 1 : "return";
}
```

### 5.3 오버레이 — `components/PatrolIntakeOverlay.tsx`
`FollowOverlay`와 동일하게 `active`일 때만 SSE(`/api/stream`) 자가 구독, pose/dock 수신.
상태(step) 기반 풀스크린 렌더. props:
```ts
type Props = {
  active: boolean;
  ns: string;
  targets: Record<string, GotoTarget>;  // /api/targets
  onExit: () => void;
};
```

### 5.4 홈 버튼 — `app/page.tsx`
회진 버튼과 동일한 확인→오버레이 패턴으로 **staff 이상**에게 "순회 문진 시작" 버튼 추가.
`confirming2/patrolActive` 상태로 `PatrolIntakeOverlay`를 띄운다. (환자 역할엔 미노출)

### 5.5 api.ts 추가
```ts
export async function resetIntakeRound(): Promise<{ ok: boolean; count: number }>;
export async function markIntakeDone(pid: string): Promise<{ ok: boolean }>;
// Patient 타입에 intake_done?: boolean 추가
```

## 6. 상태머신 (PatrolIntakeOverlay)

```
[시작] active=true → resetIntakeRound() 호출
intro      "순회 문진을 가동합니다." (풀스크린, ~2.5s)
─ 각 정류장 idx ∈ {0:t101_1, 1:t101_2} 순차 ─
  moving   pushMission(ns,"goto",{x,y,yaw}); "101호 {N}번으로 이동 중…"
           nearestArrival(pose, [현재타겟]) 반경 진입 → scanning
           (90s 내 미도착 → "이동 지연 — 위치 확인" + 재시도/중단)
  scanning QR 스캐너로 부드럽게 전환; 카메라 ON; 60s 타이머
           "101호 {N}번 — 환자 QR을 스캔해 주세요"
           ├ 유효 QR(P-YYYY-NNNN) → getPatient(pid)
           │   ├ decideAfterScan=intake → step=intake (IntakeForm pid)
           │   │       제출 성공 → markIntakeDone(pid) → advance
           │   ├ decideAfterScan=skip   → skipMsg("이미 문진 완료", ~2.5s) → advance
           │   └ unknown(미등록)        → "등록되지 않은 QR" 잠깐, 계속 대기
           └ 60s 무스캔 → timeoutMsg("시간 초과 — 다음 호실로 이동", 5s) → advance
  advance  nextStop(idx,total): 다음 idx면 moving, "return"이면 returning
returning  returnHome(ns, dock)  (saveMode stop round 없음 — 순회는 goto 기반)
           실제: pushMission(ns,"goto",{...dock, dock_after:true}); "복귀 중…"
           dock.is_docked=true → done
done       onExit() → 오버레이 닫기

[항시] "순회 중단" 버튼 → 진행 중 이동 mission_cancel 후 returning 으로.
```

- 타이머: intro 2.5s, QR 대기 60s, timeout 메시지 5s, skip 메시지 2.5s.
- 도착 반경: `nearestArrival` 기본 enterR=1.0, exitR=1.2.

## 7. 엣지 케이스

| 상황 | 처리 |
|---|---|
| 카메라 열기 실패 | 에러 표시 + "건너뛰기/재시도" 버튼 |
| 이동 90s 내 미도착 | "이동 지연 — 위치 확인" + 재시도/중단 |
| pose 미수신 | "위치 수신 대기…" |
| 미등록/형식오류 QR | 무시하고 스캔 계속(advance 안 함) |
| 중단 버튼 | 현재 이동 mission_cancel → returning(복귀 후 도킹). create3 dock/undock 비선점 규칙 준수 |
| targets에 t101_1/2 없음 | 버튼 비활성 + 안내(타겟 미설정) |

## 8. 테스트

- **vitest** (`lib/patrol.test.ts`): `decideAfterScan`(intake/skip/unknown), `nextStop`(다음/복귀 경계),
  `PATROL_STOPS` 순서. `nearestArrival`는 기존 `follow.test.ts` 커버.
- **pytest** (`web/backend/test/`): `patient_node_to_api`가 `intake_done` 포함(기본 False/True 노드),
  `reset_intake_flags`(updates 구성), `/api/patrol/reset`·`/api/patrol/intake-done` 인증·동작.

## 9. 영향도

- 신규: `lib/useQrScanner.ts`, `lib/patrol.ts`, `components/IntakeForm.tsx`,
  `components/PatrolIntakeOverlay.tsx`, 백엔드 라우트 2개·헬퍼 2개.
- 수정(추출 리팩터): `app/qr/page.tsx`(훅 사용), `app/intake/page.tsx`(폼 컴포넌트 사용),
  `app/page.tsx`(버튼), `lib/api.ts`(2함수+타입), `patients.py`(필드 1개).
- 추출 리팩터 후 `/qr`·`/intake` 기존 동작 동일 유지(회귀 없음) — 단위/수동 검증으로 확인.
- 런타임(실제 goto 이동·복귀·도킹) 검증은 사용자가 직접 로봇 구동 후 확인.

## 10. 비범위 (YAGNI)

- 정류장 동적 설정 UI(고정 2곳).
- 룸→환자 명부 매핑(QR로 동적 식별).
- 문진 결과의 별도 리포트/집계 화면.
