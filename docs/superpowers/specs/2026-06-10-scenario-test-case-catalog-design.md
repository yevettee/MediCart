# 시나리오 테스트케이스 카탈로그 — 간호사 투약 · 순회 문진 (풀스택 연결부 검증)

- **작성일**: 2026-06-10 · 대상: MediCart 전체 스택
- **목적**: 두 메인 시나리오(간호사 투약 / 순회 문진)의 워크플로우 전반을 **최소 기능단위**로 쪼개, **모든 연결부(컴포넌트 간 인터페이스)**를 검증하는 자동화 테스트케이스 카탈로그. 총 **98건**.
- **형식**: 자동화 테스트 스펙. 로봇 perception/control/ROS 노드는 mock/시뮬레이션 가정(rclpy/cv/YOLO mock). 실제 로봇 구동이 최종 확인에 필요한 건 `[+manual:runtime]` 태그.
- **범위**: 풀스택 — Perception/Control/ROS(medicart_ws, ocr_ws) + RTDB 버스 + Flask 백엔드 + Next.js 프론트.

## 규약

**케이스 필드**: `ID | 제목 | Layer · Level · Tooling` + `conn`(검증 연결부) · `G/W/T`(Given/When/Then) · `fix`(픽스처/전제) · `note`.

- **Layer**: Perception · Control · Mission · Bridge · OCR · Backend · Frontend · Infra
- **Level**: `unit` · `int`(integration) · `e2e`
- **Tooling**: `pytest` · `pytest(mock)` · `vitest` · `launch_testing`(ros2) · `api+rtdb` · `manual:runtime`
- **ID 체계**: `TC-<X|A|B>-<group>-<nn>`. X=공통, A=간호사 투약(robot6), B=순회 문진(robot3).

**RTDB 스키마 기준**(`{ns}` = robot3|robot6): `amcl_pose{x,y,yaw}`, `odom`, `battery_state{pct,voltage}`, `dock_status{is_docked}`, `imu`, `scan{angle_min,angle_inc,range_max,ranges}`, `robot_mode`, `online`, `stamp`(**밀리초**), `mission_pool/{id}`+`_meta`, `nurse_cart{phase,ocr_done,round_done}`, `patrol{phase,advance,stop}`.

---

## Section X — 공통 / 인프라 (28건)

### X-RTDB — 브릿지·스키마·페이로드 (8)

**TC-X-RTDB-01** | 토픽 노드 → 스냅샷 매핑 | Bridge · unit · pytest
- conn: `fb_read.topics_to_snapshot` (RTDB 노드 → 대시보드 스냅샷 필드)
- G/W/T: amcl_pose/odom/battery_state/dock_status/imu/scan/robot_mode/online/stamp 포함 노드 → `pose/vel/battery/dock/imu/scan/mode/online/stamp` 필드 정확 매핑
- fix: 기존 `test_fb_read.py::test_topics_to_snapshot_maps_topic_keys_to_fields`

**TC-X-RTDB-02** | cmd만 있는 센서노드 → 미존재 취급 | Bridge · unit · pytest
- conn: 스냅샷 존재 판정
- G/W/T: `None`/문자열/`{cmd:...}`(stamp 없음) → `topics_to_snapshot` 반환 `None`

**TC-X-RTDB-03** | stamp는 밀리초로 기록 | Bridge · unit · pytest [+manual:runtime]
- conn: ward_bridge `AmrBridge` → `{ns}/stamp` 기록 단위
- G/W/T: 초 단위 ROS stamp `t` → RTDB `stamp == int(round(t*1000))`. 절대 초 단위로 기록 금지(웹 `Date.now()` ms와 단위 일치 보장)
- note: 단위 불일치 시 웹 LIVE 오판(과거 버그) — 회귀 가드

**TC-X-RTDB-04** | merge_snapshots source 주입·누락 처리 | Bridge · unit · pytest
- conn: 두 로봇 노드 병합 → 대시보드
- G/W/T: raw에 robot3만 → robot3.source="robot3", robot6=None

**TC-X-RTDB-05** | mission_payload 화이트리스트 | Backend · unit · pytest
- conn: 미션 액션 검증 (임의 명령 차단)
- G/W/T: `dock`/`goto`/`nurse_cart_mission`/`patrol_intake_mission` 허용 ; `rm-rf`/`format`/`""` → ValueError

**TC-X-RTDB-06** | goto 좌표 필수·수치 검증 | Backend · unit · pytest
- conn: goto 미션 좌표 sanitize
- G/W/T: `{x,y}` 수치 → 통과(dock_after/label 보존) ; y 누락 또는 비수치 → ValueError

**TC-X-RTDB-07** | mission_pool 초기화(web-restart) | Backend · int · api+rtdb
- conn: `clear_missions(ns)` for ROBOT_NAMESPACES — 백엔드 기동 시 전 로봇 mission_pool 비움
- G/W/T: robot3·robot6 mission_pool에 더미 미션 주입 → 백엔드 `__main__` 초기화 → 두 pool 비워짐(`_meta` 제외)

**TC-X-RTDB-08** | valid_robot_ns / _req_ns 라우팅 | Backend · unit · pytest
- conn: 요청 ns → 검증 → PRIMARY 폴백
- G/W/T: `robot3`/`robot6` 통과 ; `amr2`/`../x` → False → `_req_ns`가 PRIMARY_NS로 폴백 (GET=query, POST=body)

### X-RBAC — 권한·메뉴·라우트 (7)

**TC-X-RBAC-01** | roleAtLeast 등급 비교 | Frontend · unit · vitest
- conn: `auth.roleAtLeast` (patient<staff<admin)
- G/W/T: (staff,"staff")=true, (patient,"staff")=false, (admin,"patient")=true

**TC-X-RBAC-02** | 홈 라우트 staff부터 접근 | Frontend · unit · vitest
- conn: `requiredRoleForRoute("/")` + middleware 가드
- G/W/T: `requiredRoleForRoute("/")=="staff"`, `roleAtLeast("staff", need)`=true ; `/console`="admin", staff 차단
- fix: 기존 `auth.test.ts`

**TC-X-RBAC-03** | 의료진 사이드바 메뉴 노출 | Frontend · unit · vitest
- conn: role → `NAV_ROLES` → `visibleNav`
- G/W/T: staff → 홈·환자정보·문진표·처치실 노출, /console·/control·/map·/debug 미노출 ; admin → 전부 ; patient → 문진표만(또는 PatientPanel)

**TC-X-RBAC-04** | 토큰 → 역할 매핑 | Frontend · unit · vitest
- conn: `roleForToken(token, staffTok, adminTok)`
- G/W/T: adminTok→admin, staffTok→staff, 미일치/undefined→patient

**TC-X-RBAC-05** | 백엔드 경로별 최소 등급 | Backend · unit · pytest
- conn: `auth.required_role_for_path` (프론트 표와 일치)
- G/W/T: `/api/display/current`=open ; `/api/intake*`=patient ; `/api/patients*`,`/api/ocr*`=staff ; 그 외=admin

**TC-X-RBAC-06** | 토큰 상수시간 비교 | Backend · unit · pytest
- conn: `auth` 자격 비교 (`hmac.compare_digest`)
- G/W/T: 잘못된 토큰 → 401, 비교는 상수시간(타이밍 누설 방지) — 구현이 `compare_digest` 사용함을 단언

**TC-X-RBAC-07** | 미들웨어 미인가 → 랜딩 리다이렉트 | Frontend · int · vitest
- conn: `middleware` (token→role→requiredRoleForRoute→redirect landingFor)
- G/W/T: staff가 `/console` 요청 → `landingFor("staff")=/patients`로 redirect ; 인가 통과 시 next()

### X-TELE — 텔레메트리·온라인·맵 (9)

**TC-X-TELE-01** | snapAgeMs 단위·가드 | Frontend · unit · vitest
- conn: `telemetry.snapAgeMs` (stamp ms → 나이 ms)
- G/W/T: undefined/0/음수/NaN→Infinity ; 최근 stamp→소량 양수 ; 미래 stamp→0 클램프
- fix: 기존 `telemetry.test.ts`

**TC-X-TELE-02** | isLive 임계 | Frontend · unit · vitest
- conn: `telemetry.isLive(stamp,thresholdMs)`
- G/W/T: 3s 기본 임계 ; 5s 인자 적용 ; undefined→false

**TC-X-TELE-03** | robotHome 도킹 pose 도출 | Frontend · unit · vitest
- conn: `telemetry.robotHome(snap)`
- G/W/T: 도킹+pose→pose ; 미도킹→null ; pose없음→null ; null→null

**TC-X-TELE-04** | 콘솔 경과/LIVE 표시 | Frontend · unit · vitest
- conn: AmrPanel `ageMs=snapAgeMs(stamp)`, `online=isLive(stamp)`
- G/W/T: 최근 stamp→LIVE+경과 수백 ms ; 5s 전 stamp→STALE+경과>=3000 warn

**TC-X-TELE-05** | 홈 online 카운트 단위 | Frontend · unit · vitest
- conn: page.tsx `vals.filter(isLive(stamp,5000))`
- G/W/T: robot3 최근·robot6 2h 전 → online=1/2 (ms 혼용 버그 부재)

**TC-X-TELE-06** | world→pixel 좌표 변환(mapMeta) | Frontend · unit · vitest
- conn: MapView 변환 `((wx-ox)/res, H-(wy-oy)/res)`
- G/W/T: origin[-5.59,-4.58], res 0.05, 이미지 H → 알려진 월드점이 기대 픽셀로

**TC-X-TELE-07** | targets 오버레이 렌더(dock 제외) | Frontend · int · vitest(canvas mock)
- conn: MapView `getTargets` → 마커, key=="dock" 스킵
- G/W/T: targets={t101_1,t102_1,pharmacy,dock} → 침상·약품실 마커 그려지고 dock 키는 스킵

**TC-X-TELE-08** | 로봇별 홈 마커 래치 | Frontend · unit · vitest
- conn: MapView `homesRef` 래치 (도킹 시 갱신, 떠나도 유지)
- G/W/T: robot3 도킹 pose 수신→homesRef[robot3] 저장 ; 이후 미도킹 스냅 → 마커 좌표 유지(사라지지 않음)

**TC-X-TELE-09** | /api/map 메타 = ninety 맵 | Backend · int · api
- conn: `/api/map` resolution·origin (로봇 맵과 동일해야 정렬)
- G/W/T: 응답 `available=true, resolution=0.05, origin≈[-5.59,-4.58,0]` ; `/api/map.png` 200 image
- note: 배포 env MAP_YAML/MAP_PNG가 ninety 가리키는지 회귀 가드

### X-SSE — 스트림 (4)

**TC-X-SSE-01** | /api/stream 텔레메트리 흐름 | Backend · int · api+rtdb
- conn: `/api/stream` SSE → 병합 스냅샷(source 주입)
- G/W/T: RTDB 갱신 → SSE 이벤트로 `{source:"robot6",pose,...}` 수신

**TC-X-SSE-02** | SSE 재연결 시 상태 미손실 | Frontend · int · vitest
- conn: MapView/console EventSource onmessage merge
- G/W/T: 연결 끊김→재연결 후에도 누적 amrs 유지(늦은 디코드 가드)

**TC-X-SSE-03** | /api/alerts 경보 스트림 | Backend · int · api+rtdb
- conn: `/api/alerts` SSE
- G/W/T: 경보 이벤트 발행 → 클라이언트 수신, 최근 50건 유지

**TC-X-SSE-04** | online 판정 = stamp 신선도 | Frontend · unit · vitest
- conn: SSE 수신 스냅 online 배지
- G/W/T: 수신 stamp 신선→LIVE, 정지(>임계)→STALE 전이

---

## Section A — 간호사 투약 (robot6, nurse_cart_mission) (36건)

### A-TRIG — 트리거·발행 (5)

**TC-A-TRIG-01** | 홈 '간호사 투약' staff+ 노출 | Frontend · unit · vitest
- conn: page.tsx 버튼 게이트 `roleAtLeast(role,"staff")`
- G/W/T: patient→PatientPanel(버튼 없음) ; staff/admin→'간호사 투약' 버튼 노출

**TC-A-TRIG-02** | startRound → robot6 고정 | Frontend · unit · vitest
- conn: `startRound(NURSE_CART_NS)`, `NURSE_CART_NS=="robot6"`
- G/W/T: 버튼 확인 클릭 → `startRound("robot6")` 호출 (robot3로 가지 않음)

**TC-A-TRIG-03** | nurse_cart_start 라우트 ns | Backend · int · api+rtdb
- conn: `/api/.../nurse_cart_start` → `push_mission(_req_ns,"nurse_cart_mission")`
- G/W/T: body{ns:"robot6"} → robot6/mission_pool에 `nurse_cart_mission` pending 1건

**TC-A-TRIG-04** | nurse_cart_mission 페이로드 | Backend · unit · pytest
- conn: `mission_payload("nurse_cart_mission",None,ts)`
- G/W/T: action="nurse_cart_mission", status="pending", ts 포함

**TC-A-TRIG-05** | 권한 없는 트리거 차단 | Backend · int · api
- conn: nurse_cart_start RBAC
- G/W/T: 무토큰/patient → 401/403, mission_pool 변화 없음

### A-SEQ — 시퀀서·undock·도킹 (6)

**TC-A-SEQ-01** | 시퀀서 mission_pool 폴링 | Mission · unit · pytest(mock)
- conn: `nurse_cart_sequencer` ← `mission_pool` ordered pending
- G/W/T: pending nurse_cart_mission 1건 → FSM idle→active 전이, 미션 status pending→running

**TC-A-SEQ-02** | undock 단일 발행(중복 디바운스) | Mission · unit · pytest
- conn: nav_executor undock → create3 (중복 액션 SIGSEGV 방지)
- G/W/T: 동일 undock 2회 요청 → 1회만 액션 전송(디바운스), 진행 중 재요청 무시
- note: create3_republisher 중복 undock segfault 회귀 가드

**TC-A-SEQ-03** | undock→nav→dock 체인 순서 | Mission · int · launch_testing(sim)
- conn: `NavExecutor` 액션 체인
- G/W/T: 시작 시 미도킹이면 undock 선행 → goto → 종료 시 dock_after면 dock. 순서 역전 없음

**TC-A-SEQ-04** | pose_stamped_fields 변환 | Mission · unit · pytest
- conn: `nav_executor.pose_stamped_fields(x,y,yaw)`
- G/W/T: (x,y,yaw)→PoseStamped frame_id="map", orientation=yaw→quaternion 일치

**TC-A-SEQ-05** | cmd_vel 단독 소유(mode_manager) | Control · int · launch_testing(sim)
- conn: ModeArbiter — cmd_vel/Nav2 단일 소유, 우선순위 선점
- G/W/T: 두 모드 동시 cmd_vel → 우선순위 높은 모드만 퍼블리시, 낮은 모드 차단

**TC-A-SEQ-06** | 복귀 홈 = robot6 도킹 pose | Mission · int · api+rtdb
- conn: nurse_cart 복귀(로봇 자체 처리) / 시퀀서 _DEFAULT_HOME or RTDB pose
- G/W/T: round_done 후 robot6가 자기 도크 좌표로 복귀(robot3 도크로 가지 않음)

### A-OCR — 약품실·OCR·핸드셰이크 (8)

**TC-A-OCR-01** | 약품실 goto 좌표 | Mission · unit · pytest
- conn: targets `pharmacy` → goto
- G/W/T: targets_seed.pharmacy(x,y,yaw) → goto 미션 좌표 일치

**TC-A-OCR-02** | OCR 엔진 인터페이스 | OCR · unit · pytest
- conn: `BaseOcrEngine` ← EasyOcrEngine/GcpEngine (inherits)
- G/W/T: 두 엔진 모두 `recognize(image)` 시그니처 구현, 추상 base 직접 인스턴스화 불가

**TC-A-OCR-03** | 약품명 별칭 매칭 | OCR · unit · pytest
- conn: `medicine_checker.check_medicine` (alias)
- G/W/T: "타이레놀"≈"아세트아미노펜" 별칭 → 일치 ; 무관한 텍스트 → 불일치

**TC-A-OCR-04** | OCR 텍스트 정규화 | OCR · unit · pytest
- conn: `text_cleaner` 공백/노이즈 정규화
- G/W/T: " 타이레놀\n 500mg " → "타이레놀 500mg"

**TC-A-OCR-05** | ocr_payload 구조 | OCR/Bridge · unit · pytest
- conn: `fb_read.ocr_payload(text,conf,ts)`
- G/W/T: ("타이레놀",0.9,ts)→{text,conf,ts} ; conf None 허용

**TC-A-OCR-06** | ocr_done 핸드셰이크(set) | Backend · int · api+rtdb
- conn: `/api/.../nurse_cart_ocr_done` → `set_ocr_done(ns,True)`
- G/W/T: POST{ns:robot6} → robot6/nurse_cart/ocr_done=true

**TC-A-OCR-07** | 처치실 페이지 OCR 흐름 결선 | Frontend · int · vitest
- conn: ocr/page.tsx → getNurseCartPhase/nurseCartOcrDone/nurseCartRoundDone(NURSE_CART_NS)
- G/W/T: OCR 완료 버튼 → `nurseCartOcrDone("robot6")` 호출 ; phase 폴링으로 다음 단계 표시

**TC-A-OCR-08** | OCR 결과 RTDB 기록(injection) | OCR/Bridge · int · api+rtdb
- conn: ocr_ws `db_bridge` → injection/OCR 결과 영속
- G/W/T: 인식 결과 → 환자 injection 레코드에 기록(text/conf/ts)

### A-PERC — 인지(RGB/Depth/YOLO/Tracker) (8)

**TC-A-PERC-01** | compressed RGB 10fps 수신·디코딩 | Perception · int · pytest(mock) [+manual:runtime]
- conn: OAK-D `…/rgb/…/compressed` 구독 → cv 디코딩
- G/W/T: 10Hz mock 퍼블리셔 2s → ≥18프레임 디코딩(손실 허용), BGR ndarray (H,W,3)

**TC-A-PERC-02** | compressedDepth 디코딩(raw 미사용) | Perception · int · pytest(mock) [+manual:runtime]
- conn: depth는 `compressedDepth` 구독+디코딩 (raw 금지)
- G/W/T: compressedDepth 메시지 → 16UC1/float depth 맵 디코딩 ; raw depth 토픽 미구독

**TC-A-PERC-03** | RGB-Depth 동기화(message_filters) | Perception · unit · pytest
- conn: `perception` 수신측 ApproximateTimeSynchronizer
- G/W/T: stamp 근접 RGB/Depth 쌍 → 동기 콜백 1회 ; stamp 차 큰 쌍 → 콜백 없음

**TC-A-PERC-04** | YOLO 사람 검출 래퍼 | Perception · unit · pytest(mock)
- conn: `yolo_helper.YoloHelper` (Ultralytics)
- G/W/T: 사람 포함 프레임(mock 결과) → person bbox 리스트 ; 빈 프레임 → []

**TC-A-PERC-05** | ByteTrack 추적 의존성(lap) | Perception · unit · pytest
- conn: `model.track` ByteTrack → `lap` 패키지 필요
- G/W/T: tracker 사용 경로가 lap import 가능 전제 ; 미설치 시 명확한 에러(무음 실패 금지)
- note: bytetrack-needs-lap 회귀 가드

**TC-A-PERC-06** | 추적 ID 유지/재획득 | Perception · unit · pytest(mock)
- conn: `PersonTracker` 타깃 id 유지
- G/W/T: 연속 프레임 동일 인물 → 동일 track id ; 사라졌다 재출현 → 재획득 분기

**TC-A-PERC-07** | depth→타깃 거리 추정 + tf2 | Perception · unit · pytest(mock)
- conn: bbox 중심 depth → base_link 거리 (tf2 변환)
- G/W/T: bbox+depth맵 → 타깃 거리(m) 산출, tf 프레임 변환 적용

**TC-A-PERC-08** | OAK-D 파워세이버/lazy 토픽 | Perception · int · pytest(mock) [+manual:runtime]
- conn: 유휴 시 카메라 자동정지 + lazy 토픽 (구독자 생기면 재개)
- G/W/T: 구독 없음→토픽 비활성(fps 0) ; 구독 시작→스트림 재개
- note: turtlebot4-oakd-powersaver — fps 측정이 비는 이유 회귀 가드

### A-FOLLOW — 추종 제어 (5)

**TC-A-FOLLOW-01** | 85cm 거리유지 제어법칙 | Control · unit · pytest
- conn: `follow_control` 거리→cmd_vel (의존성 없는 순수 로직)
- G/W/T: d=1.2m→linear.x>0 ; d≈0.85m→~0 ; d=0.5m→linear.x<0

**TC-A-FOLLOW-02** | 정면 근접 장애물 회피 | Control · unit · pytest
- conn: 정면 depth<200mm → 정지/회피
- G/W/T: 정면 최소거리<0.2m → linear.x<=0(전진 금지) 안전 게이트 발동

**TC-A-FOLLOW-03** | 타깃 각도 → 각속도 | Control · unit · pytest
- conn: 타깃 방위각 → angular.z
- G/W/T: 타깃 좌측→angular.z>0, 우측→<0, 정면→~0

**TC-A-FOLLOW-04** | 타깃 소실 시 정지/탐색 | Control · unit · pytest
- conn: FollowFSM 소실 분기
- G/W/T: N프레임 연속 미검출 → cmd_vel 0(정지) + 탐색 상태 전이(폭주 금지)

**TC-A-FOLLOW-05** | 추종 중 ModeArbiter 안전 게이트 | Control · unit · pytest
- conn: `ModeArbiter.safety_gate`
- G/W/T: 위험 입력(장애물/모드충돌) → cmd_vel 0으로 게이팅

### A-PHASE — 단계 인식·완료 (4)

**TC-A-PHASE-01** | phase 폴링(idle\|arrived\|tracking\|done) | Frontend · int · vitest
- conn: RoundOverlay `getNurseCartPhase(NURSE_CART_NS)`
- G/W/T: RTDB nurse_cart.phase 변화 → 오버레이 단계 텍스트 갱신

**TC-A-PHASE-02** | _phase_or_idle 정규화 | Backend · unit · pytest
- conn: `fb_read._phase_or_idle`
- G/W/T: None/""/숫자→"idle" ; "tracking"→"tracking"

**TC-A-PHASE-03** | get_nurse_cart_phase 라우트 | Backend · int · api+rtdb
- conn: `/api/.../nurse_cart_phase?ns=robot6` → get_nurse_cart_phase
- G/W/T: RTDB phase="tracking" → 응답 {phase:"tracking"}

**TC-A-PHASE-04** | round_done 핸드셰이크 → 복귀 트리거 | Backend · int · api+rtdb
- conn: `/api/.../nurse_cart_round_done` → `set_round_done(ns,True)`
- G/W/T: POST{ns:robot6} → robot6/nurse_cart/round_done=true → 로봇 복귀·도킹 단계 진입

---

## Section B — 순회 문진 (robot3, patrol_intake_mission) (34건)

### B-TRIG — 트리거·발행 (5)

**TC-B-TRIG-01** | 홈 '순회 문진' staff+ 노출 | Frontend · unit · vitest
- conn: page.tsx 버튼 게이트 `roleAtLeast(role,"staff")`
- G/W/T: patient→없음 ; staff/admin→'순회 문진 시작' 노출

**TC-B-TRIG-02** | RoundsIntakeOverlay → robot3 고정 | Frontend · unit · vitest
- conn: `<RoundsIntakeOverlay ns={PATROL_NS}>`, `PATROL_NS=="robot3"`
- G/W/T: 시작 → ns="robot3"으로 동작(robot6로 가지 않음)

**TC-B-TRIG-03** | pushMission patrol_intake_mission{stops,home} | Frontend · int · vitest+api
- conn: 시작 시 `pushMission("robot3","patrol_intake_mission",{stops,home})`
- G/W/T: 시작 → robot3/mission_pool에 patrol_intake_mission, params.stops=정차리스트, params.home=robot3 도킹 pose

**TC-B-TRIG-04** | home = robot3 도킹 pose(RTDB) | Frontend · unit · vitest
- conn: page.tsx `dock=robotHome(amrs[PATROL_NS]) ?? targets.dock ?? 기본`
- G/W/T: robot3 도킹 pose 존재 → home=그 pose(≈-7.4,-3.1) ; 미도킹 → targets.dock 폴백

**TC-B-TRIG-05** | patrol_intake_mission 페이로드 | Backend · unit · pytest
- conn: `mission_payload("patrol_intake_mission",params,ts)`
- G/W/T: action 허용, stops/home params 보존, status="pending"

### B-SEQ — 시퀀서·순회·Nav2 (8)

**TC-B-SEQ-01** | 시퀀서 자율 순회 수행 | Mission · unit · pytest(mock)
- conn: `patrol_intake_sequencer` ← mission_pool
- G/W/T: pending patrol_intake_mission → undock→stops 순차 goto FSM 전개

**TC-B-SEQ-02** | 정차 순서 101-1→101-2→102-1→복귀 | Mission · unit · pytest
- conn: ROUND_MAP/stops 순서 (102호 t102_1 포함)
- G/W/T: stops=[t101_1,t101_2,t102_1] → 그 순서로 도착 이벤트, 마지막 후 home 복귀

**TC-B-SEQ-03** | t102_1 타겟 좌표 | Backend · unit · pytest
- conn: `targets_seed` t102_1
- G/W/T: seed.t102_1.x==-4.3, y==-3.39 ; targets 총 개수·필수키(label/x/y/yaw)
- fix: 기존 `test_targets_seed_shape`

**TC-B-SEQ-04** | Nav2 BasicNavigator executor 격리 | Mission · unit · pytest(mock)
- conn: 워커 스레드 사용 시 main은 전용 executor (generator 충돌 방지)
- G/W/T: BasicNavigator 사용 노드가 별도 executor로 spin, 메인 콜백과 충돌 없음
- note: nav2-basicnavigator-executor 회귀 가드

**TC-B-SEQ-05** | 정차 도착 판정 → arrived | Mission · int · launch_testing(sim)
- conn: Nav2 goal 도달 → patrol.phase="arrived"
- G/W/T: goto 성공 콜백 → RTDB patrol/phase="arrived", stop.idx/room 기록

**TC-B-SEQ-06** | undock 단일 발행(중복 디바운스) | Mission · unit · pytest
- conn: 동일 — create3 중복 액션 segfault 방지
- G/W/T: 중복 undock → 1회만 전송

**TC-B-SEQ-07** | 순회 종료 복귀·도킹(robot3 home) | Mission · int · api+rtdb
- conn: 마지막 stop 후 home 복귀 + dock
- G/W/T: returning 단계 → robot3 home 좌표 goto + dock_after dock

**TC-B-SEQ-08** | 순회 중 LiDAR 지역 장애물 회피 | Control · int · launch_testing(sim) [+manual:runtime]
- conn: Nav2 local costmap / obstacle_detector ← scan
- G/W/T: 경로 상 장애물 → 우회 재계획 또는 정지 후 재개, 충돌 없음 ; cmd_vel은 여전히 단일 소유(ModeArbiter)

### B-QR — QR·배정환자 검증 (7)

**TC-B-QR-01** | QR 스캐너 디코딩 | Frontend · unit · vitest
- conn: `useQrScanner`/`ocrQr` QR 텍스트 파싱
- G/W/T: 유효 QR 페이로드 → pid 추출 ; 잡음 → null

**TC-B-QR-02** | valid_pid 형식 검증 | Backend · unit · pytest
- conn: `fb_read.valid_pid`
- G/W/T: "P-2026-0001"→true ; "../x"→false

**TC-B-QR-03** | 배정환자 일치 검증 | Frontend+Backend · int · vitest+api
- conn: stop.room 배정환자 ↔ 스캔 pid (`getRooms`/`getPatient`/verifyIdentify)
- G/W/T: 배정 P-0001, 스캔 P-0001→pass→문진 진입 ; P-0002→불일치 경고, 진행 차단

**TC-B-QR-04** | 미등록 환자 알림 | Frontend · int · vitest
- conn: 스캔 pid가 환자DB 미존재
- G/W/T: getPatient 404 → "미등록" 인라인 알림, 문진 미진입

**TC-B-QR-05** | room→배정환자 조회(RoomsServer) | Bridge · unit · pytest
- conn: db_bridge `RoomsServer.list_rooms` / `lookup_room`
- G/W/T: room "101-1" → 배정 환자 pid 반환 ; 미배정 → 빈값

**TC-B-QR-06** | QR→문진표 자동 이동 | Frontend · int · vitest
- conn: qr/page.tsx 등록환자면 같은 화면 문진표 전환
- G/W/T: 등록 환자 스캔 → 문진 폼으로 라우팅(해당 pid 프리필)

**TC-B-QR-07** | 동일 QR 연속 스캔 디바운스 | Frontend · unit · vitest
- conn: `useQrScanner` 중복 디코드 가드
- G/W/T: 같은 pid 1s 내 재스캔 → 1회만 처리(중복 검증/이중 진입 방지) ; 다른 pid → 즉시 처리

### B-INTAKE — 문진·부재중 (7)

**TC-B-INTAKE-01** | intake_pending_payload 구조 | Backend · unit · pytest
- conn: `fb_read.intake_pending_payload`
- G/W/T: {name(trim),room,sections} → {name,room,sections,status:"pending",ts} ; 빈 입력 기본값
- fix: 기존 test_intake_pending_payload

**TC-B-INTAKE-02** | sanitize_fields 키·숫자 변환 | Backend · unit · pytest
- conn: `fb_read.sanitize_fields`
- G/W/T: 제어키 제외, "/"→"_", 숫자키→int/float, 빈 숫자→원본
- fix: 기존 test_sanitize_fields

**TC-B-INTAKE-03** | visit_payload pid 주입 | Backend · unit · pytest
- conn: `fb_read.visit_payload`
- G/W/T: pid+섹션 → 등록번호 주입, 맥박 등 숫자 변환

**TC-B-INTAKE-04** | 문진 제출 → RTDB pending | Backend · int · api+rtdb
- conn: `/api/intake` submit → `add_intake_pending`
- G/W/T: 제출 → 환자 intake pending 기록, status="pending"

**TC-B-INTAKE-05** | 문진 완료 표시 | Backend · unit · pytest
- conn: `mark_intake_done` / `_intake_reset_updates`
- G/W/T: 잘못된 pid→false ; reset → 전 환자 intake_done=false 맵

**TC-B-INTAKE-06** | 부재중 처리 분기 | Frontend · unit · vitest
- conn: RoundsIntakeOverlay absent 단계 (ABSENT_SECONDS)
- G/W/T: 스캔 시간 초과 → absent 결과 기록, 다음 stop으로 진행

**TC-B-INTAKE-07** | 문진 폼 필수/형식 검증 | Frontend · unit · vitest
- conn: `IntakeForm` SECTIONS 입력 검증 (드롭다운/수치 필드)
- G/W/T: 필수 항목 미입력 → 저장 차단·인라인 경고 ; 숫자 필드(혈압/맥박/체온) 비수치 → 경고, 유효 입력만 sanitize되어 제출

### B-PHASE — 핸드셰이크·결과 (7)

**TC-B-PHASE-01** | patrol phase 폴링 | Frontend · int · vitest
- conn: RoundsIntakeOverlay `getPatrolPhase(PATROL_NS)`
- G/W/T: RTDB patrol.phase 변화 → starting/moving/scanning/intake/absent/returning/summary 전이

**TC-B-PHASE-02** | get_patrol_phase 라우트 | Backend · int · api+rtdb
- conn: `/api/.../patrol_phase?ns=robot3`
- G/W/T: RTDB phase="arrived" → 응답 {phase:"arrived",stop:{...}}

**TC-B-PHASE-03** | sendPatrolAdvance → 다음 정차 | Frontend+Backend · int · vitest+api
- conn: `sendPatrolAdvance(PATROL_NS)` → `set_patrol_advance(ns)`
- G/W/T: 문진/부재중 완료 → advance 신호 → 시퀀서 다음 stop 진행

**TC-B-PHASE-04** | advance 디바운스(중복 방지) | Backend · int · api+rtdb
- conn: set_patrol_advance 중복 호출
- G/W/T: 동일 stop에서 advance 2회 → 1회만 다음 진행(이중 스킵 방지)

**TC-B-PHASE-05** | 요약 단계 결과 집계 | Frontend · unit · vitest
- conn: RoundsIntakeOverlay summary (Outcome 리스트)
- G/W/T: 각 stop 결과(문진/부재중/불일치) → summary에 정확 집계

**TC-B-PHASE-06** | 순회 완료 후 mission status done | Mission/Bridge · int · api+rtdb
- conn: 시퀀서 종료 → mission_pool status
- G/W/T: 복귀·도킹 완료 → 해당 mission status "done", phase "summary/idle"

**TC-B-PHASE-07** | 순회 실패/중단 복구 | Mission · int · launch_testing(sim)
- conn: 시퀀서 에러 경로 (goto 실패/타임아웃)
- G/W/T: stop goto 실패 또는 타임아웃 → 안전 정지 + home 복귀 시도, mission status "error" 기록(무음 실패 금지), patrol.phase 오류 노출

---

## 커버리지 매트릭스 (연결부 → 케이스)

| 연결부 | 케이스 |
|---|---|
| RTDB 스키마/단위(stamp ms) | X-RTDB-01,03 · X-TELE-01,05 |
| 미션 페이로드 화이트리스트 | X-RTDB-05,06 · A-TRIG-04 · B-TRIG-05 |
| ns 라우팅/검증 | X-RTDB-08 · A-TRIG-03 · B-TRIG-03 |
| mission_pool 수명주기 | X-RTDB-07 · B-PHASE-06 |
| RBAC(메뉴/라우트/토큰) | X-RBAC-01..07 · A-TRIG-01,05 · B-TRIG-01 |
| 텔레메트리/online/맵 | X-TELE-01..09 · X-SSE-04 |
| SSE 스트림 | X-SSE-01..04 |
| compressed RGB/Depth/sync | A-PERC-01,02,03,08 |
| YOLO/추적 | A-PERC-04,05,06 |
| 거리유지/회피 제어 | A-FOLLOW-01..05 |
| OCR/약품검증/ocr_done | A-OCR-01..08 |
| nurse_cart phase/round_done | A-PHASE-01..04 |
| undock/dock/create3 디바운스 | A-SEQ-02 · B-SEQ-06 |
| Nav2/executor/cmd_vel 소유·회피 | A-SEQ-03,05 · B-SEQ-04,05,08 |
| per-robot home 복귀 | A-SEQ-06 · B-TRIG-04 · B-SEQ-07 |
| QR/배정환자 검증 | B-QR-01..07 |
| 문진/부재중 | B-INTAKE-01..07 |
| patrol phase/advance/복구 | B-PHASE-01..07 |

## 집계

- **총 98건**. Section X 28 · A 36 · B 34 (B: TRIG 5 · SEQ 8 · QR 7 · INTAKE 7 · PHASE 7).
- **Level**: unit ~50 · int ~40 · e2e/launch_testing(sim) ~8.
- **Tooling**: vitest ~27 · pytest/pytest(mock) ~40 · api+rtdb ~20 · launch_testing(sim) ~7 · `[+manual:runtime]` 태그 5(A-PERC-01,02,08 · X-RTDB-03 · B-SEQ-08).
- **기존 테스트로 일부 충족**: telemetry.test, auth.test, test_fb_read(targets_seed/payloads/sanitize/intake) — 확장 대상으로 표기.

## 비범위 / 후속

- 실제 로봇 구동 검증(`manual:runtime` 태그)은 사용자 직접 실행.
- 본 문서는 **카탈로그(스펙)**. 자동화 코드 구현은 별도 plan(writing-plans)에서 레이어별 테스트 하니스(pytest fixtures, vitest setup, ros2 launch_testing, RTDB 에뮬/mock)와 함께 단계화.
