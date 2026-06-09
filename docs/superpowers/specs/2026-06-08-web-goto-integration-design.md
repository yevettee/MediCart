# WEB ↔ dashboard goto 통합 — 설계

**작성일:** 2026-06-08
**목표:** dashboard(AMR측 ROS 노드)에서 검증된 **미니맵 클릭/침상·home 이동(dock-aware)** 기능을
web(PC측, RTDB 전용)에서 실행 가능하도록 통합한다. 경로는
`web → RTDB mission_pool → db_bridge → mission_manager(NavExecutor) → Nav2`.

---

## 1. 배경 / 현재 상태

- **dashboard**(`medicart_ws/src/dashboard`): 자체 HTTP+SSE UI에서 `NavigateToPose`(map 프레임)로
  프리셋 타깃/맵 클릭 이동, dock-aware(도킹 중 일반타깃→먼저 undock / `Docking Station` 도착→자동 dock).
  검증 완료. 본 통합의 **레퍼런스 구현**.
- **web**(`MediCart/web`): ROS 없음. `MapView`가 맵+AMR pose+rooms 렌더 중(클릭 이동 없음).
  control 페이지: 전원명령 + 모드 start/stop 하달. 경로 `push_mission→RTDB mission_pool→
  db_node→/{ns}/mission_request→mission_manager`.
- **mission_manager**: SYSTEM_ACTIONS(전원) + MODE_ACTIONS(모드 중재)만. **goto/Nav2 미구현**.

**갭:** 원격 이동(goto). 전원명령은 이미 web에 존재, RGB-D 뷰·캡처는 범위 외.

## 2. 결정 (확정)

- **범위:** 이동(goto)만 — 침상/home 프리셋 + 미니맵 클릭 + dock-aware. (전원·카메라 제외)
- **pose 출처:** RTDB `targets` 가 단일 출처. **웹이 최종 좌표를 풀어서 전송**(`{x,y,yaw,dock_after?}`),
  로봇은 좌표로 Nav2 이동만(이름 해석 불요). 맵 클릭도 map meta로 픽셀→월드 변환 후 동일 경로.
- **로봇측:** mission_manager 내부 `nav_executor` 모듈(dashboard 로직 이식) + ModeArbiter `goto`(nav) 모드.

## 3. 데이터 계약

`{ns}/mission_pool` 항목(goto):
```json
{"action":"goto",
 "params":{"x":-8.0,"y":-6.0,"yaw":-0.00142,"dock_after":true,"label":"Docking Station"},
 "status":"pending","ts":1733600000000}
```
- `db_node` → `/{ns}/mission_request`: `{id, action:"goto", params:{...}}` (params 통과 — 기존 코드가 이미 전달).
- `mission_manager` → `/{ns}/mission_feedback`: `{id, action:"goto", status:"running|done|failed", detail, ts}`.
- `db_node` → RTDB `{ns}/mission_status` 갱신 + 완료 시 `mission_pool` 항목 제거(기존 동작).

`targets` 시드(RTDB, dashboard `DEFAULT_TARGETS` 실측값):
```json
{"t101_1":{"label":"101호 1번","x":-12.0,"y":-5.0,"yaw":-0.00143},
 "t101_2":{"label":"101호 2번","x":-12.0,"y":-6.0,"yaw":-0.00143},
 "t102":  {"label":"102호 호출","x":-13.0,"y":-8.0,"yaw":-0.00143},
 "pharmacy":{"label":"약품실","x":-9.0,"y":-9.0,"yaw":-0.00143},
 "dock":  {"label":"Docking Station","x":-8.0,"y":-6.0,"yaw":-0.00142,"dock_after":true}}
```

## 4. 컴포넌트 / 파일

### 로봇 (medicart_ws)
- **`mission_manager/nav_executor.py` (신규)** — `NavExecutor`:
  - `ActionClient(NavigateToPose, /{ns}/navigate_to_pose)`, `Dock`, `Undock` 클라이언트 + `/{ns}/dock_status` 구독.
  - `start(params, on_done)`: dock-aware 시퀀스 — docked면 Undock→Nav→(dock_after면 도착 후 Dock).
  - `cancel()`: 활성 nav/dock goal 취소(선점·정지용).
  - `pose_stamped(x,y,yaw)`: **순수함수**(yaw→quaternion, map 프레임 PoseStamped) — 단위테스트 대상.
  - **create3 중복액션 디바운스**: in-flight dock/undock 추적해 재전송 금지(SIGSEGV 방지, [[create3-duplicate-action-segfault]]).
  - Nav2 서버 미연결 시 `failed` 보고(행 금지).
- **`mission_manager/mission_manager_node.py` (수정)** — 라우팅 3-lane:
  ```python
  if action in SYSTEM_ACTIONS:   self._executor.handle(req)
  elif action == "goto":         self._nav.handle(req)          # 신규 레인
  elif action in MODE_ACTIONS:   self._arbiter.apply(...)
  ```
  goto 시작 시 `arbiter.apply("start","goto",params)`(nav 점거), 완료/실패 시 `arbiter.apply("stop","goto")`.
  `_control_tick` 은 기존대로 NAV 활성 시 cmd_vel 미발행(Nav2 소유) — 수정 불필요.
- **`mission_manager/mode_arbiter.py` (소폭)** — `goto` 를 내부 nav 모드로 처리(외부 계약노드 없음 →
  `ModeProxy.set` 발행은 무해, 구독자 없음). 우선순위 `MODE_PRIORITY`에 **`goto`: 7** 추가
  (운영자 명령 — mapping(6) 포함 모든 자율모드 선점, 최상위). registry `{"goto":"nav"}` 병합.
- **`db_bridge/db_node.py` (소폭)** — goto 워치독 타임아웃 연장(`NAV_TIMEOUT=300.0`); `action=="goto"` 시 적용.
  params 전달은 기존 코드(`req['params']=mission.get('params',{})`) 그대로 — 변경 불요.
- **`mission_manager/package.xml` (수정)** — `<depend>nav2_msgs</depend>`, `<depend>irobot_create_msgs</depend>` 추가.

### 웹 (web)
- **`backend/fb_read.py` (수정)** — `MISSION_ACTIONS` 에 `"goto"` 추가. `mission_payload` 가 goto의
  `params`(x,y,yaw 수치, dock_after bool, label str) 검증·통과. `get_targets()`(RTDB `targets` 읽기),
  `seed_targets()`(없으면 위 시드 1회 기록).
- **`backend/app.py` (수정)** — `GET /api/targets`(프리셋 목록). 기존
  `POST /api/robots/<ns>/missions` 가 `body.get("params")` 도 `push_mission` 에 전달하도록 확장.
- **`frontend/lib/api.ts` (수정)** — `pushMission(ns, action, params?, mode?)`, `getTargets()`, `GotoTarget` 타입.
- **`frontend/app/control/page.tsx` (수정)** — "이동" 섹션: 선택 로봇 + `/api/targets` 프리셋 버튼 →
  `dispatch goto {params: target}`(확인창).
- **`frontend/components/MapView.tsx` (수정)** — 로봇 선택 토글 + 캔버스 클릭 → map meta(resolution/origin)로
  픽셀→월드(x,y) 변환 → 확인창 → 선택 로봇에 `goto{x,y,yaw:0,dock_after:false}`. 타깃 마커 클릭 = 해당 프리셋 전송.

### 시드
- RTDB `targets` 1회 시드: `backend` 의 `seed_targets()` 를 기동 시 호출(비어있을 때만) 또는 일회성 스크립트.

## 5. 픽셀↔월드 변환 (맵 클릭)

map yaml `resolution`(m/px), `origin=[ox,oy,_]`, 이미지 높이 `H`(px):
```
world_x = ox + px * resolution
world_y = oy + (H - py) * resolution      # 이미지 y축 반전(좌상단 원점 → map 하단 원점)
```
`MapView` 는 이미 map meta(resolution/origin)와 pose 변환 로직 보유 — 역변환만 추가.

## 6. 에러 처리

- Nav2 액션서버 미연결 → `failed` "Nav2 미연결"(타임아웃, 행 금지).
- `dock_status` 불명(None) → 자동 undock 생략하고 Nav 시도.
- 선점(상위모드/신규 goto) → `NavExecutor.cancel()` 로 현재 goal 취소 후 새 명령.
- 워치독: `db_node` goto 타임아웃 300s 초과 → `failed` 보고 + 다음 order; mission_manager 모드 해제.
- create3 dock/undock 디바운스 — in-flight 시 재전송 금지.

## 7. 테스트

**순수 단위테스트(ROS 무):**
- `mission_payload("goto", params)` — 유효 좌표 통과, 잘못된 params(좌표 누락/비수치) `ValueError`.
- `NavExecutor.pose_stamped(x,y,yaw)` — yaw→quaternion(z,w) 정확성, 프레임 `map`.
- `seed_targets` 페이로드 형태 + 멱등(이미 있으면 미덮어쓰기).
- 픽셀→월드 변환 함수(파이썬 미러 또는 TS) — 알려진 입력/출력.

**통합(로봇 필요 → 사용자 실행, 로봇 구동 직접 금지):**
- control 프리셋 → 침상 이동 / `Docking Station` → dock_after 자동 도킹.
- 맵 클릭 → 해당 좌표 이동.
- goto 중 상위모드/신규 goto 선점 → 기존 nav 취소.
- 선행: `loc`/`nav` 기동(dashboard README 순서) — 명령·순서 별도 제공.

## 8. 영향도

- `db_node` params 전달은 기존 동작 → goto 무변경 통과(타임아웃만 추가).
- `_control_tick` NAV 미발행 분기 기존 유지 → cmd_vel 충돌 없음.
- dashboard 패키지 **무변경**(레퍼런스만). 좌표는 시드로 복제(향후 dashboard와 동기화는 운영 메모).
- 기존 web 전원·모드 명령 경로 무영향(라우팅에 goto 레인만 추가).

## 9. 범위 밖 (후속)
- dashboard ↔ RTDB `targets` 좌표 자동 동기화(현재는 시드 복제).
- 맵 클릭 시 yaw 지정 UI(현재 0 고정).
- RGB-D 뷰·캡처 web 이식.
