# MediCart Architecture 발표 정리본

기준 자료:

- `/home/rokey/Downloads/MediCartSystemArchitectureDesign.drawio.pdf`
- 현재 workspace 코드 확인: `db_bridge`, `mission_manager`, `patient_identifier`, `nurse_tracker`, `scanner`, `dashboard`, `medi_interfaces`

## 1. 한 문장 요약

MediCart는 웹 UI가 Firebase RTDB에 미션을 넣고, 각 로봇 PC의 `db_node`가 그 미션을 ROS2 명령으로 변환한 뒤, `mission_manager_node`가 Nav2, Create3, 인식 노드들을 순서대로 제어하는 구조이다.

발표 때 첫 문장:

> 이 시스템은 웹과 ROS를 직접 붙이지 않고, Firebase RTDB를 중간 명령 큐로 둔 구조입니다. 웹은 DB에 미션을 넣고, 로봇 PC의 `db_node`가 그 미션을 받아 ROS 토픽, 액션, 서비스로 변환해서 실제 로봇을 움직입니다.

## 2. 큰 구조

전체는 네 층으로 나눠서 설명하면 가장 명확하다.

| 층 | 구성 | 역할 |
| --- | --- | --- |
| Web/UI 층 | Web Frontend, FastAPI backend | 버튼, 문진, 약 선택, 대시보드 트리거 |
| Data/Command 층 | Firebase RTDB | 미션 큐, 상태 heartbeat, 로그, 환자/방/디스플레이 데이터 |
| Robot PC 층 | `db_bridge`, `mission_manager`, mode node, 인식 node, Nav2 | DB 명령을 ROS 실행 흐름으로 변환 |
| Hardware 층 | Create3 base, LiDAR, OAK-D, USB webcam | 실제 이동, 도킹, 센서 데이터 제공 |

핵심 의도:

- Web은 ROS2 네트워크에 직접 들어오지 않는다.
- Firebase RTDB가 명령 큐와 상태 저장소 역할을 한다.
- 각 로봇은 namespace로 분리된다. 예: `/robot3`, `/robot6`.
- 이동은 Nav2 action, 도킹은 Create3 action, 환자/방/처방 조회는 ROS service, 상태와 이벤트는 ROS topic으로 나눈다.

## 3. 주요 컴포넌트

### 3.1 PC3 Web/UI

PDF 기준 PC3에는 두 컴포넌트가 있다.

| 컴포넌트 | 역할 |
| --- | --- |
| Web Frontend | 문진 `/display`, 약 선택, 대시보드 버튼 |
| FastAPI backend | `/api/robots/{ns}/missions` 요청을 받아 Firebase에 mission push |

연결:

```text
Web Frontend
  -> HTTP / REST
  -> FastAPI backend
  -> firebase-admin push_mission()
  -> {ns}/mission_pool/{mid}
```

중요 포인트:

- 웹 버튼이 ROS topic을 직접 publish하지 않는다.
- FastAPI backend가 Firebase Admin SDK로 `mission_pool`에 명령을 넣는다.
- 이 설계 덕분에 웹 서버와 ROS 네트워크가 분리된다.

발표 문장:

> 웹에서 순찰 시작이나 투약 시작 버튼을 누르면, FastAPI가 바로 ROS로 보내는 것이 아니라 Firebase RTDB의 `mission_pool`에 pending 상태의 미션을 생성합니다. 이후 로봇 PC의 `db_node`가 이 큐를 감시하다가 ROS 명령으로 바꿉니다.

### 3.2 Firebase RTDB

PDF에 나온 주요 경로:

| RTDB path | 의미 |
| --- | --- |
| `{ns}/mission_pool/{mid}` | 웹이 넣는 미션 큐. `pending`, `running` 상태 관리 |
| `{ns}/mission_log/{mid}` | 끝난 미션 아카이브 |
| `{ns}/mission_status` | 1Hz heartbeat. 현재 미션, queue length, alive 상태 |
| `display/current_patient` | 웹 display 화면이 현재 환자를 띄우기 위한 값 |
| `patients/{id}` | 환자 기본 정보 |
| `patient_rooms/{id}` | 환자와 병실 매핑 |
| `rooms/{room_id}` | 방 좌표 `x, y, yaw`와 환자 배정 정보 |

왜 RTDB를 중심에 두었는가:

- 웹과 로봇을 느슨하게 연결하기 위해서이다.
- 미션 요청과 결과가 DB에 남아 디버깅과 시연 확인이 쉽다.
- 웹이 꺼졌다 켜져도 로봇 상태를 DB에서 다시 볼 수 있다.
- 로봇이 잠깐 끊겨도 `mission_status` heartbeat와 timeout으로 상태를 판단할 수 있다.

예상 질문:

> 왜 ROS topic으로 바로 보내지 않았나요?

답변:

> 웹 서버가 ROS2 discovery domain 안에 직접 들어오면 네트워크 설정, 보안, 배포가 복잡해집니다. 그래서 웹은 RTDB에 명령만 쓰고, 로봇 PC에서만 ROS 변환을 담당하게 했습니다. 이러면 웹과 ROS가 느슨하게 결합되고, 미션 기록도 DB에 남습니다.

### 3.3 각 로봇 PC의 `db_bridge`

각 로봇 PC에는 같은 구조의 `db_bridge package`가 있다.

핵심 노드:

| 노드 | 역할 |
| --- | --- |
| `db_node` | RTDB `mission_pool`을 listen하고 ROS `/mission_request`로 변환 |
| `rooms_server` | RTDB `/rooms`를 읽어 `ListRooms` 서비스 응답 |
| `prescription_server` | RTDB 환자 데이터를 읽어 `GetPrescription` 서비스 응답 |
| `display_bridge` | ROS 환자 식별 결과를 RTDB `display/current_patient`에 기록 |

연결:

```text
{ns}/mission_pool
  -> db_node listen
  -> /{ns}/mission_request
  -> mission_manager_node

mission_manager_node
  -> /{ns}/mission_feedback
  -> db_node
  -> {ns}/mission_log 기록
  -> {ns}/mission_pool/{mid} 삭제
```

왜 이렇게 만들었는가:

- `db_node`가 큐를 FIFO로 하나씩 처리해서 동시에 여러 명령이 로봇에 들어가는 것을 막는다.
- 미션마다 timeout을 두어 무한 대기를 방지한다.
- 1Hz heartbeat를 RTDB에 기록해서 웹이 로봇 alive 상태를 볼 수 있다.
- 완료 후 `mission_log`에 아카이브하고 `mission_pool`에서 삭제해 큐가 정리된다.

발표 문장:

> `db_node`는 DB와 ROS 사이의 통역사입니다. DB에는 미션이 `pending`으로 들어오고, `db_node`는 이를 하나씩 `/robotX/mission_request`로 발행합니다. 미션이 끝나면 `/robotX/mission_feedback`을 받아 `mission_log`에 저장하고 큐에서 제거합니다.

## 4. ROS 통신 타입별 의미

이 시스템은 topic, service, action을 용도별로 분리한다.

| 타입 | 쓰는 상황 | 예시 | 이유 |
| --- | --- | --- | --- |
| Topic | 상태나 이벤트를 계속 흘릴 때 | `/robot3/mission_request`, `/robot3/patient_identified`, `/robot6/mode/round/cmd_vel` | publish/subscribe로 느슨한 연결 |
| Service | 짧은 요청/응답이 필요할 때 | `/robot3/db/list_rooms`, `/robot6/db/get_prescription` | DB 조회처럼 즉시 응답이 필요한 작업 |
| Action | 오래 걸리고 feedback이 필요한 작업 | `/robot3/navigate_to_pose`, `/robot6/dock`, `/robot6/undock` | 이동/도킹은 시간이 걸리고 성공/실패 결과가 필요 |

예상 질문:

> 왜 이동은 service가 아니라 action인가요?

답변:

> 이동은 몇 초 이상 걸리고 중간 상태와 취소가 필요합니다. 그래서 Nav2의 `NavigateToPose` action을 사용합니다. 반대로 환자 처방 조회는 짧은 요청/응답이므로 service가 맞습니다.

## 5. `/robot3` 순찰 로봇 흐름

`robot3`의 목적은 병실 순회와 환자 확인이다.

### 5.1 웹에서 순찰 시작

```text
Web button "순찰 시작"
  -> POST /api/robots/robot3/missions
  -> {action: "patrol_mission"}
  -> Firebase robot3/mission_pool/{mid}
  -> robot3 db_node
  -> /robot3/mission_request
```

### 5.2 `mission_manager_node`

`robot3`의 `mission_manager_node`는 `patrol_mission`을 시퀀스로 처리한다.

```text
mission_request 수신
  -> IDLE
  -> UNDOCK
  -> PATROL_START
  -> patrol status == done ? 확인
  -> DOCK
  -> DONE
  -> mission_feedback
```

코드상 `MissionSequencer`의 핵심 순서:

```text
undock -> patrol mode start -> patrol done/failed 대기 -> dock
```

왜 시퀀서가 필요한가:

- 순찰은 단일 동작이 아니라 출발, 여러 waypoint 이동, 환자 확인, 복귀, 도킹이 묶인 workflow이다.
- `db_node` 입장에서는 하나의 미션으로 보이지만, 내부에서는 여러 action과 topic이 순서대로 실행된다.
- 실패해도 로봇 회수를 위해 dock 단계로 진행하는 정책을 둘 수 있다.

### 5.3 `patrol_mode_node`

`patrol_mode_node`는 병상 waypoint를 순회한다.

연결:

```text
/robot3/mode/patrol/set
  -> patrol_mode_node active true
  -> list_rooms(filter="bed")
  -> NavigateToPose(각 병상 좌표)
  -> 도착 시 /robot3/identify/start(room_id)
  -> dwell 6s
  -> 다음 waypoint
  -> /robot3/mode/patrol/status done
```

중요:

- PDF에는 `ListRooms`로 RTDB rooms를 읽는 흐름이 있다.
- 현재 코드에는 `use_config_waypoints=True` 기본값으로 dashboard 기준 고정 waypoint도 사용할 수 있다.
- 발표에서는 “설계상 DB rooms를 쓰며, 실좌표 보정 전에는 config waypoint로 대체 가능하다”고 말하면 안전하다.

### 5.4 환자 식별

환자 식별 흐름:

```text
patrol_mode_node
  -> /robot3/identify/start = room_id
  -> patient_identifier_node
  -> 최신 camera frame에서 QR scan
  -> /robot3/db/get_prescription(patient_id)
  -> DB상 환자 방 == 방문 room ?
  -> /robot3/patient_identified 1회 발행
  -> display_bridge
  -> RTDB display/current_patient update
```

상태:

| 상태 | 의미 |
| --- | --- |
| `identified` | QR 환자와 방문 병실이 일치 |
| `mismatch` | QR은 읽었지만 해당 병실 환자가 아님 |
| `absent` | timeout 동안 QR을 읽지 못함 |

왜 도착 후 스캔 윈도우인가:

- 로봇이 이동 중일 때 계속 환자를 판정하면 오검출 가능성이 크다.
- 목표 병실에 도착했을 때만 QR 확인을 열어 방과 환자를 정확히 매칭한다.
- timeout을 두어 환자가 없거나 QR을 못 읽는 상황도 종료 상태로 처리한다.

예상 질문:

> 환자 존재 여부를 YOLO로 보나요?

답변:

> 현재 구조에서는 병상 도착 후 QR 식별을 중심으로 판단합니다. QR을 읽고 DB의 환자 방과 방문 방을 비교해 `identified` 또는 `mismatch`를 만들고, 제한 시간 안에 QR을 못 읽으면 `absent`로 처리합니다.

## 6. `/robot6` 투약 및 회진 추종 로봇 흐름

`robot6`는 투약 시작과 round 추종, 약품 검증 흐름을 가진다.

### 6.1 웹에서 투약 시작

```text
Web button "투약 시작"
  -> POST /api/robots/robot6/missions
  -> {action: "start", mode: "round"}
  -> Firebase robot6/mission_pool/{mid}
  -> robot6 db_node
  -> /robot6/mission_request
  -> mission_manager_node
```

### 6.2 `mission_manager_node`의 mode arbiter

`mission_manager_node`는 모드 중재 허브이다.

모드 registry:

```text
round: reactive
patrol: nav
errand, guide, intake: nav
```

중재 우선순위:

```text
mapping > intake > round > errand > guide > patrol > idle
```

왜 arbiter가 필요한가:

- 여러 모드가 동시에 켜지는 것을 방지한다.
- 높은 우선순위 모드가 낮은 모드를 선점할 수 있다.
- reactive 모드의 속도 명령은 safety gate를 통과하게 한다.
- 모드 status가 끊기면 lost abort로 정리할 수 있다.

### 6.3 `nurse_tracker` round 추종

PDF와 코드 기준:

```text
/robot6/mode/round/set {active:true}
  -> tracker_node
  -> RGB + Depth 동기화
  -> YOLO로 nurse target 탐지
  -> error_x, depth 거리 계산
  -> /robot6/mode/round/cmd_vel 발행
  -> mission_manager safety_gate
  -> /robot6/cmd_vel
```

제어 판단:

| 조건 | 행동 |
| --- | --- |
| target fresh이고 `|error_x| > 0.25` | 회전만 해서 정렬 |
| target fresh이고 중앙 정렬됨 | 거리비례 직진 + 미세회전 |
| target 손실 지속 | HOLD 또는 LOST_WAIT |
| 정면 LiDAR 거리 `< 0.30m` | 전진속도 0 |

왜 Nav2가 아니라 tracker cmd_vel인가:

- Nav2는 고정된 map goal로 이동할 때 좋다.
- 간호사 추종은 목표가 계속 움직이는 reactive task이다.
- 그래서 tracker가 짧은 주기로 cmd_vel 후보를 만들고, mission_manager가 안전 게이트를 통과시킨다.

예상 질문:

> tracker가 바로 `/robot6/cmd_vel`을 내면 안 되나요?

답변:

> 바로 내면 안전 정책과 모드 중재를 우회하게 됩니다. 그래서 tracker는 `/robot6/mode/round/cmd_vel` 후보만 발행하고, 최종 `/robot6/cmd_vel`은 `mission_manager`가 safety gate와 arbitration을 거쳐 발행합니다.

### 6.4 투약 검증 흐름

PDF의 설계 흐름:

```text
round 중 환자 도착
  -> /robot6/verify/start = patient_id|room
  -> medicine_verifier_node
  -> 환자 QR 확인
  -> GetPrescription(patient_id)
  -> 약품 순차 스캔
  -> MedicineMatcher로 처방 순서/항목 대조
  -> 모두 일치하면 verify/done
  -> 투약/검증 상태를 display로 전달
```

중요한 구현 상태 메모:

- PDF에는 `medicine_verifier_node`와 약품 순차 검증 흐름이 상세히 설계되어 있다.
- 현재 코드에서는 `scanner_node`가 아직 skeleton 수준이고, `MedicineMatcher`는 문자열 매칭 로직만 구현되어 있다.
- `prescription_server`도 현재 `medicines`를 빈 배열로 반환한다고 주석에 적혀 있다.
- 발표에서 이 부분은 “설계된 투약 검증 파이프라인이며, 현재 구현은 OCR/처방 스키마 연동을 확장하는 단계”라고 구분해서 말하는 것이 좋다.

예상 질문:

> 투약 검증은 지금 완전히 동작하나요?

답변:

> 아키텍처상으로는 `verify/start -> 환자 QR -> 처방 조회 -> 약품 순차 스캔 -> MedicineMatcher -> verify/done` 흐름으로 설계되어 있습니다. 다만 현재 코드 기준으로는 scanner와 처방 medicines 스키마 연동은 확장 단계입니다. 환자 조회와 room 검증 기반은 있고, 약품 리스트와 OCR 결과를 연결하면 같은 구조로 완성됩니다.

## 7. Nav2와 Create3 연결

두 로봇 모두 하단 hardware 층은 비슷하다.

```text
Nav2 bt_navigator
  -> planner_server ComputePathToPose
  -> nav_msgs/Path
  -> controller_server FollowPath
  -> /robotX/cmd_vel
  -> Create3 base
```

센서 피드백:

```text
Create3 LiDAR /scan
  -> amcl
  -> /robotX/amcl_pose

/scan 또는 PointCloud
  -> costmap layers
  -> obstacle/inflation layer
  -> planner/controller에 반영
```

Dock/Undock:

```text
mission_manager or sequencer
  -> /robotX/undock action
  -> Create3 base

mission complete
  -> /robotX/dock action
  -> Create3 base
```

왜 Nav2와 Create3를 나눴는가:

- Nav2는 map 기반 목표 이동을 담당한다.
- Create3 dock/undock은 base가 제공하는 별도 action이다.
- 도킹 상태에서는 Nav2 이동 전에 undock이 선행되어야 한다.
- 미션 종료 후에는 dock으로 회수해 다음 시연/충전을 안정화한다.

예상 질문:

> 장애물 회피는 어디서 하나요?

답변:

> map 기반 이동은 Nav2의 global/local costmap이 `/scan` 등을 받아 obstacle/inflation layer로 반영합니다. 그리고 robot6의 reactive 추종 속도는 Nav2 costmap을 직접 타지 않기 때문에 mission_manager의 safety gate에서 정면 0.30m 이하일 때 전진속도를 0으로 제한합니다.

## 8. 상태 피드백과 로그 흐름

명령만 내려가는 것이 아니라 상태도 계속 올라간다.

```text
mission_manager_node
  -> /{ns}/mission_feedback
  -> db_node
  -> {ns}/mission_log/{mid}

db_node
  -> {ns}/mission_status 1Hz heartbeat

FastAPI backend
  -> GET /api/robots/{ns}/missions
  -> mission_status poll
  -> Web button running/done 표시
```

왜 heartbeat가 필요한가:

- 로봇이 살아 있는지 웹에서 확인해야 한다.
- 현재 처리 중인 mission id, action, elapsed time, queue length를 보여줄 수 있다.
- timeout과 함께 무한 대기 문제를 줄인다.

예상 질문:

> 미션 완료 여부는 웹이 어떻게 아나요?

답변:

> 로봇 내부에서 `mission_feedback`이 올라오면 `db_node`가 이를 RTDB의 `mission_log`와 `mission_status`에 반영합니다. 웹은 `/api/robots/{ns}/missions`로 status를 polling해서 버튼 상태를 running 또는 done으로 바꿉니다.

## 9. 연결 구조를 한 번에 말하는 발표용 순서

발표 때 다이어그램을 보면서 아래 순서로 말하면 자연스럽다.

1. 먼저 상단 Web/UI를 설명한다.
   - 사용자가 버튼을 누르면 FastAPI로 간다.
   - FastAPI는 ROS가 아니라 Firebase RTDB에 미션을 넣는다.

2. Firebase RTDB를 설명한다.
   - `mission_pool`은 명령 큐이다.
   - `mission_status`는 로봇 heartbeat이다.
   - `mission_log`는 완료 기록이다.
   - `rooms`, `patients`, `patient_rooms`는 DB 조회용이다.

3. 로봇 PC의 `db_bridge`를 설명한다.
   - DB 명령을 `/mission_request`로 바꾼다.
   - 결과 `/mission_feedback`을 DB에 다시 기록한다.

4. `mission_manager_node`를 설명한다.
   - 미션을 받아 system action, mode action, sequence action으로 나눈다.
   - dock/undock, Nav2 이동, mode 활성화 순서를 관리한다.

5. `robot3` 흐름을 설명한다.
   - 순찰 미션: undock, 병상 waypoint, 환자 QR 확인, display update, dock.

6. `robot6` 흐름을 설명한다.
   - 투약/round 미션: 약품실 이동, nurse 추종, 환자 도착, 약품 검증.

7. 하단 hardware와 Nav2를 설명한다.
   - Nav2가 path와 cmd_vel을 만들고 Create3가 실제 이동한다.
   - LiDAR scan은 AMCL과 costmap에 들어간다.

## 10. 질문 들어올 가능성이 큰 부분

### Q1. 왜 Firebase RTDB를 중간에 두었나요?

답변:

> 웹과 ROS를 직접 연결하지 않기 위해서입니다. RTDB가 미션 큐, 상태 저장소, 로그 저장소 역할을 하므로 웹은 ROS 네트워크를 몰라도 되고, 로봇은 DB를 통해 명령을 안정적으로 받아올 수 있습니다.

### Q2. 동시에 여러 미션이 들어오면 어떻게 되나요?

답변:

> `db_node`가 `mission_pool`에서 `pending` 미션을 시간 순서로 정렬하고 하나씩 실행합니다. 현재 미션이 `done` 또는 `failed`가 되어야 다음 미션을 시작합니다.

### Q3. 로봇이 미션 중 멈추면 어떻게 아나요?

답변:

> `db_node`가 1Hz로 `mission_status` heartbeat를 씁니다. 또한 action별 timeout을 두고, timeout이 지나면 실패 처리 후 다음 미션으로 넘어갈 수 있게 설계되어 있습니다.

### Q4. robot3와 robot6를 왜 나눴나요?

답변:

> 역할이 다르기 때문입니다. robot3는 병실 순찰과 환자 확인 중심이고, robot6는 투약과 간호사 추종, 약품 검증 중심입니다. namespace를 나누면 같은 node 구조를 재사용하면서 토픽 충돌 없이 독립 운용할 수 있습니다.

### Q5. Nav2와 mission_manager의 역할 차이는 무엇인가요?

답변:

> Nav2는 목표 좌표까지 경로를 계획하고 로컬 제어를 수행하는 이동 엔진입니다. mission_manager는 언제 undock할지, 어떤 mode를 켤지, Nav2를 언제 호출할지, 완료 후 dock할지를 결정하는 workflow 관리자입니다.

### Q6. 환자 확인은 어떤 데이터로 하나요?

답변:

> 병실 도착 후 QR을 읽어 patient_id를 얻고, `GetPrescription` 서비스를 통해 DB에서 해당 환자의 방을 조회합니다. 방문한 room_id와 DB의 room이 같으면 `identified`, 다르면 `mismatch`, 시간 안에 QR을 못 읽으면 `absent`로 처리합니다.

### Q7. 약품 검증은 어떻게 하나요?

답변:

> 설계상으로는 환자 확인 후 처방 목록을 가져오고, 약품을 순차 스캔해서 `MedicineMatcher`가 처방 순서와 약품명을 비교합니다. 모두 일치하면 전달 완료를 발행하고, 하나라도 다르면 mismatch로 경고/보류합니다.

### Q8. 왜 `mission_request`와 `mission_feedback`이 String JSON인가요?

답변:

> 미션 명령은 `{id, action, params, mode}`처럼 action마다 payload가 달라질 수 있습니다. String JSON을 쓰면 새로운 미션 타입을 추가할 때 custom msg를 매번 바꾸지 않아도 됩니다. 대신 내부에서 parsing과 schema validation을 잘 해야 합니다.

### Q9. 안전 제어는 어디에 있나요?

답변:

> map 이동은 Nav2 costmap과 controller가 처리하고, robot6의 reactive 추종은 mission_manager의 safety gate가 전진 속도를 제한합니다. 정면 LiDAR 여유가 0.30m보다 작으면 전진속도를 0으로 만들어 충돌 위험을 줄입니다.

### Q10. DB가 끊기면 어떻게 되나요?

답변:

> DB 연결이 끊기면 웹 미션 수신과 상태 기록이 제한됩니다. 다만 로봇 내부 ROS 미션이 이미 시작된 경우에는 내부 node들이 계속 진행할 수 있습니다. 발표에서는 RTDB가 command/status layer의 단일 의존점이므로 네트워크 복구, retry, local cache를 개선 포인트로 말하면 좋습니다.

### Q11. 현재 구현과 설계가 모두 완전히 같은가요?

답변:

> 큰 구조는 일치합니다. `db_node`, `mission_manager`, `patrol_mode`, `patient_identifier`, `rooms_server`, `prescription_server`, `nurse_tracker`는 설계 흐름과 대응됩니다. 다만 약품 검증 쪽은 PDF의 상세 설계가 코드보다 앞서 있으며, 현재는 scanner/OCR/처방 medicines 스키마 연결을 확장하는 단계입니다.

## 11. 발표에서 강조할 설계 이유

### 11.1 웹과 ROS 분리

웹은 RTDB에만 쓴다. ROS 명령 변환은 로봇 PC에서 한다.

장점:

- ROS discovery와 웹 배포를 분리할 수 있다.
- 보안 경계가 명확하다.
- DB 로그로 미션 추적이 쉽다.

### 11.2 namespace 분리

모든 토픽과 서비스에 `/robot3`, `/robot6` namespace가 붙는다.

장점:

- 같은 노드 구조를 두 로봇에 재사용할 수 있다.
- 토픽 충돌을 막는다.
- 웹에서 `{ns}`만 바꿔 다른 로봇에 명령할 수 있다.

### 11.3 mission_manager 중심 orchestration

이동, 도킹, mode, 인식을 mission_manager가 순서대로 엮는다.

장점:

- workflow가 한 곳에서 보인다.
- 실패 복구 정책을 넣기 쉽다.
- 모드 간 우선순위와 안전 게이트를 통합할 수 있다.

### 11.4 Nav2와 reactive control 분리

고정 goal 이동은 Nav2, 사람 추종은 tracker reactive control로 나눈다.

장점:

- map 기반 주행과 동적 대상 추종을 각각 맞는 방식으로 처리한다.
- reactive cmd_vel도 mission_manager safety gate를 통과시킬 수 있다.

### 11.5 DB service 분리

`rooms_server`, `prescription_server`, `display_bridge`를 따로 둔다.

장점:

- 환자/방/처방 조회 로직을 여러 노드가 재사용할 수 있다.
- 인식 노드가 Firebase SDK를 직접 들고 있지 않아도 된다.
- DB 스키마 변경 영향이 bridge 쪽으로 모인다.

## 12. 약점 또는 개선 질문이 들어오면 말할 내용

| 질문 포인트 | 솔직한 답변 방향 |
| --- | --- |
| RTDB 단일 장애점 | command/status layer 의존점이다. retry, offline queue, watchdog 보강 가능 |
| String JSON topic | 확장성은 좋지만 schema 검증이 약하다. Pydantic 또는 custom msg로 강화 가능 |
| 처방 medicines 빈 배열 | 현재 환자 조회 기반은 있고, 구조화 처방 스키마와 OCR 연동이 다음 단계 |
| waypoint 좌표 | DB rooms를 목표로 설계했지만, 실좌표 보정 전에는 config waypoint를 쓸 수 있다 |
| 보안 | 웹은 backend를 통해 Firebase admin으로 쓰고, 로봇 credential은 PC 환경변수로 분리해야 한다 |
| 실시간성 | RTDB/polling은 hard real-time이 아니다. 로봇 제어 loop는 ROS 내부에서 처리하고, DB는 명령/상태 계층으로만 쓴다 |

## 13. 1분 설명 대본

> MediCart는 웹, DB, 로봇 ROS 시스템을 분리한 구조입니다.
>
> 사용자가 웹에서 순찰 시작이나 투약 시작을 누르면 FastAPI backend가 Firebase RTDB의 `{ns}/mission_pool`에 pending 미션을 생성합니다.
>
> 각 로봇 PC의 `db_node`는 자기 namespace의 mission_pool을 listen하다가, 미션을 하나씩 `/robot3/mission_request` 또는 `/robot6/mission_request`로 발행합니다.
>
> 이후 `mission_manager_node`가 실제 workflow를 담당합니다. robot3는 undock 후 병상 waypoint를 돌고, 도착할 때마다 QR 기반 환자 확인을 수행한 뒤 dock합니다. robot6는 투약/round 모드에서 약품실 이동, 간호사 추종, 환자 확인과 약품 검증 흐름을 수행합니다.
>
> 실제 이동은 Nav2 `NavigateToPose` action이 담당하고, 도킹과 언도킹은 Create3 action이 담당합니다. LiDAR `/scan`은 AMCL과 costmap에 들어가 위치 추정과 장애물 회피에 쓰입니다.
>
> 미션이 끝나면 `/mission_feedback`이 `db_node`로 돌아가고, `db_node`가 `mission_log`와 `mission_status`에 기록합니다. 웹은 이 상태를 polling해서 버튼과 화면 상태를 갱신합니다.
>
> 핵심 설계 이유는 웹과 ROS를 직접 붙이지 않고 RTDB를 명령 큐로 둬서, 두 로봇을 namespace별로 독립 운용하고, 미션 기록과 상태 확인을 안정적으로 남기는 것입니다.

## 14. 10초 설명 대본

> 웹은 Firebase에 미션을 넣고, 로봇 PC의 `db_node`가 그것을 ROS 명령으로 바꿉니다. `mission_manager`가 Nav2, Create3, 인식 노드를 순서대로 제어하고, 결과는 다시 Firebase에 기록되어 웹에서 상태를 확인하는 구조입니다.
