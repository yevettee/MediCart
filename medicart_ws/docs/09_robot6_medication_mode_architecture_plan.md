# ROBOT6 투약 모드 풀 시퀀스 아키텍처 계획

작성일: 2026-06-10  
대상: MediCart ROBOT6, Scenario B 확장  
목적: 현재 `nurse_cart` 구조를 기준으로, 약품실 OCR 이후 간호사 추종, 병상 앞 자동 정지, 약 포장 QR 2차 검증, 복귀/도킹까지 이어지는 투약 모드를 설계한다.

---

## 1. 한 줄 결론

현재 시스템은 `투약모드 시작 -> undock -> 약품실 이동 -> OCR 완료 -> 약품실 입구 이동 -> 간호사 추종 시작 -> 수동 회진 종료 -> 홈 복귀/도킹`까지만 설계되어 있고, 목표 시나리오에는 `침대 앞 자동 정지 이벤트`, `약 포장 QR 검증`, `웹 경고/YES 표시`, `투약 모드 off로 복귀` 상태가 추가되어야 한다.

침대 앞 자동 정지는 Nav2 keepout filter 자체로 처리하는 것이 아니라, AMCL pose 또는 TF를 보는 `bed_zone_monitor`가 병상 사각 영역 진입을 감지하고 mission_manager에 `bed_arrived` 이벤트를 보내서 `round` 추종 모드를 끄는 방식이 가장 적합하다.

구현 전에 반드시 정해야 하는 것은 두 가지다.

| 결정 항목 | 추천 | 이유 |
|---|---|---|
| 병상 앞 정지 기준 | `map` frame polygon zone | 현재 ROBOT6가 AMCL/Nav2 기반으로 위치를 알고 있고, 추종 중에도 pose 기반 이벤트를 만들 수 있음 |
| 약 포장 QR 인식 주체 | 1차는 웹 카메라, 2차 확장은 OAK-D | demo 안정성은 웹 카메라가 높고, 시간이 남으면 로봇 카메라 QR node로 자율성을 높일 수 있음 |

---

## 2. 현재 ROBOT6 Scenario B 구조

### 2.1 현재 실행 노드

현재 `src/mission_manager/launch/scenario_b.launch.py`는 아래 노드를 띄운다.

| 노드 | 패키지 | 역할 |
|---|---|---|
| `db_node` | `db_bridge` | Firebase RTDB `robot6/mission_pool`을 ROS `/robot6/mission_request`로 중계 |
| `mission_manager_node` | `mission_manager` | 미션 라우팅, Nav2 goal 실행, round 추종 모드 중재 |
| `tracker_node` | `nurse_tracker` | `round` 모드가 켜졌을 때 OAK-D/YOLO 기반 간호사 추종 속도 생성 |

단, localization/Nav2/RViz는 이 launch 안에 포함되어 있지 않다. 별도로 `loc 6`, `nav 6`, `rv 6` 또는 팀 bashrc alias에 맞는 명령으로 켜야 한다.

### 2.2 현재 웹 버튼 흐름

현재 웹은 로봇과 직접 ROS 통신하지 않는다. 웹은 Flask backend REST API를 호출하고, backend가 Firebase RTDB를 쓴다. 로봇 쪽 `db_node`가 RTDB를 listen해서 ROS topic으로 바꾼다.

| 웹 동작 | Backend API | Firebase RTDB | ROS 변환 |
|---|---|---|---|
| 회진/투약 시작 | `POST /api/nurse_cart/start` | `robot6/mission_pool/<id>`에 `action=nurse_cart_mission` push | `db_node`가 `/robot6/mission_request` publish |
| OCR 완료 | `POST /api/nurse_cart/ocr_done` | `robot6/nurse_cart/ocr_done=true` | `db_node`가 `/robot6/nurse_cart/ocr_done` publish |
| 회진 종료 | `POST /api/nurse_cart/round_done` | `robot6/nurse_cart/round_done=true` | `db_node`가 `/robot6/nurse_cart/round_done` publish |
| 단계 조회 | `GET /api/nurse_cart/phase` | `robot6/nurse_cart/phase` read | 웹 badge/redirect에 사용 |

### 2.3 현재 ROS 내부 흐름

현재 `NurseCartSequencer` 상태는 아래와 같다.

```text
IDLE
  -> GOTO_PHARMACY
  -> WAIT_OCR
  -> GOTO_STANDBY
  -> START_ROUND
  -> WAIT_ROUND_DONE
  -> GOTO_HOME
  -> DONE
```

세부 동작은 다음과 같다.

1. `nurse_cart_mission` 수신
   - `db_node`가 `robot6/mission_pool/<id>`를 보고 `/robot6/mission_request` 발행.
   - `mission_manager_node`가 action이 `nurse_cart_mission`이면 `NurseCartSequencer.start()` 호출.

2. `GOTO_PHARMACY`
   - `NavExecutor`가 `/robot6/dock_status`를 보고 docked/unknown이면 먼저 `/robot6/undock` action 호출.
   - 이후 `/robot6/navigate_to_pose` action으로 약품실 좌표 이동.

3. `WAIT_OCR`
   - 약품실 도착 시 mission feedback detail을 `pharmacy_arrived`로 발행.
   - `db_node`가 이것을 보고 `robot6/nurse_cart/phase=arrived` 기록.
   - 웹 `/display` 또는 `/ocr` 쪽은 이 phase를 보고 OCR 화면으로 이동하거나 badge를 갱신.

4. `OCR 완료`
   - 웹 OCR 완료 버튼이 `robot6/nurse_cart/ocr_done=true` 기록.
   - `db_node`가 `/robot6/nurse_cart/ocr_done` 발행.
   - `mission_manager_node`가 `NurseCartSequencer.signal_ocr_done()` 호출.

5. `GOTO_STANDBY`
   - 로봇이 약품실 입구 standby 좌표로 Nav2 이동.

6. `START_ROUND`
   - `ModeArbiter`가 `round` 모드를 start.
   - `tracker_node`는 `/robot6/mode/round/set`에서 `active=true`를 받고 간호사 추종을 시작.
   - `tracker_node`는 `/robot6/mode/round/cmd_vel`을 발행하고, `mission_manager_node`가 safety gate를 거쳐 `/robot6/cmd_vel`로 내보낸다.

7. `WAIT_ROUND_DONE`
   - 현재 구조에서는 병상 앞 자동 정지 조건이 없다.
   - 웹의 회진 종료 버튼 또는 수동 trigger가 `round_done=true`를 보내야 홈 복귀로 넘어간다.

8. `GOTO_HOME`
   - `round` 모드를 끄고 Nav2로 도킹 스테이션 좌표 이동.
   - `dock_after=True`라서 도착 후 `/robot6/dock` action 호출.

### 2.4 현재 OCR 후 입구에서 멈춰 보이는 이유

OCR 완료 버튼을 누른 뒤 로봇이 입구 쪽으로 살짝 이동하고 멈추는 것은 현재 코드상 정상적인 중간 단계일 수 있다.

가능한 해석은 두 가지다.

1. `GOTO_STANDBY`에 도착했고, 그 다음 `round` 추종 모드는 켜졌지만 간호사 target이 아직 잡히지 않았다.
   - 확인: `ros2 topic echo /robot6/robot_mode`
   - 확인: `ros2 topic echo /robot6/mode/round/status`
   - 확인: `ros2 topic echo /nurse_tracker/target`

2. `tracker_node`가 실행되지 않았거나 OAK-D/YOLO 입력이 들어오지 않아 추종 cmd_vel이 안 나온다.
   - 확인: `ros2 node list | grep tracker`
   - 확인: OAK-D RGB/depth topic이 살아있는지 확인.

즉, 현재 architecture 기준으로는 “입구 도착 후 추종 모드 활성화”까지만 있고, “병상 앞 도착 자동 판단”은 없다.

---

## 3. 목표 투약 모드 풀 시퀀스

사용자가 정의한 목표 시나리오는 다음이다.

```text
웹 투약모드 ON
  -> start trigger
  -> undock
  -> 약품실 이동
  -> OCR로 환자 약품 리스트 비교
  -> OCR 완료 버튼
  -> 간호사 tracking 시작
  -> 간호사를 따라 병원 호실/침대 앞으로 이동
  -> 침대 앞 영역 진입 감지
  -> tracking 자동 해제
  -> 약 포장 QR 인식
  -> QR 성공: YES 표시
  -> QR 실패: "환자의 약품이 아닙니다" 로그 + 웹 경고
  -> 웹 투약모드 OFF
  -> 도킹 스테이션 복귀
  -> dock
```

### 3.1 제안 상태머신

현재 `NurseCartSequencer`를 확장하거나 새 `MedicationSequencer`를 만든다. 발표/구현 명확성을 생각하면 새 action 이름을 두는 것이 좋다.

제안 action:

```text
medication_mission
```

제안 상태:

| 상태 | 의미 | 다음 전이 |
|---|---|---|
| `IDLE` | 아무 투약 미션 없음 | start |
| `GOTO_PHARMACY` | undock 후 약품실 이동 | Nav2 success |
| `WAIT_OCR_VERIFY` | 약품 OCR/처방 비교 대기 | `ocr_done` |
| `GOTO_STANDBY` | 약품실 입구 이동 | Nav2 success |
| `TRACK_NURSE_TO_BED` | 간호사 추종 활성화 | `bed_arrived` |
| `WAIT_MEDICATION_QR` | 병상 앞 정지 후 약 포장 QR 대기 | `qr_match` 또는 `qr_mismatch` |
| `QR_CONFIRMED` | QR가 현재 환자/약품과 일치 | `medication_off` 또는 자동 완료 |
| `QR_MISMATCH` | QR 불일치, 웹 경고 표시 | 재스캔 또는 `medication_off` |
| `RETURN_HOME` | 투약 모드 off 후 홈 좌표 이동 | Nav2 success |
| `DOCK` | dock action 수행 | dock success |
| `DONE` | 투약 시퀀스 종료 | idle reset |
| `FAILED` | 실패/timeout | 운영자 clear |

핵심 차이:

- 현재는 `WAIT_ROUND_DONE`에서 사람이 종료 버튼을 누를 때까지 tracking 유지.
- 목표는 `TRACK_NURSE_TO_BED`에서 `bed_zone_monitor`가 자동으로 `bed_arrived`를 보내 tracking을 끊고 QR 단계로 넘어감.

---

## 4. 현재 구조와 목표 구조의 차이

### 4.0 현재 아키텍처와 목표 아키텍처 한눈에 비교

현재 아키텍처는 `약품실 이동 + OCR 완료 후 간호사 추종 시작 + 수동 종료 후 복귀` 구조다. 목표 아키텍처는 여기에 `병상 zone 도착 판단`, `약 포장 QR 2차 검증`, `투약 경고/YES 결과`, `투약모드 OFF 복귀`가 추가된다.

현재 구조:

```text
Web
  -> Flask Backend
  -> Firebase RTDB
     - robot6/mission_pool
     - robot6/nurse_cart/ocr_done
     - robot6/nurse_cart/round_done
     - robot6/nurse_cart/phase
  -> db_node
  -> /robot6/mission_request
  -> mission_manager_node
     - NurseCartSequencer
     - NavExecutor
     - ModeArbiter
  -> Nav2 / robot6/navigate_to_pose
  -> nurse_tracker round mode
  -> 수동 round_done
  -> home + dock
```

목표 구조:

```text
Web Medication UI
  -> Flask Backend
  -> Firebase RTDB
     - robot6/mission_pool
     - robot6/medication/phase
     - robot6/medication/ocr_done
     - robot6/medication/mode_off
     - robot6/medication/bed_arrival
     - robot6/medication/qr
     - robot6/medication/alert
     - patients/<pid>/medication_packages/<pkg_id>
  -> db_node
  -> /robot6/mission_request
  -> mission_manager_node
     - MedicationSequencer 또는 확장 NurseCartSequencer
     - NavExecutor
     - ModeArbiter
     - bed_arrived/qr_result/off 이벤트 처리
  -> Nav2 / robot6/navigate_to_pose
  -> nurse_tracker round mode
  -> bed_zone_monitor가 zone 진입 감지
  -> round 자동 stop
  -> 약 포장 QR 검증
  -> YES 또는 "환자의 약품이 아닙니다"
  -> medication off
  -> home + dock
```

### 4.0.1 그대로 유지되는 부분

| 영역 | 현재 역할 | 목표에서도 유지되는 이유 |
|---|---|---|
| Web -> Flask -> Firebase RTDB | 웹 명령을 RTDB에 저장 | ROS와 웹을 직접 연결하지 않는 현재 구조가 안정적이고 이미 동작함 |
| `db_node` | RTDB를 ROS topic으로 중계 | 기존 bridge 패턴을 그대로 확장하면 됨 |
| `mission_manager_node` | 미션 라우팅, 모드 중재 | 전체 로봇 행동의 중앙 controller 역할 유지 |
| `NavExecutor` | undock, Nav2 goal, dock | 약품실 이동과 복귀/도킹은 기존 방식 재사용 |
| Nav2 stack | 고정 좌표 이동 | 약품실, standby, home 이동은 그대로 Nav2가 담당 |
| `nurse_tracker` | 간호사 추종 `round` mode | OCR 후 병상까지 따라가는 핵심 기능이므로 유지 |
| `ModeArbiter` | `goto`와 `round` 모드 충돌 방지 | Nav2 주행과 추종 주행을 한 로봇 base에서 중재해야 함 |

### 4.0.2 새로 추가되는 부분

| 추가 요소 | 위치 | 왜 필요한가 |
|---|---|---|
| `robot6/medication/*` RTDB schema | Firebase | 기존 `nurse_cart/phase`만으로는 QR, 병상 도착, 경고, package 상태를 표현하기 부족 |
| `MedicationSequencer` | `mission_manager` | 현재 `NurseCartSequencer`는 `WAIT_ROUND_DONE`까지만 있어서 bed/QR 단계를 담기 어려움 |
| `bed_zone_monitor` | ROS node 또는 mission_manager 내부 module | 추종 중 병상 앞 polygon zone에 들어왔는지 감지해야 함 |
| `/robot6/medication/bed_arrived` | ROS topic | zone monitor가 mission_manager에 “이제 추종을 끊어라”라고 알리는 이벤트 |
| 약 포장 QR verifier | Web backend 또는 ROS node | 환자 QR이 아니라 포장된 약 QR이 현재 환자/처방과 맞는지 확인해야 함 |
| `patients/<pid>/medication_packages/<pkg_id>` | Firebase | OCR로 확인된 약품 묶음과 QR payload를 DB에 남겨야 함 |
| 웹 경고/YES 표시 | Frontend | QR 성공/실패를 의료진에게 즉시 보여줘야 함 |

### 4.0.3 역할이 바뀌는 부분

| 항목 | 현재 | 목표 |
|---|---|---|
| `round_done` | 사람이 회진 종료 버튼을 눌러 추종 종료와 복귀를 시작 | 병상 도착은 자동 `bed_arrived`로 처리하고, 복귀는 `medication/off`로 분리 |
| `nurse_cart/phase` | 거의 `idle`, `arrived` 중심 | `medication/phase`로 `tracking`, `bed_arrived`, `wait_qr`, `qr_confirmed`, `qr_mismatch`, `returning`, `docked`까지 표현 |
| QR 기능 | 현재 `/ocr` 화면에서 환자 QR 확인에 가까움 | 약품 포장 QR을 읽고 expected package와 비교하는 2차 투약 확인 |
| Nav2 filter | 현재 사용 흐름에 직접 없음 | keepout/speed는 안전 보조로만 사용 가능, 추종 정지 trigger는 zone monitor가 담당 |
| mission 종료 | `round_done` 후 바로 home/dock | QR 성공/실패 확인 후 `투약모드 OFF`에서 home/dock |

### 4.0.4 기존 구조도 기준으로 추가 박스 표시

기존 구조도에서 그대로 두는 박스:

- Web Frontend
- Flask Backend
- Firebase RTDB
- `db_bridge/db_node`
- `mission_manager/mission_manager_node`
- Nav2 Stack
- Localization / AMCL
- `nurse_tracker/tracker_node`
- TurtleBot4/Create3 base

기존 구조도에 새로 그려야 하는 박스:

- `MedicationSequencer`
- `Bed Zone Monitor`
- `Medication QR Verifier`
- `Medication Package DB`
- `Medication Alert / Result UI`

기존 선에서 바뀌는 것:

```text
기존:
OCR 완료 -> GOTO_STANDBY -> START_ROUND -> 사람이 round_done -> HOME/DOCK

목표:
OCR 완료 -> GOTO_STANDBY -> START_ROUND
        -> bed_zone_monitor가 bed_arrived
        -> round 자동 stop
        -> 약 포장 QR 검증
        -> YES/경고
        -> 투약모드 OFF
        -> HOME/DOCK
```

### 4.1 통신 방식 차이

| 구분 | 현재 | 목표 |
|---|---|---|
| 시작 명령 | `nurse_cart_mission` | `medication_mission` 또는 `nurse_cart_mission` 확장 |
| OCR 완료 | RTDB flag `nurse_cart/ocr_done` | 유지 가능. 단, 환자/약품/expected_package 정보도 같이 저장 |
| 추종 시작 | OCR 후 standby 도착 시 자동 `round` start | 동일 |
| 추종 정지 | 웹 `round_done` 수동 | `bed_zone_monitor`가 자동 `bed_arrived` 이벤트 발행 |
| 병상 도착 데이터 | 없음 | `robot6/medication/bed_arrival` 기록 |
| QR 검증 | 현재는 웹 OCR 페이지의 환자 QR 확인 중심 | 약 포장 QR payload를 expected package와 비교 |
| 웹 경고 | 약품 OCR mismatch 표시만 있음 | QR mismatch 시 전역 alert/투약 화면 경고 필요 |
| 복귀 트리거 | `round_done` | `medication/off` 또는 투약 모드 OFF |

### 4.2 새로 필요한 ROS topic

| Topic | Type | Publisher | Subscriber | 의미 |
|---|---|---|---|---|
| `/robot6/medication/bed_arrived` | `std_msgs/String(JSON)` | `bed_zone_monitor` | `mission_manager_node` | 로봇이 목표 침대 앞 영역에 들어옴 |
| `/robot6/medication/qr_result` | `std_msgs/String(JSON)` | `medication_qr_node` 또는 `db_node` | `mission_manager_node` | 약 포장 QR 검증 결과 |
| `/robot6/medication/off` | `std_msgs/String(JSON)` | `db_node` | `mission_manager_node` | 웹 투약 모드 OFF |
| `/robot6/mission_feedback` | 기존 | `mission_manager_node` | `db_node` | phase/status 기록 |

예시 payload:

```json
{
  "mission_id": "med_1781073432",
  "patient_id": "P-2026-0001",
  "room_id": "601",
  "bed_id": "A",
  "zone_id": "bed_601_A",
  "pose": {"x": 1.23, "y": -2.34, "yaw": 1.57},
  "ts": 1781073432000
}
```

### 4.3 새로 필요한 Firebase RTDB schema

현재는 `robot6/nurse_cart/phase`, `ocr_done`, `round_done` 정도만 있다. 목표 구조에서는 투약 전용 상태를 따로 두는 것이 좋다.

제안 RTDB:

```text
robot6/
  medication/
    active: true|false
    phase: "idle" | "goto_pharmacy" | "wait_ocr" | "tracking" | "bed_arrived" | "wait_qr" | "qr_confirmed" | "qr_mismatch" | "returning" | "docked"
    current_mission_id: "med_..."
    current_patient_id: "P-2026-0001"
    current_room_id: "601"
    current_bed_id: "A"
    expected_package_id: "pkg_..."
    expected_med_hash: "..."
    ocr_done: false
    mode_off: false
    bed_arrival:
      zone_id: "bed_601_A"
      pose: {x: 1.23, y: -2.34, yaw: 1.57}
      ts: 1781073432000
    qr:
      expected_payload: {...}
      scanned_payload: {...}
      match: true|false
      reason: "ok" | "patient_mismatch" | "package_mismatch" | "unverified_meds"
      ts: 1781073432000
    alert:
      level: "warning"
      message: "환자의 약품이 아닙니다"
      ts: 1781073432000
```

환자별 약 포장 기록:

```text
patients/
  P-2026-0001/
    medication_packages/
      pkg_20260610_001:
        package_id: "pkg_20260610_001"
        patient_id: "P-2026-0001"
        injection_ids: ["inj1", "inj2"]
        medication_hash: "sha256..."
        status: "prepared" | "confirmed" | "mismatch"
        ocr_verified_at: 1781073432000
        qr_confirmed_at: null
```

### 4.4 누가 어떤 데이터를 보는가

| 데이터 | 저장 위치 | 작성자 | 조회자 |
|---|---|---|---|
| 미션 시작 | `robot6/mission_pool/<id>` | 웹 backend | `db_node` |
| 투약 phase | `robot6/medication/phase` | `db_node` 또는 backend | 웹 frontend |
| 약품 OCR 결과 | `patients/<pid>/injections/<inj_id>` | backend OCR verify API | 웹 frontend, 의료진 |
| 약 포장 expected QR | `patients/<pid>/medication_packages/<pkg_id>` | backend | QR verifier, 웹 |
| 병상 도착 이벤트 | `robot6/medication/bed_arrival` | `bed_zone_monitor` -> mission feedback -> `db_node` | 웹 frontend |
| QR actual result | `robot6/medication/qr` | QR verifier | mission_manager, 웹 |
| 경고 | `robot6/medication/alert` 또는 공통 `alerts` | QR verifier/backend | 웹 alert stream |

---

## 5. 침대 앞에서 tracking을 어떻게 멈출 것인가

### 5.1 질문에 대한 직접 답

가능하다. 병원 호실/침대 앞에 사각형 또는 polygon zone을 정의하고, 로봇의 현재 map pose가 그 영역 안으로 들어오면 tracking mode를 해제할 수 있다.

단, 이것을 Nav2 keepout filter만으로 처리하는 방식은 맞지 않다. Nav2 costmap filter는 주로 costmap의 비용, 금지구역, 속도 제한을 바꾸는 기능이고, “영역에 들어왔으니 mission_manager에 이벤트를 보낸다”는 애플리케이션 이벤트는 기본 제공 목적이 아니다. 그래서 별도 `bed_zone_monitor`가 필요하다.

### 5.2 추천 방식: `bed_zone_monitor`

구조:

```text
/robot6/amcl_pose 또는 TF map->base_link
  -> bed_zone_monitor
  -> /robot6/medication/bed_arrived
  -> mission_manager_node
  -> ModeArbiter stop round
  -> /robot6/cmd_vel = 0
  -> phase = wait_qr
```

동작:

1. mission 시작 시 현재 환자의 `room_id`, `bed_id`, `target_zone_id`를 params 또는 Firebase에서 읽는다.
2. `bed_zone_monitor`는 `map` frame 기준 polygon 목록을 가진다.
3. `/robot6/amcl_pose` 또는 TF `map -> base_link`로 현재 로봇 좌표를 읽는다.
4. 현재 target zone 안에 들어왔는지 point-in-polygon으로 판단한다.
5. 0.5초 이상 연속으로 zone 안에 있으면 false positive를 막기 위해 도착 확정.
6. `/robot6/medication/bed_arrived`를 발행한다.
7. `mission_manager_node`가 `round` 모드를 끄고 QR 대기 상태로 전이한다.

zone config 예시:

```yaml
bed_zones:
  - id: bed_601_A
    room_id: "601"
    bed_id: "A"
    frame_id: map
    dwell_sec: 0.5
    polygon:
      - [1.10, -2.80]
      - [2.05, -2.80]
      - [2.05, -1.95]
      - [1.10, -1.95]
  - id: bed_601_B
    room_id: "601"
    bed_id: "B"
    frame_id: map
    dwell_sec: 0.5
    polygon:
      - [2.20, -2.80]
      - [3.10, -2.80]
      - [3.10, -1.95]
      - [2.20, -1.95]
```

장점:

- 현재 `nurse_tracker`를 거의 건드리지 않고 붙일 수 있다.
- Nav2가 주행 중이 아니어도 동작한다. 지금 추종은 Nav2가 아니라 `round` reactive mode이기 때문에 이 점이 중요하다.
- 병상별 사각형/다각형을 Firebase 또는 YAML로 관리할 수 있다.
- 발표 때 “localization pose 기반 geofence event”라고 명확하게 설명할 수 있다.

주의:

- map 좌표가 정확해야 한다.
- AMCL 초기 pose가 틀리면 zone 판정도 틀린다.
- 병실 문 앞 zone과 침대 앞 zone을 구분해야 한다.
- 추종 중 사람 때문에 로봇이 zone 근처를 스치기만 해도 멈추지 않도록 dwell time과 hysteresis가 필요하다.

---

## 6. Nav2 filter로 가능한 것과 불가능한 것

### 6.1 Keepout filter

Nav2 공식 문서의 keepout tutorial은 filter mask를 준비하고, `costmap_filter_info_server`와 mask map server를 띄운 뒤, global/local costmap에 `nav2_costmap_2d::KeepoutFilter`를 추가하는 방식이다.

Keepout filter는 “로봇이 들어가면 안 되는 영역” 또는 preferred lanes 같은 navigation costmap 정책에 가깝다.

병상 앞 자동 정지에 그대로 쓰기 어려운 이유:

- 병상 앞 영역을 keepout으로 만들면 로봇이 그 영역에 진입하지 않도록 회피한다.
- 우리는 오히려 병상 앞 영역에 들어온 뒤 멈춰야 한다.
- keepout filter 자체가 mission_manager에 `entered_zone` 같은 이벤트를 주는 구조가 아니다.

따라서 keepout은 “환자 침대에 너무 가까이 붙지 말아야 하는 금지영역”을 막는 안전 레이어로는 좋지만, “tracking stop trigger”로는 부적합하다.

### 6.2 Speed filter

Nav2 speed filter는 filter mask 값을 속도 제한으로 바꿔 controller server가 쓰게 한다. 공식 문서 기준으로 speed filter는 `/speed_limit` 성격의 제한값을 만들고, mask value를 `base + multiplier * mask_value`로 해석한다.

사용 가능성:

- 병실 내부나 침대 근처에서는 속도를 낮추는 용도로 좋다.
- 예: 복도는 정상 속도, 병실/침대 근처 zone은 20% 속도.

한계:

- speed filter도 “이 영역에 들어왔으니 round mode를 끄라”는 이벤트를 만들지는 않는다.
- 현재 추종 cmd_vel은 custom `nurse_tracker` -> `mission_manager` 게이트 구조라서 Nav2 controller speed limit과 직접 연결되지 않을 수 있다.

결론:

- speed filter는 보조 안전 기능으로 고려.
- tracking stop은 `bed_zone_monitor`가 담당.

### 6.3 Binary filter

공식 `costmap_filter_info_server` 문서는 filter type으로 `0 keepout/preferred lanes`, `1 speed percent`, `2 absolute speed`, `3 binary filter`를 정의한다.

binary filter도 mask 해석용이지, 현재 architecture의 mission event를 자동 생성하는 장치로 보기 어렵다. binary mask를 구독해서 직접 이벤트를 만들 수도 있지만, 그럴 바에는 단순 polygon 기반 `bed_zone_monitor`가 구현과 설명이 더 쉽다.

### 6.4 Waypoint follower task executor

Nav2 Waypoint Follower에는 waypoint에 도착했을 때 task executor plugin을 실행하는 구조가 있다. 공식 문서에서 `waypoint_task_executor_plugin`은 waypoint 도착 시 실행할 작업을 정의하는 plugin이다.

사용 가능성:

- 로봇이 Nav2로 “침대 앞 좌표”까지 이동하는 구조라면, waypoint 도착 시 QR scan task를 실행할 수 있다.

한계:

- 현재 목표는 “간호사를 tracking해서 병상까지 따라간다”이다.
- tracking 중에는 Nav2 waypoint follower가 주행을 담당하지 않으므로 waypoint 도착 plugin이 자연스럽게 끼어들 자리가 없다.

결론:

- 추종을 포기하고 침대 좌표 Nav2 이동으로 바꾸면 Waypoint Follower가 좋다.
- 간호사 추종을 유지하려면 `bed_zone_monitor`가 더 맞다.

### 6.5 Nav2 Dynamic Object Following 대안

Nav2 공식 문서에는 dynamic object following 기능도 있다. `FollowObject` action은 pose topic 또는 TF frame을 따라가고, desired distance와 recovery 동작을 제공한다.

하지만 현재 시스템은 이미 `nurse_tracker`가 YOLO target을 찾고 custom `round` mode로 cmd_vel을 생성한다. 지금 단계에서는 Nav2 following server로 갈아타기보다, 현재 추종 구조를 유지하고 병상 zone event만 추가하는 편이 구현 리스크가 낮다.

---

## 7. 약 포장 QR 2차 검증 설계

### 7.1 현재 QR과 목표 QR의 차이

현재 `/ocr` 페이지 QR 모드는 주로 “환자 QR”을 읽어 선택 환자와 맞는지 확인한다.

목표 QR은 “약품 포장 QR”이다. 즉 OCR 검증을 통과한 약품들을 포장한 뒤 그 포장에 붙인 QR을 침대 앞에서 다시 읽어야 한다.

따라서 QR payload는 환자 ID만 있으면 부족하다.

### 7.2 제안 QR payload

```json
{
  "type": "medication_package",
  "package_id": "pkg_20260610_001",
  "patient_id": "P-2026-0001",
  "injection_ids": ["inj1", "inj2"],
  "medication_hash": "sha256...",
  "issued_at": 1781073432000
}
```

검증 기준:

1. `type == medication_package`
2. `package_id`가 현재 미션의 `expected_package_id`와 일치
3. `patient_id`가 현재 미션의 `current_patient_id`와 일치
4. `medication_hash`가 OCR 검증 후 저장한 expected hash와 일치
5. 해당 injection들이 모두 `confirmed` 또는 `prepared` 상태

### 7.3 QR 성공/실패 동작

성공:

```text
robot6/medication/qr/match=true
robot6/medication/phase=qr_confirmed
patients/<pid>/medication_packages/<pkg_id>/status=confirmed
웹: YES 표시
```

실패:

```text
robot6/medication/qr/match=false
robot6/medication/phase=qr_mismatch
robot6/medication/alert/message="환자의 약품이 아닙니다"
patients/<pid>/medication_packages/<pkg_id>/status=mismatch
웹: 경고 표시
```

### 7.4 QR을 누가 읽을지 결정 필요

선택 A: 로봇 OAK-D가 약 포장 QR을 읽음

- 장점: 로봇 시나리오가 더 자율적.
- 단점: QR을 카메라 시야에 맞게 보여줘야 하고, 조명/거리 영향이 큼.
- 필요 노드: `medication_qr_node`
  - subscribe: `/robot6/oakd/rgb/image_raw/compressed`
  - publish: `/robot6/medication/qr_result`

선택 B: 웹 태블릿/노트북 카메라가 약 포장 QR을 읽음

- 장점: 현재 `/ocr` 페이지의 jsQR 구조를 재사용하기 쉽다.
- 단점: 로봇 카메라 기반 완전자율은 아님.
- 필요 API: `POST /api/medication/qr/verify`

현 demo 안정성 기준 추천:

1차 구현은 웹 카메라 QR로 빠르게 붙이고, 시간이 남으면 robot OAK-D QR node를 추가한다.

---

## 8. 구현 계획

### Phase 1: 데이터 계약 확정

1. `medication_mission` action 이름 확정.
2. RTDB `robot6/medication/*` schema 확정.
3. QR payload 형식 확정.
4. 병상 zone 좌표를 YAML로 둘지 RTDB `rooms/<room>/beds/<bed>/zone`에 둘지 결정.

### Phase 2: ROS state machine 확장

1. `MedicationSequencer` 추가 또는 `NurseCartSequencer` 확장.
2. `mission_manager_node`에 `medication_mission` route 추가.
3. `db_node`에 새 RTDB flag listener 추가.
   - `robot6/medication/ocr_done`
   - `robot6/medication/mode_off`
   - 선택: `robot6/medication/qr_result`
4. feedback detail을 phase별로 명확히 변경.

예시 feedback detail:

```text
pharmacy_arrived
tracking_started
bed_arrived
wait_medication_qr
qr_confirmed
qr_mismatch
returning_home
docked
```

### Phase 3: `bed_zone_monitor`

1. `/robot6/amcl_pose` subscribe 또는 TF listener 구현.
2. target zone id를 params/RTDB에서 수신.
3. polygon 포함 판정 + dwell time.
4. `/robot6/medication/bed_arrived` publish.
5. mission_manager에서 이벤트 수신 시:
   - `round` stop
   - `/robot6/cmd_vel` zero
   - phase `wait_qr`

### Phase 4: QR 검증

웹 카메라 우선 구현:

1. backend에 `POST /api/medication/package/create` 추가.
2. backend에 `POST /api/medication/qr/verify` 추가.
3. frontend `/ocr` 또는 새 `/medication` 화면에서 package QR scan.
4. match이면 YES, mismatch이면 경고.

로봇 카메라 확장:

1. `medication_qr_node` 추가.
2. OpenCV QR detector 또는 pyzbar/jsQR equivalent 사용.
3. `/robot6/medication/qr_result` publish.

### Phase 5: 웹 UX

투약 모드 화면에 필요한 상태:

| Phase | 웹 표시 |
|---|---|
| `goto_pharmacy` | 약품실 이동 중 |
| `wait_ocr` | 약품 OCR 대기 |
| `tracking` | 간호사 추종 중 |
| `bed_arrived` | 병상 도착, QR 대기 |
| `qr_confirmed` | YES |
| `qr_mismatch` | 환자의 약품이 아닙니다 |
| `returning` | 도킹 스테이션 복귀 중 |
| `docked` | 도킹 완료 |

버튼:

- `투약모드 ON`: `/api/medication/start`
- `OCR 완료`: `/api/medication/ocr_done`
- `QR 재스캔`: local QR state reset
- `투약모드 OFF`: `/api/medication/off`

---

## 9. 발표 때 예상 질문과 답변

Q. 왜 OCR 완료 후 바로 병상으로 Nav2 이동하지 않고 간호사 tracking을 쓰나?  
A. 병상 이동 경로가 상황에 따라 간호사 동선과 함께 변할 수 있고, 의료진이 로봇을 병실까지 자연스럽게 유도하는 시나리오이기 때문이다. 고정 목적지 이동은 Nav2가 담당하고, 의료진 동행 구간은 `round` 추종 mode가 담당한다.

Q. 로봇은 어떻게 침대 앞이라는 것을 아나?  
A. AMCL localization으로 로봇의 map 좌표를 알고 있고, 병상 앞 영역을 map frame polygon으로 저장한다. `bed_zone_monitor`가 현재 pose가 해당 polygon 안에 일정 시간 이상 들어왔는지 감지해 `bed_arrived` 이벤트를 낸다.

Q. Nav2 filter로 사각형을 그리면 자동으로 멈출 수 있나?  
A. 사각형 mask는 만들 수 있지만, Nav2 keepout/speed filter는 costmap 정책을 바꾸는 기능이지 mission event를 발생시키는 기능이 아니다. keepout으로 만들면 오히려 그 영역에 못 들어가고, speed filter는 속도 제한만 한다. 그래서 stop trigger는 별도 zone monitor가 맡는 것이 맞다.

Q. QR은 환자 QR인가 약 QR인가?  
A. 목표 시나리오의 QR은 약 포장 QR이다. OCR로 검증된 약품들을 포장한 뒤 그 포장에 붙인 QR이며, 침대 앞에서 환자/약품/package id/hash가 현재 미션과 맞는지 2차 확인한다.

Q. QR이 틀리면 어디에 기록되나?  
A. `robot6/medication/qr/match=false`, `robot6/medication/alert/message="환자의 약품이 아닙니다"`, 환자별 package status `mismatch`로 기록한다. 웹은 이 값을 읽어 경고 표시를 띄운다.

Q. 투약 모드 OFF는 기존 round_done과 같은가?  
A. 개념은 비슷하지만 목표 시나리오에서는 `round_done`보다 `medication/off`가 더 명확하다. QR 성공/실패 이후 사용자가 OFF를 누르면 tracking이 이미 꺼진 상태에서 home Nav2 goal과 dock action을 수행한다.

---

## 10. 최종 추천 구조

가장 안정적인 구현 순서는 아래다.

```text
web medication ON
  -> RTDB mission_pool medication_mission
  -> db_node
  -> mission_manager MedicationSequencer
  -> NavExecutor undock + goto pharmacy
  -> OCR verify + expected package 생성
  -> ocr_done
  -> goto standby
  -> start round tracking
  -> bed_zone_monitor detects target bed zone
  -> stop round + wait QR
  -> web QR verify
  -> YES or warning
  -> medication OFF
  -> goto home + dock
```

이 구조가 좋은 이유:

- 현재 웹/RTDB/ROS bridge 패턴을 유지한다.
- 현재 `nurse_tracker`를 유지하므로 추종 기능을 새로 갈아엎지 않는다.
- Nav2는 원래 잘하는 `undock`, `NavigateToPose`, `dock`, optional speed/keepout safety에 집중한다.
- 침대 앞 도착 판단은 localization 기반 zone event로 분리되어 테스트와 발표 설명이 쉽다.
- 약 QR 검증은 환자 데이터/처방 데이터와 직접 연결되어 웹 경고까지 자연스럽게 이어진다.

---

## 11. 공식 Nav2 문서 근거

- [Nav2: Navigating with Keepout Zones](https://docs.nav2.org/tutorials/docs/navigation2_with_keepout_filter.html)
- [Nav2: Keepout Filter Parameters](https://docs.nav2.org/configuration/packages/costmap-plugins/keepout_filter.html)
- [Nav2: Speed Filter Parameters](https://docs.nav2.org/configuration/packages/costmap-plugins/speed_filter.html)
- [Nav2: Costmap Filter Info Server](https://docs.nav2.org/configuration/packages/map_server/configuring-costmap-filter-info-server.html)
- [Nav2: Waypoint Follower](https://docs.nav2.org/configuration/packages/configuring-waypoint-follower.html)
- [Nav2: Dynamic Object Following](https://docs.nav2.org/tutorials/docs/navigation2_dynamic_point_following.html)
