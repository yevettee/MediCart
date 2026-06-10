# MediCart 전체 시스템 아키텍처 설명 대본

이 문서는 MediCart 전체 시스템을 강사님께 설명하기 위한 발표 대본이다. 설명 대상은 ROS2, DB, 로봇 노드의 세부 연결을 물어볼 수 있는 강사님이지만, 말의 순서는 초등학생도 따라올 수 있게 아주 쉬운 이야기에서 시작한다.

핵심 목표는 하나다.

```text
"두 대의 로봇이 병원 안에서 각자 맡은 일을 하고,
운영 화면과 DB가 그 일을 연결해 주는 구조입니다."
```

## 0. 발표 시작 멘트

발표자는 이렇게 시작하면 된다.

> 저희 MediCart 시스템은 병원에서 두 대의 AMR 로봇을 역할별로 나누어 운영하는 구조입니다.
>
> `/robot3`는 환자 순회 로봇입니다. 병실을 돌면서 환자가 있는지 보고, QR로 환자가 맞는지 확인하고, 문진이나 방문 결과를 DB에 남기는 역할입니다.
>
> `/robot6`는 투약 로봇입니다. 약품실로 이동하고, 환자 병실로 이동하고, 약 라벨을 OCR로 읽어서 처방과 맞는지 검증하는 역할입니다.
>
> 그리고 이 두 로봇을 사람이 조작하고 상태를 볼 수 있게 `dashboard_node`가 있고, Firebase Realtime Database와 ROS2 사이를 이어 주는 `db_node`가 있습니다.
>
> 전체 시스템을 아주 단순하게 말하면, dashboard는 사람의 버튼, mission_manager는 로봇의 두뇌, Nav2와 Create3는 로봇의 다리, identifier와 scanner/OCR은 로봇의 눈, db_node와 RTDB는 병원 기록장입니다.

## 1. 정말 쉬운 비유로 보는 전체 구조

먼저 로봇 시스템을 학교 심부름으로 비유한다.

| 실제 구성 | 쉬운 비유 | 하는 일 |
| --- | --- | --- |
| `dashboard_node` | 선생님 책상 | 사람이 버튼을 누르고 상태를 본다 |
| `/robot3/mission_manager_node` | 환자 순회 반장 | 어느 병실로 갈지 정하고 순서를 진행한다 |
| `/robot6/mission_manager_node` | 투약 반장 | 약품실, 환자 병실, 복귀 순서를 진행한다 |
| `Nav2` | 길찾기 담당 | 목표 좌표까지 로봇을 이동시킨다 |
| `Create3 Dock/Undock` | 출발/충전 담당 | 도킹 해제와 도킹을 담당한다 |
| `identifier_node` | 환자 확인 담당 | 사람을 찾고 QR을 읽고 환자가 맞는지 확인한다 |
| `scanner_node` | 약 검사 담당 | OCR 결과를 받아 처방과 맞는지 확인한다 |
| `ocr_node` | 글자 읽기 담당 | 약 라벨 사진에서 글자를 읽는다 |
| `db_node` | 기록 담당 | ROS2 요청을 Firebase RTDB 읽기/쓰기로 바꾼다 |
| Firebase RTDB | 병원 기록장 | 환자, 병실, 처방, 방문 결과, 투약 결과를 저장한다 |

발표자는 이렇게 말하면 된다.

> 전체 시스템은 한 명이 모든 일을 하는 구조가 아닙니다. 역할이 작게 나뉘어 있습니다.
>
> dashboard는 사람과 대화하고, mission_manager는 로봇의 미션 순서를 정합니다.
>
> 실제 이동은 Nav2 action으로 하고, 충전 스테이션에서 나가고 들어오는 것은 Create3 dock/undock action으로 합니다.
>
> 환자 확인은 identifier_node가 하고, 약 확인은 scanner_node와 ocr_node가 합니다.
>
> DB는 로봇이 직접 만지지 않고, db_node라는 중간 담당자를 통해서만 읽고 쓰는 구조를 목표로 합니다.

## 2. 전체 시스템을 한 줄로 설명

```text
Dashboard 버튼
  -> MissionManager가 미션 시작
  -> Nav2/Create3가 이동과 도킹 수행
  -> Identifier 또는 Scanner/OCR가 현장 확인
  -> DbNode가 Firebase RTDB에서 환자/처방을 읽고 결과를 저장
  -> Dashboard가 상태와 알림을 표시
```

조금 더 구체적으로 말하면 다음과 같다.

```text
사람이 dashboard에서 시작 버튼을 누른다.
mission_manager가 "이제 출발하자"라고 상태를 바꾼다.
로봇이 undock action으로 충전기에서 나온다.
Nav2 action으로 목표 위치까지 이동한다.
도착하면 카메라 노드가 환자나 약을 확인한다.
필요한 환자 정보와 처방 정보는 db_node가 RTDB에서 읽어 온다.
결과는 topic, service response, DB 기록으로 다시 dashboard와 시스템에 돌아온다.
```

## 3. 시스템의 큰 덩어리

MediCart는 크게 네 덩어리로 설명할 수 있다.

| 덩어리 | 구성 | 역할 |
| --- | --- | --- |
| 운영자 영역 | `dashboard_node`, Web UI | 사람이 버튼을 누르고 로봇 상태를 확인 |
| 로봇 실행 영역 | `/robot3`, `/robot6`, Nav2, Create3 | 로봇이 실제로 이동하고 도킹 |
| 인식 영역 | `identifier_node`, `scanner_node`, `ocr_node`, `obstacle_node` | 환자, QR, 약 라벨, 장애물 인식 |
| 데이터 영역 | `db_node`, Firebase RTDB, Interview Web App | 환자 정보, 병실 좌표, 처방, 방문/투약 기록 저장 |

발표자는 이렇게 설명한다.

> 시스템을 한 번에 보면 복잡하지만, 사실 네 구역으로 나누면 쉽습니다.
>
> 첫 번째는 운영자 영역입니다. 사람이 보는 화면입니다.
>
> 두 번째는 로봇 실행 영역입니다. 실제 이동과 도킹을 합니다.
>
> 세 번째는 인식 영역입니다. 카메라를 보고 환자, QR, 약 라벨을 확인합니다.
>
> 네 번째는 데이터 영역입니다. Firebase RTDB에 환자 정보, 방 좌표, 처방, 결과 기록을 저장하고 조회합니다.

## 4. ROS2 통신 방식 세 가지

이 시스템은 ROS2에서 세 가지 방식으로 노드끼리 대화한다.

| 방식 | 쉽게 말하면 | 이 시스템 예시 |
| --- | --- | --- |
| Topic | 계속 방송하는 라디오 | `/robot3/patient_identified`, `/robot6/robot_state`, `/robot6/amcl_pose` |
| Service | 물어보면 답하는 전화 | `/medicart/db/get_prescription`, `/robot6/scan_medicine` |
| Action | 오래 걸리는 일을 맡기는 주문서 | `/robot6/navigate_to_pose`, `/robot6/dock`, `/robot6/undock` |

발표자는 이렇게 말한다.

> Topic은 계속 흘러가는 정보입니다. 예를 들어 로봇 위치나 환자 식별 결과처럼 여러 노드가 계속 받아볼 수 있는 정보입니다.
>
> Service는 질문과 답변입니다. 예를 들어 "이 환자의 처방을 주세요"라고 요청하면 DB가 한 번 응답합니다.
>
> Action은 시간이 걸리는 일입니다. 예를 들어 "약품실까지 이동해 주세요"는 몇 초 이상 걸리기 때문에 action으로 보내고, 중간 피드백과 최종 결과를 받습니다.

## 5. 현재 repo의 패키지별 역할

현재 워크스페이스에는 아래 ROS2 패키지들이 있다.

| Package | 핵심 노드/파일 | 담당 역할 | 현재 상태 |
| --- | --- | --- | --- |
| `dashboard` | `dashboard_node.py`, `gui_panel.py` | Web UI, robot6 수동 이동/도킹/카메라 표시 | 가장 많이 구현됨 |
| `mission_manager` | `mission_manager_node.py`, `state_machine.py`, `prescription_session.py` | 미션 상태기와 순서 제어 | 뼈대 중심, service/action 추가 필요 |
| `patient_identifier` | `identifier_node.py`, `patient_validator.py`, `person_detector.py`, `qr_scanner.py` | 환자 존재 감지, QR 읽기, DB 검증 | 흐름은 있음, `/robot6` 하드코딩 수정 필요 |
| `db_bridge` | `db_node.py`, `firebase_client.py`, `models.py` | RTDB와 ROS2 service 사이 bridge | placeholder, 실제 RTDB 구현 필요 |
| `scanner` | `scanner_node.py`, `medicine_matcher.py` | 약 스캔 검증 흐름 | placeholder 중심 |
| `ocr_detector` | `ocr_node.py`, `ocr_engine.py`, `text_cleaner.py` | 약 라벨 OCR | placeholder 중심 |
| `obstacle_detector` | `obstacle_node.py`, `height_filter.py` | 장애물 point cloud 생성 | placeholder 중심 |
| `nurse_tracker` | `tracker_node.py` 등 | 간호사 추적 | 현재 범위 밖, 추후 기능 |
| `medi_interfaces` | `msg/*.msg`, `srv/*.srv` | custom message/service 정의 | 필요한 인터페이스 대부분 있음 |
| `simulation` | simulation package | 테스트/시뮬레이션 | 별도 확인 필요 |

발표자는 이렇게 말한다.

> 현재 repo에는 큰 기능별 패키지는 이미 나누어져 있습니다.
>
> 다만 "패키지가 있다"와 "end-to-end로 완성되어 있다"는 다릅니다.
>
> 현재 가장 실제 동작에 가까운 것은 dashboard의 robot6 수동 주행/도킹/카메라 화면입니다.
>
> 환자 순회와 투약 검증은 인터페이스와 노드 뼈대는 있지만, mission_manager, db_bridge, scanner, ocr_detector 쪽에 실제 service/action 연결이 더 필요합니다.

## 6. 전체 실행 위치

목표 구조에서는 노드들이 아래처럼 나뉘어 실행된다.

| 실행 위치 | 노드 | 설명 |
| --- | --- | --- |
| Host PC | `dashboard_node` | 운영자가 보는 웹 대시보드 |
| Host PC | `/medicart/db_node` | RTDB와 ROS2를 이어 주는 공용 DB bridge |
| Host PC | Fast DDS Discovery Server | 서로 다른 PC/로봇의 ROS2 노드가 서로 찾게 해 줌 |
| `/robot3` | `mission_manager_node` | 환자 순회 미션 상태기 |
| `/robot3` | `identifier_node` | 환자 존재/QR 확인 |
| `/robot3` | `obstacle_node` | 장애물 정보 생성 |
| `/robot3` | Nav2, Create3 | 이동과 도킹 |
| `/robot6` | `mission_manager_node` | 투약 미션 상태기 |
| `/robot6` | `scanner_node`, `ocr_node` | 약 라벨 OCR과 처방 검증 |
| `/robot6` | `obstacle_node` | 장애물 정보 생성 |
| `/robot6` | Nav2, Create3 | 이동과 도킹 |

발표자는 이렇게 말한다.

> Host PC에는 사람이 보는 dashboard와 DB bridge가 올라갑니다.
>
> `/robot3`에는 환자 순회를 위한 mission_manager와 identifier가 올라갑니다.
>
> `/robot6`에는 투약 미션을 위한 mission_manager, scanner, OCR 노드가 올라갑니다.
>
> 두 로봇 모두 실제 이동은 Nav2가 담당하고, 충전기에서 나오는 것과 들어가는 것은 Create3 dock/undock action이 담당합니다.

## 7. DashboardNode 설명

### 7.1 쉬운 설명

`dashboard_node`는 사람이 누르는 버튼과 로봇 세계를 이어 주는 창구다.

발표자는 이렇게 말한다.

> dashboard_node는 운영자가 보는 화면입니다.
>
> 운영자는 여기서 지도 위 목표를 클릭하거나, dock/undock 버튼을 누르거나, 환자 순회 시작 버튼을 누릅니다.
>
> dashboard_node는 이 버튼을 ROS2 action이나 service 호출로 바꿔서 로봇에게 전달합니다.

### 7.2 실제 코드에서 시작되는 곳

| 코드 | 역할 |
| --- | --- |
| `dashboard.dashboard_node:main` | `rclpy.init()` 후 `DashboardNode` 생성 |
| `DashboardNode.__init__()` | HTTP server, action client, topic subscription, service client 생성 |
| `DashboardRequestHandler.do_GET()` | Web UI와 상태 API 제공 |
| `DashboardRequestHandler.do_POST()` | 버튼 요청을 받아 ROS 동작으로 연결 |

대본:

> dashboard 패키지는 `setup.py`의 console script인 `dashboard_node`로 실행됩니다.
>
> 실행되면 `dashboard.dashboard_node:main`이 호출되고, 여기서 `DashboardNode` 객체가 만들어집니다.
>
> `DashboardNode.__init__()` 안에서 웹 서버를 열고, Nav2 action client, dock/undock action client, 카메라 topic subscription, pose subscription, start_patrol service client를 만듭니다.

### 7.3 Dashboard가 만드는 주요 연결

| 코드 위치 | 만드는 것 | 타입 | 상대 |
| --- | --- | --- | --- |
| `ActionClient(self, NavigateToPose, action_name)` | `/robot6/navigate_to_pose` | Action client | Nav2 |
| `ActionClient(self, Dock, dock_action_name)` | `/robot6/dock` | Action client | Create3 |
| `ActionClient(self, Undock, undock_action_name)` | `/robot6/undock` | Action client | Create3 |
| `create_subscription(DockStatus, dock_status_topic, _handle_dock_status)` | `/robot6/dock_status` | Topic sub | Create3 |
| `create_subscription(PoseWithCovarianceStamped, pose_topic, _handle_pose)` | `/robot6/amcl_pose` | Topic sub | AMCL |
| `create_subscription(CompressedImage, rgb_topic, _handle_rgb_frame)` | `/robot6/oakd/rgb/image_raw/compressed` | Topic sub | OAK-D |
| `create_subscription(CompressedImage, depth_topic, _handle_depth_frame)` | `/robot6/oakd/stereo/image_raw/compressedDepth` | Topic sub | OAK-D |
| `create_client(StartPatrol, START_PATROL_SERVICE)` | `/robot6/start_patrol` 현재 코드 | Service client | mission_manager |
| `create_subscription(PatientIdentified, IDENTIFIED_TOPIC, _on_identified)` | `/robot6/patient_identified` 현재 코드 | Topic sub | identifier_node |

주의할 점:

```text
현재 dashboard 코드는 robot6 중심이다.
목표 아키텍처에서는 robot3 환자 순회와 robot6 투약 미션을 분리해야 한다.
```

### 7.4 Dashboard에서 지도 클릭 시 흐름

지도에서 목표를 클릭하면 이런 순서로 흘러간다.

```text
브라우저 지도 클릭
  -> HTTP POST /api/goals
  -> DashboardRequestHandler.do_POST()
  -> DashboardNode.send_navigation_goal()
  -> DashboardNode._send_navigation_only()
  -> ActionClient sends NavigateToPose goal
  -> /robot6/navigate_to_pose Nav2 action server
  -> feedback는 _handle_feedback()
  -> 최종 결과는 _handle_result()
  -> dashboard log로 표시
```

발표 멘트:

> 예를 들어 운영자가 지도에서 약품실을 클릭했다고 하겠습니다.
>
> 브라우저는 `/api/goals`로 HTTP 요청을 보냅니다.
>
> Python 웹 서버의 `DashboardRequestHandler.do_POST()`가 이 요청을 받고, `DashboardNode.send_navigation_goal()`을 호출합니다.
>
> `send_navigation_goal()`은 입력된 x, y, yaw를 `NavigationTarget`으로 바꾼 다음, 로봇이 dock 상태면 먼저 undock을 시도하고, 아니면 바로 `_send_navigation_only()`로 Nav2 action goal을 보냅니다.
>
> 이때 실제 ROS2 action 이름은 보통 `/robot6/navigate_to_pose`입니다.
>
> 이동 중 남은 거리 같은 feedback은 `_handle_feedback()`에서 받고, 성공/실패 최종 결과는 `_handle_result()`에서 받아 dashboard 로그로 보여줍니다.

### 7.5 Dashboard에서 Dock/Undock 버튼 시 흐름

```text
브라우저 Dock 버튼
  -> HTTP POST /api/commands {"command": "dock"}
  -> DashboardNode.run_operator_command()
  -> DashboardNode._send_dock()
  -> /robot6/dock action
  -> _handle_dock_feedback()
  -> _handle_dock_result()

브라우저 Undock 버튼
  -> HTTP POST /api/commands {"command": "undock"}
  -> DashboardNode.run_operator_command()
  -> DashboardNode._send_undock_only()
  -> /robot6/undock action
  -> _handle_manual_undock_response()
  -> _handle_manual_undock_result()
```

발표 멘트:

> dock과 undock도 service가 아니라 action입니다.
>
> 이유는 도킹도 시간이 걸리는 작업이기 때문입니다.
>
> dashboard는 `/robot6/dock` 또는 `/robot6/undock` action server에게 목표를 보내고, 진행 중인지, 성공했는지, 실패했는지를 callback으로 받습니다.

## 8. MissionManagerNode 설명

### 8.1 쉬운 설명

`mission_manager_node`는 로봇 미션의 두뇌다.

발표자는 이렇게 말한다.

> mission_manager는 로봇이 지금 무엇을 해야 하는지 순서를 관리하는 노드입니다.
>
> 예를 들어 환자 순회에서는 출발, 이동, 환자 확인, 문진, 다음 방 이동, 복귀, 도킹 순서가 있습니다.
>
> 투약 미션에서는 출발, 약품실 이동, 약 적재, 환자 방 이동, 약 스캔, 복귀, 도킹 순서가 있습니다.

### 8.2 현재 코드에서 실제로 있는 부분

| 코드 | 현재 역할 |
| --- | --- |
| `mission_manager.mission_manager_node:main` | `MissionManagerNode` 생성 |
| `MissionManagerNode.__init__()` | `mission_type` parameter 선언, `StateMachine` 생성, `/robot6/start_patrol` service server 생성 |
| `_on_start_patrol()` | patrol 미션 시작 요청을 받으면 상태를 `IDLE -> UNDOCK`으로 전환 |
| `StateMachine.transition()` | 현재 state에서 다음 state로 넘어갈 수 있는지 확인하고 변경 |

현재 구현된 service:

| Service name | Type | Server callback |
| --- | --- | --- |
| `/robot6/start_patrol` | `StartPatrol` | `_on_start_patrol()` |

주의:

```text
목표 문서에서는 robot3가 환자 순회이므로 /robot3/start_patrol이 맞다.
하지만 현재 코드에는 /robot6/start_patrol로 하드코딩되어 있다.
```

### 8.3 목표로 필요한 MissionManager 연결

환자 순회용 `/robot3/mission_manager_node`가 만들어야 할 것:

| Interface | 타입 | 방향 | 받는 쪽/주는 쪽 |
| --- | --- | --- | --- |
| `/robot3/start_patrol` | `StartPatrol` service | server | dashboard가 호출 |
| `/robot3/move_home` | `MoveHome` service | server | dashboard가 호출 |
| `/robot3/patient_identified` | `PatientIdentified` topic | subscribe | identifier_node가 발행 |
| `/robot3/robot_state` | `RobotState` topic | publish | dashboard가 구독 |
| `/robot3/navigate_to_pose` | `NavigateToPose` action | client | Nav2 server |
| `/robot3/undock` | `Undock` action | client | Create3 server |
| `/robot3/dock` | `Dock` action | client | Create3 server |
| `/medicart/db/update_visit_status` | `UpdateVisitStatus` service | client | db_node server |

투약용 `/robot6/mission_manager_node`가 만들어야 할 것:

| Interface | 타입 | 방향 | 받는 쪽/주는 쪽 |
| --- | --- | --- | --- |
| `/robot6/start_medication` | `StartMedication` service | server | dashboard가 호출 |
| `/robot6/scan_patient` | `ScanPatient` service | server | dashboard가 호출 |
| `/robot6/scan_medicine` | `ScanMedicine` service | server | dashboard가 호출 |
| `/robot6/robot_state` | `RobotState` topic | publish | dashboard가 구독 |
| `/robot6/navigate_to_pose` | `NavigateToPose` action | client | Nav2 server |
| `/robot6/undock` | `Undock` action | client | Create3 server |
| `/robot6/dock` | `Dock` action | client | Create3 server |
| `/medicart/db/get_prescription` | `GetPrescription` service | client | db_node server |
| `/robot6/scanner/verify_medicine` | `VerifyMedicine` service | client | scanner_node server |

### 8.4 StateMachine 설명

`StateMachine`은 로봇의 현재 상태를 관리한다.

현재 코드에는 두 가지 flow가 있다.

환자 순회 flow:

```text
IDLE -> UNDOCK -> PATROL -> IDENTIFY -> INTERVIEW -> NEXT_ROOM
NEXT_ROOM -> PATROL 또는 RETURN
RETURN -> DOCK -> IDLE
```

투약 flow:

```text
IDLE -> UNDOCK -> MOVE 또는 FOLLOW -> SCAN -> RETURN -> DOCK -> IDLE
```

발표 멘트:

> StateMachine은 로봇의 체크리스트입니다.
>
> 지금 상태가 `IDLE`이면 다음은 `UNDOCK`만 가능합니다.
>
> `UNDOCK`이 끝나면 환자 순회는 `PATROL`로 가고, 투약은 `MOVE`나 `FOLLOW`로 갑니다.
>
> 이렇게 하면 로봇이 갑자기 순서를 건너뛰지 못하게 막을 수 있습니다.

강사님 질문 대비:

```text
Q. 왜 state machine이 필요한가?
A. 미션이 여러 단계라서 순서 보장이 필요합니다. 예를 들어 도킹 상태에서 바로 SCAN으로 가면 안 되고, 먼저 undock과 이동이 끝나야 합니다.
```

## 9. Patient Identifier 설명

### 9.1 쉬운 설명

`identifier_node`는 환자 순회 로봇의 눈이다.

발표자는 이렇게 말한다.

> identifier_node는 병실에 도착했을 때 환자가 있는지 보고, QR을 읽어서 그 환자가 맞는지 확인합니다.
>
> 사람이 없으면 absent, QR을 못 읽으면 no_qr, QR 환자와 DB 병실이 다르면 mismatch, 맞으면 identified를 발행합니다.

### 9.2 실제 코드 구성

| 파일 | 함수/클래스 | 역할 |
| --- | --- | --- |
| `identifier_node.py` | `IdentifierNode.__init__()` | 카메라 topic subscribe, 결과 topic publisher, timer 생성 |
| `identifier_node.py` | `_on_image()` | 최신 RGB 이미지 저장 |
| `identifier_node.py` | `_on_depth()` | 최신 depth 이미지 저장 |
| `identifier_node.py` | `_run_pipeline()` | 사람 감지 -> QR 읽기 -> DB 검증 -> 결과 발행 |
| `identifier_node.py` | `_publish()` | `PatientIdentified` message 발행 |
| `person_detector.py` | `PersonDetector.detect()` | YOLO로 사람 존재 여부 판단 |
| `qr_scanner.py` | `QrScanner.scan()` | QR payload에서 `patient_id`, `room` 읽기 |
| `patient_validator.py` | `PatientValidator.validate()` | DB service로 환자 정보와 방 검증 |

### 9.3 Identifier가 쓰는 통신

현재 코드 기준:

| Interface | 타입 | 방향 | 설명 |
| --- | --- | --- | --- |
| `/robot6/oakd/image_raw` | `sensor_msgs/msg/Image` | sub | 현재 RGB 이미지 입력 |
| `/robot6/oakd/depth_image` | `sensor_msgs/msg/Image` | sub | 현재 depth 이미지 입력 |
| `/robot6/patient_identified` | `PatientIdentified` | pub | 환자 식별 결과 |
| `/robot6/db/get_prescription` | `GetPrescription` | service client | DB에서 환자 정보 조회 |

목표 구조에서는 이렇게 바뀌어야 한다.

| Interface | 타입 | 방향 | 설명 |
| --- | --- | --- | --- |
| `/robot3/oakd/image_raw` | `sensor_msgs/msg/Image` | sub | robot3 카메라 |
| `/robot3/oakd/depth_image` | `sensor_msgs/msg/Image` | sub | robot3 depth |
| `/robot3/patient_identified` | `PatientIdentified` | pub | robot3 환자 순회 결과 |
| `/medicart/db/get_prescription` | `GetPrescription` | service client | 공용 db_node 조회 |

### 9.4 환자 확인 흐름

```text
robot3가 병실 앞 도착
  -> identifier_node가 최신 camera frame 확인
  -> PersonDetector.detect(frame)
  -> 사람이 없으면 status=absent 발행
  -> 사람이 있으면 QrScanner.scan()
  -> QR이 없으면 status=no_qr 발행
  -> QR에서 patient_id, room 읽음
  -> PatientValidator.validate(patient_id, current_room)
  -> db_node에 GetPrescription service 요청
  -> DB의 환자 room과 현재 room 비교
  -> 맞으면 status=identified 발행
  -> 다르면 status=mismatch 발행
```

발표 멘트:

> 환자 확인은 세 단계입니다.
>
> 첫째, 사람이 있는지 봅니다.
>
> 둘째, 사람이 있으면 QR을 읽습니다.
>
> 셋째, QR에 있는 환자 ID를 DB에 물어보고 현재 방과 맞는지 확인합니다.
>
> 결과는 `/robot3/patient_identified` topic으로 mission_manager와 dashboard가 같이 받을 수 있습니다.

## 10. DbNode와 Firebase RTDB 설명

### 10.1 쉬운 설명

`db_node`는 ROS2 세계와 Firebase RTDB 세계 사이의 통역사다.

발표자는 이렇게 말한다.

> 로봇 노드가 Firebase URL을 직접 알 필요는 없습니다.
>
> 로봇 노드는 `GetPrescription` 같은 ROS2 service만 호출합니다.
>
> 그러면 db_node가 Firebase RTDB에서 필요한 JSON을 읽고, ROS message 형태로 바꿔서 응답합니다.
>
> 반대로 방문 결과나 투약 결과도 로봇 노드가 DB에 직접 쓰지 않고, db_node service를 호출해서 기록합니다.

### 10.2 현재 RTDB 최상위 구조

현재 확인한 RTDB root:

```text
/patients
/rooms
/robot3
/robot6
/ocr
```

| 경로 | 현재 의미 |
| --- | --- |
| `/patients` | 환자 기본정보, 문진, 바이탈, 방문 기록 |
| `/rooms` | 병실/약품실/home 좌표와 일부 환자 배정 |
| `/robot3` | robot3 상태 요약 |
| `/robot6` | robot6 상태 요약과 일부 mission log |
| `/ocr` | 마지막 OCR 텍스트 |

### 10.3 목표 service 계약

`db_node`가 제공해야 할 service:

| Service | Request | Response | RTDB 동작 |
| --- | --- | --- | --- |
| `/medicart/db/get_prescription` | `patient_id` | `PatientInfo`, `MedicineInfo[]` | `/patients`, `/rooms`, `/prescriptions` read |
| `/medicart/db/verify_medicine` | `patient_id`, `step_index`, `scanned_text` | expected/scanned/match | `/prescriptions` read, `/medicine_scan_logs` write |
| `/medicart/db/update_visit_status` | `patient_id`, `room`, `status`, `session_id` | success/message | `/robot_visits`, `/patients/{id}/visits` write |

현재 코드 상태:

| 파일 | 현재 내용 |
| --- | --- |
| `db_node.py` | `DbNode` 생성 후 시작 로그만 출력 |
| `firebase_client.py` | `get_prescription()`, `verify_medicine_at_step()`, `update_visit_status()` placeholder |
| `models.py` | `Patient`, `Medicine` 간단 model |

발표 멘트:

> 현재 db_bridge 패키지는 구조는 있지만 실제 Firebase RTDB 연결은 아직 구현 전입니다.
>
> 그래서 목표 아키텍처에서는 이 부분을 가장 중요한 추가 구현 지점으로 보고 있습니다.

### 10.4 현재 DB에서 부족한 것

현재 DB에는 환자 기본정보와 방 좌표는 있지만, 투약 검증에 꼭 필요한 구조화된 처방 목록이 없다.

필요한 추가 경로:

```text
/patient_rooms/{patient_id}/room

/prescriptions/{patient_id}/current/medicines/{sequence_order}
  medicine_id
  name
  dosage
  expiry
  manufacturer
  sequence_order
  ocr_keywords

/robot_visits/{session_id}/{push_id}
  robot_id
  room
  patient_id
  status
  message
  ts

/medication_sessions/{session_id}
  robot_id
  patient_id
  room
  status
  current_step
  total_steps
  started_ts
  ended_ts

/medicine_scan_logs/{session_id}/{step_index}
  patient_id
  expected_medicine_id
  expected_name
  scanned_text
  match
  confidence
  ts
```

강사님 질문 대비:

```text
Q. 현재 DB만으로 투약 검증이 가능한가?
A. 완전하게는 어렵습니다. 현재 환자의 "현재 복용약물" 같은 문자열은 있지만, OCR로 순서대로 검증하려면 sequence_order가 있는 medicines 배열이 필요합니다.
```

## 11. ScannerNode와 OcrNode 설명

### 11.1 쉬운 설명

투약 검증은 두 사람이 나눠서 하는 일처럼 보면 된다.

```text
ocr_node: 약 봉투/라벨에서 글자를 읽는 담당
scanner_node: 읽은 글자가 처방의 현재 순서와 맞는지 확인하는 담당
```

발표자는 이렇게 말한다.

> 투약 로봇은 약을 환자에게 전달하기 전에 약이 맞는지 확인해야 합니다.
>
> ocr_node는 카메라 이미지를 보고 글자를 읽습니다.
>
> scanner_node는 ocr_node가 읽은 글자를 받아서 db_node에게 처방과 맞는지 물어봅니다.
>
> 최종적으로 match가 true이면 다음 약 단계로 넘어가고, false이면 dashboard에 불일치 알림을 보여줍니다.

### 11.2 목표 통신 구조

| 노드 | Interface | 타입 | 방향 |
| --- | --- | --- | --- |
| `ocr_node` | `/robot6/oakd/image_raw` 또는 `/robot6/webcam/image_raw` | Image topic | sub |
| `ocr_node` | `/robot6/ocr/get_result` | `GetOcrResult` service | server |
| `scanner_node` | `/robot6/ocr/get_result` | `GetOcrResult` service | client |
| `scanner_node` | `/robot6/scanner/verify_medicine` | `VerifyMedicine` service | server |
| `scanner_node` | `/medicart/db/verify_medicine` | `VerifyMedicine` service | client |
| `mission_manager` | `/robot6/scanner/verify_medicine` | `VerifyMedicine` service | client |

### 11.3 약 스캔 흐름

```text
dashboard에서 "약 스캔" 버튼
  -> /robot6/scan_medicine service 호출
  -> robot6 mission_manager가 scanner_node 호출
  -> /robot6/scanner/verify_medicine
  -> scanner_node가 ocr_node 호출
  -> /robot6/ocr/get_result
  -> ocr_node가 latest image에서 글자 읽음
  -> scanner_node가 db_node 호출
  -> /medicart/db/verify_medicine
  -> db_node가 /prescriptions/{patient_id}/current/medicines/{step} 읽음
  -> OCR text와 expected medicine 비교
  -> match true/false 응답
  -> mission_manager가 current_step 증가 또는 오류 처리
```

현재 코드 상태:

| 파일 | 현재 내용 |
| --- | --- |
| `ocr_node.py` | 노드 생성과 시작 로그만 있음 |
| `ocr_engine.py` | `recognize()` placeholder |
| `text_cleaner.py` | OCR text 정리 함수 |
| `scanner_node.py` | 노드 생성과 시작 로그만 있음 |
| `medicine_matcher.py` | OCR text와 expected medicine name 비교 로직 일부 |

발표 멘트:

> scanner와 OCR은 설계상 필요한 노드와 인터페이스가 정해져 있지만, 현재 repo에서는 아직 실제 service server/client 연결이 비어 있습니다.
>
> 그래서 구현 우선순위는 `ocr_node`가 `GetOcrResult` service server가 되고, `scanner_node`가 `VerifyMedicine` service server가 되는 것입니다.

## 12. Robot3 환자 순회 전체 흐름

### 12.1 초등학생 버전

```text
robot3가 충전기에서 나온다.
첫 번째 병실로 간다.
사람이 있는지 본다.
QR을 읽는다.
DB에 "이 환자가 이 방 환자 맞아?"라고 물어본다.
맞으면 방문 성공으로 기록한다.
틀리거나 없으면 문제 상황으로 기록한다.
다음 병실로 간다.
모든 병실을 돌면 home으로 돌아가고 dock한다.
```

### 12.2 발표 대본

> 이제 `/robot3` 환자 순회 흐름을 설명드리겠습니다.
>
> 운영자가 dashboard에서 환자 순회 시작 버튼을 누르면 `/robot3/start_patrol` service가 호출되는 것이 목표 구조입니다.
>
> 이 요청을 받은 `/robot3/mission_manager_node`는 state를 `IDLE`에서 `UNDOCK`으로 바꾸고, `/robot3/undock` action으로 충전기에서 나옵니다.
>
> 그 다음 DB의 `/rooms` 또는 waypoint 설정에서 순회할 병실 좌표를 가져오고, 각 병실마다 `/robot3/navigate_to_pose` action으로 이동합니다.
>
> 병실에 도착하면 `identifier_node`가 카메라 이미지로 사람이 있는지 확인하고 QR을 읽습니다.
>
> QR에서 나온 `patient_id`는 `/medicart/db/get_prescription` service로 db_node에 확인합니다.
>
> db_node는 RTDB의 `/patients`, `/rooms` 또는 `/patient_rooms`를 읽어서 환자 이름과 병실을 돌려줍니다.
>
> identifier_node는 그 결과를 `/robot3/patient_identified` topic으로 발행합니다.
>
> mission_manager와 dashboard가 이 topic을 같이 받을 수 있습니다.
>
> mission_manager는 결과에 따라 `/medicart/db/update_visit_status` service를 호출해서 identified, absent, mismatch, no_qr, db_error 같은 결과를 DB에 남깁니다.
>
> 모든 방을 돌면 `/robot3/navigate_to_pose`로 home에 복귀하고, `/robot3/dock` action으로 도킹합니다.

### 12.3 robot3 흐름을 통신 단위로 보기

| 순서 | 누가 | 무엇을 호출/발행 | 누가 받음 | 의미 |
| --- | --- | --- | --- | --- |
| 1 | dashboard | `/robot3/start_patrol` service | robot3 mission_manager | 순회 시작 |
| 2 | mission_manager | `/robot3/undock` action | Create3 | 충전기에서 나오기 |
| 3 | mission_manager | `/robot3/navigate_to_pose` action | Nav2 | 병실로 이동 |
| 4 | camera | `/robot3/oakd/image_raw` topic | identifier_node | 이미지 제공 |
| 5 | identifier_node | `/medicart/db/get_prescription` service | db_node | 환자/병실 검증 |
| 6 | identifier_node | `/robot3/patient_identified` topic | mission_manager, dashboard | 식별 결과 공유 |
| 7 | mission_manager | `/medicart/db/update_visit_status` service | db_node | 방문 결과 저장 |
| 8 | mission_manager | `/robot3/robot_state` topic | dashboard | 상태 표시 |
| 9 | mission_manager | `/robot3/dock` action | Create3 | 복귀 후 도킹 |

### 12.4 환자 식별 status 의미

| Status | 뜻 | 처리 |
| --- | --- | --- |
| `identified` | 환자가 있고 QR과 DB 병실이 맞음 | 방문 성공 기록 |
| `absent` | 사람이 감지되지 않음 | 부재 기록, 재방문 후보 |
| `no_qr` | 사람은 있지만 QR을 읽지 못함 | 알림 표시, 수동 확인 필요 |
| `mismatch` | QR 환자와 현재 방이 맞지 않음 | 알림 표시, DB/환자 확인 필요 |
| `db_error` | DB 조회 실패 | 시스템 오류 알림 |

## 13. Robot6 투약 전체 흐름

### 13.1 초등학생 버전

```text
robot6가 충전기에서 나온다.
약품실로 간다.
간호사가 약을 싣는다.
환자 병실로 간다.
약 라벨을 카메라로 본다.
글자를 OCR로 읽는다.
DB 처방과 맞는지 확인한다.
맞으면 다음 약으로 넘어간다.
모든 약이 맞으면 home으로 돌아가고 dock한다.
```

### 13.2 발표 대본

> `/robot6` 투약 로봇은 약품실과 환자 병실을 오가는 로봇입니다.
>
> 운영자가 dashboard에서 투약 미션을 시작하면 `/robot6/start_medication` service가 호출되는 것이 목표입니다.
>
> robot6 mission_manager는 먼저 `/robot6/undock` action으로 출발하고, `/robot6/navigate_to_pose` action으로 RTDB의 `/rooms/pharmacy` 좌표, 즉 약품실로 이동합니다.
>
> 약품실에서 약 적재가 끝나면 환자 병실 좌표로 이동합니다.
>
> 환자 병실에 도착하면 dashboard에서 `ScanPatient`를 호출해서 해당 환자의 처방 목록을 불러옵니다.
>
> 이때 mission_manager는 `/medicart/db/get_prescription` service로 db_node에게 환자 정보와 처방 목록을 요청합니다.
>
> db_node는 RTDB의 `/patients/{patient_id}`와 `/prescriptions/{patient_id}/current/medicines`를 읽고 `MedicineInfo[]` 배열로 돌려줍니다.
>
> 그 다음 약 하나하나를 검사할 때 dashboard가 `/robot6/scan_medicine` service를 호출합니다.
>
> mission_manager는 scanner_node의 `/robot6/scanner/verify_medicine` service를 호출합니다.
>
> scanner_node는 ocr_node의 `/robot6/ocr/get_result` service로 현재 약 라벨 OCR 결과를 받고, 다시 db_node의 `/medicart/db/verify_medicine` service로 처방과 맞는지 검증합니다.
>
> 맞으면 `PrescriptionSession.current_step`을 하나 증가시키고, 틀리면 dashboard에 오류를 보여줍니다.
>
> 모든 약 검증이 끝나면 home으로 돌아가고 dock합니다.

### 13.3 robot6 흐름을 통신 단위로 보기

| 순서 | 누가 | 무엇을 호출/발행 | 누가 받음 | 의미 |
| --- | --- | --- | --- | --- |
| 1 | dashboard | `/robot6/start_medication` service | robot6 mission_manager | 투약 미션 시작 |
| 2 | mission_manager | `/robot6/undock` action | Create3 | 충전기에서 나오기 |
| 3 | mission_manager | `/robot6/navigate_to_pose` action | Nav2 | 약품실 이동 |
| 4 | mission_manager | `/robot6/navigate_to_pose` action | Nav2 | 환자 병실 이동 |
| 5 | dashboard | `/robot6/scan_patient` service | mission_manager | 환자 처방 세션 시작 |
| 6 | mission_manager | `/medicart/db/get_prescription` service | db_node | 처방 목록 조회 |
| 7 | dashboard | `/robot6/scan_medicine` service | mission_manager | 현재 약 검증 요청 |
| 8 | mission_manager | `/robot6/scanner/verify_medicine` service | scanner_node | OCR 기반 검증 요청 |
| 9 | scanner_node | `/robot6/ocr/get_result` service | ocr_node | 글자 읽기 요청 |
| 10 | scanner_node | `/medicart/db/verify_medicine` service | db_node | 처방과 OCR 결과 비교 |
| 11 | db_node | `/medicine_scan_logs/...` write | Firebase RTDB | 검증 기록 저장 |
| 12 | mission_manager | `/robot6/robot_state` topic | dashboard | 상태 표시 |
| 13 | mission_manager | `/robot6/dock` action | Create3 | 복귀 후 도킹 |

### 13.4 PrescriptionSession 설명

`PrescriptionSession`은 현재 환자의 처방 검증 진행 상황을 기억한다.

| 함수 | 역할 |
| --- | --- |
| `start(patient_id, medicines)` | 환자와 약 목록으로 세션 시작 |
| `expected_medicine()` | 현재 step에서 기대하는 약 반환 |
| `advance_if_match(match)` | match가 true면 다음 step으로 이동 |
| `is_complete` | 모든 약 검증이 끝났는지 확인 |
| `clear()` | 세션 초기화 |

발표 멘트:

> 처방은 보통 약이 여러 개입니다.
>
> 그래서 robot6는 지금 몇 번째 약을 검사 중인지 기억해야 합니다.
>
> 이 역할을 `PrescriptionSession`이 합니다.
>
> 첫 번째 약이 맞으면 step이 1 증가하고, 다음 약을 기대합니다.

## 14. RTDB가 전체 흐름에서 하는 일

### 14.1 현재 DB에 있는 데이터

| RTDB path | 쓰임 |
| --- | --- |
| `/patients/{patient_id}/info` | 환자 이름, 등록번호, 진료과 등 |
| `/patients/{patient_id}/vitals` | 바이탈과 통증점수 |
| `/patients/{patient_id}/visits` | 문진/방문 기록 |
| `/rooms/{room_id}` | 병실, 약품실, home 좌표 |
| `/robot3/*` | robot3 상태 요약 |
| `/robot6/*` | robot6 상태 요약, mission status/log |
| `/ocr/latest` | 마지막 OCR 텍스트 |

### 14.2 추가되어야 하는 데이터

| 필요한 기능 | 필요한 RTDB path |
| --- | --- |
| 환자 방 역조회 | `/patient_rooms/{patient_id}/room` |
| 처방 조회 | `/prescriptions/{patient_id}/current/medicines` |
| 환자 순회 결과 저장 | `/robot_visits/{session_id}` |
| 투약 세션 저장 | `/medication_sessions/{session_id}` |
| 약 스캔 로그 저장 | `/medicine_scan_logs/{session_id}` |

발표 멘트:

> 현재 DB는 환자 기본정보와 방 좌표는 가지고 있습니다.
>
> 하지만 투약 검증을 하려면 처방이 문자열 하나가 아니라 약 배열로 있어야 합니다.
>
> 그래서 `/prescriptions/{patient_id}/current/medicines` 형태의 구조화된 처방이 필요합니다.

## 15. 현재 구현된 것과 목표 구현의 차이

강사님께는 이 부분을 솔직하게 말하는 것이 좋다.

| 영역 | 현재 구현 | 목표 |
| --- | --- | --- |
| Dashboard robot6 수동 주행 | 구현됨 | 유지하되 운영 모드는 mission_manager service 중심으로 정리 |
| Dashboard camera 표시 | 구현됨 | robot3/robot6 선택 가능하게 확장 |
| Dock/Undock action | dashboard에서 구현됨 | mission_manager에서도 구현 필요 |
| StartPatrol | 현재 `/robot6/start_patrol`만 있음 | `/robot3/start_patrol`로 정리 |
| Patient identifier | 흐름 구현됨 | `/robot3` namespace와 `/medicart/db` service로 수정 |
| DB bridge | placeholder | RTDB REST/SDK client와 service server 구현 |
| Scanner/OCR | placeholder 중심 | `GetOcrResult`, `VerifyMedicine` service 구현 |
| 처방 DB | 없음 | `/prescriptions` 추가 |
| Multi-robot launch | 없음 | robot3/robot6 launch 추가 |

발표 멘트:

> 현재 구현 상태와 최종 목표를 구분해서 말씀드리겠습니다.
>
> 현재 dashboard의 robot6 수동 주행과 도킹, 카메라 표시는 실제 구현이 많이 되어 있습니다.
>
> 반면 환자 순회와 투약 검증은 인터페이스와 노드 구조는 있지만, db_bridge와 mission_manager, scanner/OCR의 실제 연결이 추가로 필요합니다.
>
> 그래서 저희는 아키텍처상으로 필요한 토픽, 서비스, 액션 계약을 먼저 정리했고, 그 계약에 맞춰 구현을 채워 넣는 방향입니다.

## 16. 강사님 질문 대비 핵심 답변

### Q1. 왜 로봇이 DB를 직접 읽지 않고 `db_node`를 거치나요?

> 로봇 노드가 Firebase 구조를 직접 알면 DB 구조가 바뀔 때 모든 로봇 코드를 고쳐야 합니다.
>
> 그래서 `db_node`를 중간에 두고, 로봇은 `GetPrescription`, `VerifyMedicine`, `UpdateVisitStatus` 같은 ROS service만 호출합니다.
>
> 이렇게 하면 DB 구조 변경은 db_bridge 안에서 처리하고, 로봇 로직은 안정적으로 유지할 수 있습니다.

### Q2. Topic, Service, Action은 왜 나눠 쓰나요?

> 계속 바뀌는 상태는 topic이 좋습니다. 예를 들어 로봇 위치나 환자 식별 결과입니다.
>
> 한 번 물어보고 답을 받는 것은 service가 좋습니다. 예를 들어 환자 처방 조회입니다.
>
> 오래 걸리는 일은 action이 좋습니다. 예를 들어 목표 지점까지 이동하거나 dock하는 일입니다.

### Q3. `/robot3`와 `/robot6`는 왜 namespace가 필요한가요?

> 두 로봇이 같은 종류의 topic과 action을 사용하기 때문입니다.
>
> 예를 들어 두 로봇 모두 `navigate_to_pose`가 있습니다.
>
> namespace가 없으면 누가 누구의 이동 명령인지 헷갈립니다.
>
> 그래서 `/robot3/navigate_to_pose`, `/robot6/navigate_to_pose`처럼 분리합니다.

### Q4. 현재 DB만으로 투약 검증이 가능한가요?

> 완전한 투약 검증은 어렵습니다.
>
> 현재 DB에는 환자 기본정보와 방 좌표는 있지만, 순서가 있는 약 목록인 `MedicineInfo[]`가 없습니다.
>
> OCR로 약을 검증하려면 `/prescriptions/{patient_id}/current/medicines/{sequence_order}` 같은 구조가 필요합니다.

### Q5. 환자 식별 결과는 누가 받나요?

> `identifier_node`가 `PatientIdentified` topic을 발행합니다.
>
> 목표 구조에서는 `/robot3/patient_identified`입니다.
>
> 이 topic은 mission_manager가 받아서 미션 상태를 진행하고, dashboard가 받아서 화면에 표시합니다.

### Q6. 실제 이동 명령은 누가 보내야 하나요?

> 목표 구조에서는 mission_manager가 Nav2 action client가 되어야 합니다.
>
> dashboard는 mission_manager service를 호출하고, mission_manager가 상황에 맞게 `/robot3/navigate_to_pose` 또는 `/robot6/navigate_to_pose` action을 보내는 구조가 더 좋습니다.
>
> 현재는 dashboard가 robot6 Nav2 action을 직접 호출하는 manual/debug 기능이 구현되어 있습니다.

### Q7. 가장 먼저 구현해야 할 것은 무엇인가요?

> 첫 번째는 DB schema 보강입니다. 처방과 patient room 역조회가 필요합니다.
>
> 두 번째는 `db_bridge`의 RTDB service server 구현입니다.
>
> 세 번째는 `/robot6` 하드코딩을 제거하고 namespace 기반으로 바꾸는 것입니다.
>
> 그 다음 mission_manager에 Nav2/Dock/DB/Scanner service 연결을 추가하면 됩니다.

## 17. 발표용 전체 흐름 요약

발표 마지막에는 이렇게 정리하면 된다.

> 정리하겠습니다.
>
> 저희 시스템은 dashboard, mission_manager, 인식 노드, db_node, RTDB가 역할을 나누어 동작합니다.
>
> dashboard는 사람이 조작하는 창구입니다.
>
> mission_manager는 미션 순서를 관리하는 두뇌입니다.
>
> Nav2와 Create3는 실제 이동과 도킹을 담당합니다.
>
> identifier_node는 robot3에서 환자를 확인합니다.
>
> scanner_node와 ocr_node는 robot6에서 약을 확인합니다.
>
> db_node는 Firebase RTDB와 ROS2 사이를 이어 주며, 환자 정보, 병실 좌표, 처방, 방문 결과, 투약 결과를 읽고 씁니다.
>
> 전체 흐름은 사람이 dashboard에서 시작하고, mission_manager가 action과 service를 이용해 로봇 미션을 진행하고, 인식 결과와 DB 결과가 다시 mission_manager와 dashboard로 돌아오는 구조입니다.

## 18. 한 장으로 외우는 최종 연결

```text
[사람]
  -> dashboard_node
     -> StartPatrol / StartMedication / ScanPatient / ScanMedicine service
        -> mission_manager_node
           -> NavigateToPose action -> Nav2
           -> Dock/Undock action -> Create3
           -> GetPrescription / UpdateVisitStatus service -> db_node -> Firebase RTDB
           -> scanner verify service -> scanner_node
                -> OCR service -> ocr_node
                -> DB verify service -> db_node -> Firebase RTDB

[카메라]
  -> identifier_node
     -> PatientIdentified topic
        -> mission_manager_node
        -> dashboard_node

[상태]
  -> RobotState topic
     -> dashboard_node
```

## 19. 기능별 최소 구현 체크리스트

### 19.1 환자 순회 체크리스트

- `/robot3/start_patrol` service server
- `/robot3/navigate_to_pose` action client
- `/robot3/dock`, `/robot3/undock` action client
- `/robot3/patient_identified` topic subscribe
- `/robot3/robot_state` topic publish
- `/medicart/db/get_prescription` service client
- `/medicart/db/update_visit_status` service client
- `identifier_node` namespace parameter화
- RTDB `/patient_rooms` 또는 `/patients/{id}/room`
- RTDB `/robot_visits`

### 19.2 투약 체크리스트

- `/robot6/start_medication` service server
- `/robot6/scan_patient` service server
- `/robot6/scan_medicine` service server
- `/robot6/navigate_to_pose` action client
- `/robot6/dock`, `/robot6/undock` action client
- `/medicart/db/get_prescription` service client
- `/robot6/scanner/verify_medicine` service client
- `scanner_node`의 `VerifyMedicine` service server
- `ocr_node`의 `GetOcrResult` service server
- RTDB `/prescriptions`
- RTDB `/medication_sessions`
- RTDB `/medicine_scan_logs`

### 19.3 DB bridge 체크리스트

- RTDB URL parameter
- `GetPrescription` service server
- `VerifyMedicine` service server
- `UpdateVisitStatus` service server
- `/patients` -> `PatientInfo` 변환
- `/prescriptions` -> `MedicineInfo[]` 변환
- `/robot_visits` write
- `/medicine_scan_logs` write

## 20. 마지막 한 문장

발표 마지막 한 문장은 이렇게 하면 좋다.

> 저희 MediCart 아키텍처의 핵심은 두 대의 로봇이 각각 환자 순회와 투약이라는 역할을 맡고, dashboard가 사람의 명령을 받고, mission_manager가 로봇 미션을 순서대로 진행하며, db_node가 Firebase RTDB와 연결해서 병원 데이터를 안전하게 읽고 쓰는 구조입니다.
