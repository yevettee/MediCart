# nurse_tracker (round 모드) 설계 — REACTIVE 추종

**날짜:** 2026-06-07
**대상:** `medicart_ws/src/nurse_tracker` 를 `round`(회진/추종) 모드 노드로 구현. mission_manager 허브에 REACTIVE 모드로 꽂혀 간호사를 0.8m로 추종. intel1 `ward_robot`의 검증된 perception/follow 코드를 **포팅**(재발명 아님).

## 결정 요약 (brainstorming)

- **actuation = REACTIVE 단독**(Twist). Nav2 미사용. 벽/장애물 정면 정지는 **허브 safety_gate**(LiDAR)가 담당.
- **추적 = ByteTrack 단독**(ultralytics model.track persist). OSNet ReID 는 미구현(perception에 훅 주석만 — 후속).
- **포팅 기반**: intel1 `perception.py`(PersonTracker)·`yolo_helper.py`·`control.follow_cmd` 를 nurse_tracker 로 복사·적응(standalone — intel1 import 아님). intel1의 in-process ModeContext 대신 모드 계약(set/cmd_vel/status) I/O.
- **손실 동작**: 사용자 사양 — 정지 후 대기 → 5s 초과 시 `lost` 보고(모드는 유지=HOLD, 하트비트 계속). 재등장 시 FOLLOW 복귀. (intel1의 SEARCH 회전은 미채택.)

## 허브 계약 (round 모드)

- 구독 `/{ns}/mode/round/set`(String JSON {active,params}) — active=true → 추종 시작(ACQUIRE).
- 발행 `/{ns}/mode/round/cmd_vel`(geometry_msgs/Twist) — 허브가 safety_gate 거쳐 `/{ns}/cmd_vel` 중계.
- 발행 `/{ns}/mode/round/status`(String JSON {state:"running", detail:"FOLLOW|LOST_WAIT|lost", ts}) — active 동안 매 틱 하트비트(허브 워치독 충족). 실패로 모드를 내리지 않음(HOLD 유지).
- 발행 `/nurse_tracker/target`(medi_interfaces/TargetBBox) — 시각화/웹.
- 서비스 `StartTracking`(`/{ns}/start_tracking`) — 강제 재-lock(테스트·수동 재포착, 선택).

## 입력 (OAK-D, 로봇→host 스트림)

- `/{ns}/oakd/rgb/image_raw/compressed` (CompressedImage)
- `/{ns}/oakd/stereo/image_raw/compressedDepth` (CompressedImage, 12B 헤더 후 16UC1 mm)
- `message_filters` ApproximateTimeSynchronizer(slop≈0.05) 동기화. (메모리: OAK-D 수신측 동기화·compressedDepth 디코딩 원칙.)

## 모듈 (포팅 기반, 평탄)

| 파일 | 내용 |
|---|---|
| `nurse_tracker/yolo_helper.py` | intel1 그대로 복사 — ByteTrack 래퍼(model.track persist, 모델 없으면 graceful 빈리스트). |
| `nurse_tracker/perception.py` | intel1 PersonTracker 복사·적응 — RGB-D 동기화·디코딩·YOLO+ByteTrack·락온·depth중앙값→distance·bearing·front_depth. **적응 2가지**: (1) OAK-D 토픽 파라미터화, (2) 초기 lock 선택을 **정면최근접 점수**(|cx−W/2| 최소 × depth 최소)로(intel1 max-area 대신, 사용자 사양). conf 기본 0.5. |
| `nurse_tracker/follow_control.py` (순수) | intel1 `follow_cmd`+`FollowParams` 복사(desired_distance=0.8, allow_reverse=True) + **LossFSM**(FOLLOW/LOST_WAIT, lost_timeout=5.0). 단위테스트. |
| `nurse_tracker/tracker_node.py` | 오케스트레이션: PersonTracker 보유, 모드 계약(set/cmd_vel/status), control_hz(10) 타이머 → follow_control step → cmd_vel/status/TargetBBox 발행, StartTracking 서비스. |

**삭제(기존 stub)**: `yolo_detector`(→yolo_helper), `host_tracker`(→model.track 흡수), `spatial_estimator`(→perception 흡수), `spatial_transform`(→Nav2 없어 불요).

## follow_control (순수 로직)

- `follow_cmd(distance, bearing, p)` → (lin, ang): 0.8m 유지(±deadband 정지), 멀면 전진(max_lin 상한), 가까우면 후진(allow_reverse·max_reverse), bearing→각속도. (intel1 control.follow_cmd 규약 그대로.)
- `class FollowFSM`: `step(target, now) -> (lin, ang, detail)`.
  - target fresh(detected·distance>0·age≤follow_timeout) → FOLLOW: follow_cmd.
  - 아니면 LOST_WAIT: (0,0). now−lost_since > lost_timeout(5s) → detail="lost"(유지), 그 전엔 detail="LOST_WAIT".
  - 재-fresh → FOLLOW 복귀.
- 전부 ROS 무관(스텁 target으로 단위테스트).

## tracker_node 동작

- `set(active=false)` 기본 IDLE — cmd_vel/TargetBBox 미발행, FSM reset.
- `set(active=true)` → active. 타이머(10Hz):
  1. perception.target 폴링 → `FollowFSM.step` → (lin,ang,detail).
  2. `/mode/round/cmd_vel` 발행(lin,ang). (허브가 safety_gate.)
  3. `/mode/round/status` 발행 {state:"running", detail, ts}.
  4. target 있으면 `/nurse_tracker/target`(TargetBBox: bbox·conf·id·depth·spatial) 발행.
- `StartTracking` 호출 → perception 락 해제(다음 프레임 재-lock).

## 파라미터

namespace, model_path(기본 ward_model.pt; 없으면 미탐지 graceful), conf=0.5, hfov_deg=69, sync_slop=0.05, desired_distance=0.8, deadband=0.1, allow_reverse=True, max_reverse=0.06, max_lin=0.12, max_ang=0.6, follow_timeout=1.0, lost_timeout=5.0, control_hz=10, oakd rgb/depth 토픽.

## 의존

ultralytics(YOLO11n), lap(ByteTrack), opencv-python, numpy, message_filters, cv_bridge(불요 — 직접 imdecode), medi_interfaces. (pip: ultralytics·lap. 모델 없으면 노드는 미탐지로 graceful 기동.)

## 검증

- 단위: `follow_control` — follow_cmd(원/근/유지·후진), FollowFSM(FOLLOW→LOST_WAIT→lost→복귀). 로봇·카메라 무관.
- 빌드: `colcon build --packages-select nurse_tracker` + import.
- 통합(허브와): 허브 round 등록(이미 reactive) + nurse_tracker 기동 → `start round` → set(active) 수신·status 하트비트 → 허브가 cmd_vel 중계. (실카메라 추종은 사용자 실행 — OAK-D 스트림 필요.)

## 범위 밖 (후속)

- OSNet ReID 재포착(perception 훅) — 교차 오인이 실제 문제 시.
- 허브 depth 안전게이트 입력(perception.front_depth → 허브).
- 웹 표시(TargetBBox 시각화), 시뮬.
