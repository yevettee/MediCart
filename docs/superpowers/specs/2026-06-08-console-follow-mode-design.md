# 회진(추종) 풀스크린 모드 — 설계 (Design)

**작성일**: 2026-06-08
**대상**: `web/frontend` (홈 `/` 배너 진입) — 회진/추종 풀스크린 안내 + 근접 도착 표시 + 홈 복귀

## 1. 목표

`https://intel.thatshoon.com/` **홈페이지 최상단 배너**로 **회진(추종) 모드** 진입을 노출한다.
배너 클릭 → **재확인 버튼** 표시 → 재확인 시 **즉시** 회진 시작. 시작 시 로봇이 **도크 상태면
자동 undock 후** 추종(이동)을 시작한다(추종은 이동이라 undock 상태가 필수).

회진이 시작되면 브라우저가 **풀스크린 안내 화면**으로 전환되고 AMR이 앞의 대상을 따라간다.
추종 중 약품실·101호 1번·101호 2번에 **1m 이내로 근접**하면 풀스크린 텍스트가 `"OO에 도착"`으로
바뀐다(로봇은 멈추지 않고 계속 추종). 풀스크린 **우하단 '홈 위치로 복귀' 버튼**을 누르면 추종을
멈추고 Docking Station으로 이동해 도킹한다.

> **dock/undock 해석 주의**: 요청 문구 "undock 상태라면 자동으로 dock"은 추종 동작과 모순된다
> (추종하려면 undock 필요). 따라서 **"시작 시 docked면 자동 undock → 회진"** 으로 해석해 반영했다.
> 진짜 '시작 전 도크로 정렬 후 회진'을 원하면 리뷰에서 변경.

## 2. 핵심 원칙 — 프론트엔드 전용, 기존 배관 재사용

회진/추종(`round` 모드)·undock·goto·dock·targets·로봇 pose(SSE)는 **이미 모두 구현돼 있다**.
이 기능은 그것들을 `/console`에서 **오케스트레이션 + 풀스크린 뷰**로 묶는 것이며,
**백엔드·ROS2 코드 변경은 없다.**

재사용하는 기존 인터페이스:

| 기존 자산 | 위치 | 용도 |
| --- | --- | --- |
| `saveMode(action, mode, params)` | `web/frontend/lib/api.ts` | `round` 모드 start/stop |
| `pushMission(action, params?, mode?)` | `web/frontend/lib/api.ts` | `undock`, `goto`(dock_after) |
| `getTargets()` → `{targets}` | `lib/api.ts` / `/api/targets` | 타겟 좌표 |
| SSE `/api/stream` → `AmrSnapshot.pose {x,y,yaw}` | `app/console/page.tsx` | 로봇 실시간 위치 |
| SSE `AmrSnapshot.dock {is_docked}` | 〃 | undock 완료 감지 |
| 타겟 좌표 | `fb_read.targets_seed` (RTDB) | `pharmacy(-9,-9)` · `t101_1(-12,-5)` · `t101_2(-12,-6)` · `dock(-8,-6)` |

**운영 전제(코드 아님)**: 로봇에 `nurse_tracker` 노드가 기동돼 있어야 `round` 모드가
`/{ns}/mode/round/cmd_vel`을 발행해 실제로 움직인다.

## 3. UX 흐름

```
[홈 `/` 최상단 "회진 모드" 배너] 클릭
 → 재확인 버튼 표시 → [확인] 클릭 → 즉시 시작 오케스트레이션:
 1) (docked 이면) pushMission("undock")           // 추종은 이동이라 undock 필수
 2) SSE dock.is_docked == false 까지 대기(타임아웃 20s; 이미 undock이면 즉시 통과)
 3) saveMode("start", "round")                    // 추종 시작
 4) FollowOverlay 풀스크린 ON — "회진 중 — 안내를 따라오세요"
 5) SSE pose 갱신마다 nearestArrival(pose, [pharmacy,t101_1,t101_2], 1.0m)
       → 결과 label 있으면 "<label>에 도착" / 없으면 기본 텍스트
       (로봇은 계속 추종 — 표시만 변경)
 [홈 위치로 복귀] (풀스크린 우하단 버튼)
 6) saveMode("stop", "round")                     // 추종 종료
 7) pushMission("goto", {x:-8, y:-6, yaw, dock_after:true})  // Nav2→dock 체인
 8) 텍스트 "복귀 중…", dock.is_docked == true 되면 오버레이 OFF → /console 복귀
```

## 4. 컴포넌트 설계 (web/frontend)

### 4.1 `nearestArrival` — 순수 함수 (테스트 대상)
`web/frontend/lib/follow.ts` (신규)

```ts
export type Pt = { x: number; y: number };
export type ArrivalTarget = { key: string; label: string; x: number; y: number };

// 히스테리시스: 진입 enterR(1.0m) 이내면 도착, 한번 도착하면 exitR(1.2m) 벗어날 때까지 유지.
// prevKey = 직전에 도착으로 판정된 key(없으면 null). 가장 가까운 타겟 1개를 반환.
export function nearestArrival(
  pose: Pt | undefined,
  targets: ArrivalTarget[],
  prevKey: string | null,
  enterR = 1.0,
  exitR = 1.2,
): ArrivalTarget | null
```

- pose 없으면 `null`.
- 각 타겟까지 유클리드 거리 계산, 가장 가까운 타겟 선택.
- 그 타겟이 `prevKey`와 같으면 `exitR` 기준, 아니면 `enterR` 기준으로 도착 여부 판정.
- 도착이면 타겟 반환, 아니면 `null`.

### 4.2 `FollowOverlay` — 풀스크린 컴포넌트 (신규, 자가완결)
`web/frontend/components/FollowOverlay.tsx`

- props: `{ active: boolean; ns: string; targets: ArrivalTarget[]; onExit: () => void }`
- **SSE 자가 구독**: `active`일 때 컴포넌트가 직접 `EventSource(/api/stream)`를 열어 해당 `ns`의
  `pose`·`dock.is_docked`를 구독한다(홈 페이지가 SSE를 안 띄워도 동작하도록 자가완결). `active=false`면
  EventSource 종료.
- `active`일 때 `position:fixed inset-0 z-50` 풀스크린 렌더.
- 내부 상태 `phase`: `following | returning`.
- 표시 텍스트 우선순위:
  - `phase==='returning'` → "복귀 중…"
  - pose 없음 → "위치 수신 대기…"
  - `nearestArrival(...)` 결과 있음 → "{label}에 도착"
  - 그 외 → "회진 중 — 안내를 따라오세요" (기본, 스펙 리뷰에서 문구 조정 가능)
- 우하단 고정 버튼 "홈 위치로 복귀" → `returning`으로 전환 + 복귀 시퀀스 호출.
- 자가 구독한 `dock.is_docked===true && phase==='returning'` 이면 `onExit()` 호출(오버레이 종료).

### 4.3 홈 페이지 배너 진입 (`app/page.tsx`)
- 홈 랜딩 **최상단(가장 앞)에 "회진 모드" 배너** 추가(눈에 띄는 풀폭 배너).
- 클릭 → **재확인 단계**: 배너가 "회진을 시작할까요? [확인] [취소]" 형태로 전환(또는 confirm 버튼 노출).
- [확인] → 시작 오케스트레이션(4.4) 실행 → `followActive=true`.
- 대상 `ns` = **primary namespace**(`NEXT_PUBLIC_PRIMARY_NS`, 기본 robot6). 홈엔 /console 같은 ns
  선택 UI가 없으므로 설정값 사용.
- `<FollowOverlay active={followActive} ns={primaryNs} targets={arrivalTargets} onExit={()=>setFollowActive(false)} />` 마운트.
- `arrivalTargets` = `getTargets()` 결과에서 `pharmacy/t101_1/t101_2` 만 추림.

### 4.4 오케스트레이션 헬퍼 (`lib/follow.ts`)
- `startFollow(ns, isDocked)`: `isDocked`면 `pushMission("undock")` → `waitDockState(ns,false,20s)` →
  `saveMode("start","round")`. (이미 undock이면 undock 생략)
- `returnHome(ns)`: `saveMode("stop","round")` → `pushMission("goto", {x,y,yaw,dock_after:true})` (dock 타겟 좌표).
- `waitDockState(ns, want, timeoutMs)`: `/api/stream` SSE로 해당 ns `dock.is_docked`가 `want`이 될 때까지
  기다리는 Promise(타임아웃 시 resolve).

## 5. 상태·에러 처리

| 상황 | 처리 |
| --- | --- |
| pose 미수신 | 텍스트 "위치 수신 대기…", 도착 판정 보류 |
| undock 타임아웃(20s) | 토스트/텍스트 경고, 그래도 `round` 시작은 진행(이미 undock 상태일 수 있음) |
| `round`가 안 움직임(nurse_tracker 미기동) | 화면 유지, 운영자가 '복귀'/수동 중지 가능 (코드로 감지 안 함) |
| 복귀 goto 실패(mission_feedback failed) | "복귀 실패 — 다시 시도" 표시, 오버레이 유지 |
| 다중 AMR | 홈 배너는 primary namespace(`NEXT_PUBLIC_PRIMARY_NS`, 기본 robot6) 대상. 오버레이도 해당 ns pose 사용 |

## 6. 테스트

**전제**: 현재 `web/frontend`에는 테스트 러너가 없다(`package.json` scripts = dev/build/start/lint).
순수 함수 `nearestArrival`를 검증하려면 **경량 `vitest` 도입**이 필요하다 → `devDependency`로 `vitest`
추가 + `package.json`에 `"test": "vitest run"` 스크립트 추가(구현 플랜에 포함). 백엔드/ROS는 무변경이라
영향 없음.

- **단위(`vitest`, `nearestArrival`)**: ① 1m 경계(0.9m 도착/1.1m 미도착) ② 최근접 타겟 선택
  ③ pose 없음→null ④ 히스테리시스(도착 후 1.0~1.2m 유지, 1.2m 초과 시 해제) ⑤ 타겟 빈 배열→null.
- **수동 E2E**: 콘솔 '회진 시작' → 로봇 undock+추종 확인 → 약품실 1m 접근 시 "약품실에 도착" 표시 →
  '홈 위치로 복귀' → 로봇이 dock으로 이동·도킹 → 오버레이 종료.

## 7. 범위 밖 (Out of scope)

- 로봇/백엔드 코드 변경(이 기능은 프론트 전용).
- 로봇측 근접 판정(웹에서 수행).
- 추종 대상 카메라 영상/bbox 표시(텍스트 안내만; 추후 확장 가능).
- 도착 시 자동 정지·음성 안내(현재는 텍스트만, 추종 지속).

## 8. 파일 변경 요약

- 신규: `web/frontend/lib/follow.ts` (순수 `nearestArrival` + `startFollow`/`returnHome`/`waitDockState` 헬퍼)
- 신규: `web/frontend/components/FollowOverlay.tsx` (풀스크린 + 자가 SSE 구독)
- 신규: `web/frontend/lib/follow.test.ts` (vitest, `nearestArrival`)
- 수정: `web/frontend/app/page.tsx` (최상단 '회진 모드' 배너 + 재확인 + FollowOverlay 마운트 + arrivalTargets)
- 수정: `web/frontend/package.json` (devDep `vitest` + `"test":"vitest run"`)
