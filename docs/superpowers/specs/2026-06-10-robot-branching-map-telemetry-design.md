# 로봇별 분기 + 맵/텔레메트리 정확성 (하위 프로젝트 A) — 설계

- **작성일**: 2026-06-10 · 대상: `MediCart/web` (Next.js 프론트 + Flask 백엔드 + RTDB)
- **범위**: 전체 웹/DB 리뷰 6항목 중 **A 묶음 = ① 로봇별 홈 분기 · ⑤ 미니맵 오버레이 · ⑥ 경과/LIVE 버그**
- **비범위**: B 묶음(② 등급별 레이아웃 · ③ 웹 디자인 · ④ 문진표 UX) — 별도 스펙
- **전제**: robot3·robot6은 **각각 다른 PC**에서 자기 AMR과 연결돼 자기 데이터를 RTDB `robot3`/`robot6` 노드에 업데이트한다. **웹은 RTDB에서 per-robot 데이터를 끌어다 쓴다**(하드코딩 좌표 없음).

---

## A1. ⑥ 경과/LIVE 버그 — stamp 단위 불일치

### 원인 (확정)
RTDB `{ns}/stamp`는 **밀리초**(예: robot6 `1781056366312`; 로봇측 ward_bridge가 `초×1000`으로 기록). 웹은 `now = Date.now()/1000`(**초**)와 빼서 `age = now - stamp`가 거대 음수가 된다.
- `console/page.tsx`(AmrPanel)·`debug/page.tsx`: `경과` 가 `-1779275530…ms` 표시, `online = age < 3`이 음수라 항상 참 → **STALE인데 LIVE 오판**.
- `app/page.tsx`: AMR online 카운트 `now - s.stamp < 5` 도 동일 버그 → 항상 online으로 셈.

### 수정
공통 순수 헬퍼를 한 곳에 두고 3곳에서 재사용(DRY). stamp·now 를 **ms로 통일**.
```ts
// lib/telemetry.ts (신규)
export function snapAgeMs(stamp?: number): number {
  if (!stamp || stamp <= 0) return Infinity;
  return Date.now() - stamp;          // 둘 다 ms
}
export const isLive = (stamp?: number, thresholdMs = 3000) => snapAgeMs(stamp) < thresholdMs;
```
- `console`/`debug`: `const ageMs = snapAgeMs(snap?.stamp); online = isLive(snap?.stamp);` 표시 `경과 = isFinite(ageMs) ? `${ageMs.toFixed(0)}ms` : "—"`, `warn = ageMs >= 3000`.
- `app/page.tsx` online 카운트: `vals.filter(s => isLive(s?.stamp, 5000)).length`.
- **방어**: 미래/음수 stamp(잘못된 값)는 `snapAgeMs`가 정상 양수 또는 Infinity가 되도록 — 음수면 Infinity 취급(STALE).

### 검증
- 단위테스트(`lib/telemetry.test.ts`, vitest): `snapAgeMs(0)=Infinity`, `snapAgeMs(Date.now()-1000)≈1000`, 미래 stamp → 음수가 아니라 작은 값/Infinity 처리 확인. `isLive` 임계.

---

## A2. ① 로봇별 홈/dock — RTDB에서 per-robot 소싱

### 원인 (확정)
- 각 로봇의 홈 = **도킹 중 `{ns}/amcl_pose`** (RTDB에 이미 존재). 실측: robot3 `(-7.4,-3.1,0.0)`, robot6 `(0.016,-0.078,0.36)` — 서로 다름.
- 그런데 웹은 단일 `targets.dock(-0.354229,-0.118972)`만 사용. `RoundsIntakeOverlay`가 `pushMission(ns,"patrol_intake_mission",{home: dock})`로 **이 단일 dock을 홈으로 로봇에 전달** → robot3 순회 문진이 robot6 홈으로 복귀.

### 수정 — 홈은 RTDB 도킹 pose에서
프론트가 이미 폴링하는 `getAmrs()` 스냅샷에 `{ns}/amcl_pose`(pose)가 있다. **도킹 중인 로봇의 pose = 그 로봇의 홈**.
```ts
// lib/telemetry.ts
export function robotHome(snap?: AmrSnapshot):
  { x: number; y: number; yaw?: number } | null {
  if (snap?.dock?.is_docked && snap.pose) return { x: snap.pose.x, y: snap.pose.y, yaw: snap.pose.yaw };
  return null;   // 미도킹/미수신 → 알 수 없음
}
```
- **`app/page.tsx`**: `amrs` 전체를 상태로 보관(현재는 online 카운트만 계산). 순회 문진(robot3) 시작 시 `home = robotHome(amrs[PATROL_NS]) ?? targets.dock ?? {x,y,...기본}` 를 `RoundsIntakeOverlay`의 `dock` prop으로 전달. → patrol_intake_mission 의 `home`이 robot3 실제 홈이 됨.
- **간호사 투약(robot6, nurse_cart_mission)**: 복귀·도킹은 **로봇이 자체 처리**(round_done → 로봇이 자기 홈으로). 웹이 dock 좌표를 보낼 필요 없음(현 구조 유지).
- **`targets.dock`**: per-robot 홈 용도로는 폐기(미니맵·복귀가 RTDB pose 사용). 콘솔의 수동 'goto dock' 프리셋이 필요하면 generic 프리셋으로만 유지.
- **로봇이 미도킹 상태에서 시작하는 엣지**: `robotHome`이 null → `targets.dock` 폴백 + 경고. (정상 운용은 도크에서 시작)

### 비고 — 로봇측 contract(선택, B/협의)
더 견고히 하려면 각 로봇 PC가 `{ns}/home = {x,y,yaw}`(AMCL initial_pose)를 1회 기록하고 웹이 우선 사용. 본 스펙은 **웹 단독(도킹 pose)** 으로 충분하며, 로봇측 변경 없이 구현.

### 검증
- `robotHome` 단위테스트(도킹+pose→pose, 미도킹→null, pose 없음→null).
- 런타임(사용자): 순회 문진 시작 시 patrol_intake_mission `home`이 robot3 실홈으로 전달되는지 RTDB mission_pool 확인.

---

## A3. ⑤ 미니맵 오버레이 — 좌표 정렬 + targets 렌더

### 원인 (확정)
- `MapView`는 RTDB **`rooms`만** 그리고(`getRooms`), **`targets`(dock·침상 t101_*·t102_1·약품실·호실)는 안 그림**. `rooms`는 백엔드 시드가 없어 거의 비어 있음 → 침상·도크·호실 미표시.
- 좌표 변환이 **맵 PNG의 `mapMeta`(origin·resolution)** 대신 점들의 bounds로 맞춰져 PNG와 어긋날 수 있음.

### 수정
1. **좌표 변환을 mapMeta 기준 표준 ROS 변환으로 교체.** `/api/map`이 `resolution`·`origin`을 노출(ninety.yaml: res 0.05, origin [-5.59,-4.58,0]). PNG 픽셀 = `((world.x - origin.x)/res, H - (world.y - origin.y)/res)`. → 모든 오버레이가 PNG와 정렬.
   - **전제 확인 항목**: 웹이 서빙하는 맵 PNG/yaml(`MAP_PNG`/`MAP_YAML` env)이 **로봇 맵(ninety)** 과 동일해야 함. 기본값이 `ward_map.yaml`이므로 배포 env가 ninety를 가리키는지 점검(불일치 시 정렬 깨짐).
2. **`getTargets` 구독 추가 → targets 오버레이.** 침상(t101_1·t101_2·t102_1)·약품실(pharmacy)·호실(t102) 을 라벨 마커로. 기존 `rooms` 마커 유지.
3. **로봇별 도크 마커**: 각 AMR의 `robotHome(snap)`(도킹 pose)을 dock 아이콘+라벨(`robot3 home`/`robot6 home`)로. (단일 `targets.dock` 대신 per-robot)
4. 마커 스타일: 침상=원+라벨, 약품실=약품 아이콘, 도크=도크 아이콘, 호실=사각. 겹침 시 라벨 오프셋.

### 검증
- 런타임(사용자): 콘솔 미니맵에 도크(로봇별)·침상·약품실·호실이 **맵 위 올바른 위치**에 표시. 로봇 pose 마커와 정렬.
- 좌표 변환 순수 함수(`worldToPixel(origin,res,H)`) 단위테스트.

---

## 영향도
- 신규: `lib/telemetry.ts`(+test).
- 수정: `app/console/page.tsx`·`app/debug/page.tsx`(경과/online), `app/page.tsx`(online 카운트 + amrs 보관 + 순회 문진 home), `components/RoundsIntakeOverlay.tsx`(home prop 출처), `components/MapView.tsx`(mapMeta 변환 + targets/per-robot dock 오버레이).
- 로봇측·DB 스키마 변경 없음(웹 단독). 런타임 검증은 사용자(로봇 구동).
