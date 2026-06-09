# MediCart Architecture (Mermaid)

> 통합 브랜치(`integration` = main ↔ jaehoon) 기준. 전체 시스템 · 워크플로우 · **주 기능별 노드
> 아키텍처(주고받는 토픽/서비스/액션 명칭·타입 포함)** 를 mermaid로 정리한다. namespace 기본 `robot6`.
> 텍스트 상세는 `01_system_architecture.md`~`04_db_schema.md`, 시각본은 `diagrams/` 참고.

---

## 1. 전체 시스템 아키텍처

```mermaid
graph TD
  subgraph WEB["Web 계층 · PC3 (ROS 노드 없음)"]
    FE["Next.js 프론트 :3000<br/>/console /map /patients /intake /ocr /display /qr"]
    BE["Flask 백엔드 :5000<br/>REST + SSE · RBAC(admin/staff/patient)"]
    FE -->|"/api/* · /api/stream(SSE)"| BE
  end

  subgraph FB["Firebase — 크로스-PC 버스"]
    POOL["RTDB robot6/mission_pool<br/>(미션 큐)"]
    TEL["RTDB telemetry / alerts"]
    PAT["RTDB patients · rooms · targets<br/>intake_pending · display · ocr/latest"]
  end

  subgraph ROBOT["로봇 ROS2 스택 · 각 AMR PC (FastDDS Discovery Server, DOMAIN 6)"]
    DB["db_node<br/>(db_bridge)"]
    MM["mission_manager_node<br/>(중재 허브 · cmd_vel 단독소유)"]
    PRES["prescription_server / rooms_server<br/>(db_bridge, GetPrescription/ListRooms)"]
    PERC["인지: identifier_node(A) · tracker_node(B) · obstacle_node"]
    NAV["Nav2 + AMCL"]
    HW["Create3 · OAK-D · RPLIDAR · turtlebot4_node"]
  end

  USER["운영자 · 간호사 · 환자<br/>브라우저(cloudflared tunnel)"] -->|HTTPS| FE
  BE <-->|firebase-admin| POOL
  BE <-->|firebase-admin| TEL
  BE <-->|firebase-admin| PAT
  DB -->|listen| POOL
  DB -->|"상태 write"| POOL
  DB -.->|"telemetry"| TEL
  DB -->|"/robot6/mission_request"| MM
  MM -->|"/robot6/mission_feedback"| DB
  MM --> PERC
  MM -->|"navigate_to_pose · dock/undock"| NAV
  MM -->|"/robot6/cmd_vel"| HW
  PRES <-->|RTDB| PAT
  PERC --> NAV
  NAV --> HW
  HW --> PERC
```

---

## 2. 워크플로우

### 2.1 미션 요청 파이프라인 (웹 → 로봇)

```mermaid
sequenceDiagram
  participant U as 사용자(브라우저)
  participant FE as Next.js :3000
  participant BE as Flask :5000
  participant POOL as RTDB mission_pool
  participant DB as db_node
  participant MM as mission_manager_node
  participant ACT as Nav2 / Create3 / mode

  U->>FE: 명령(goto/undock/회진 등)
  FE->>BE: POST /api/robots/robot6/missions
  BE->>POOL: push mission
  POOL-->>DB: listen (신규/pending)
  DB->>MM: /robot6/mission_request (std_msgs/String)
  Note over MM: 2-lane 라우팅<br/>system / goto / mode
  MM->>ACT: 실행(navigate_to_pose · dock/undock · cmd_vel)
  ACT-->>MM: 결과/피드백
  MM->>DB: /robot6/mission_feedback (String)
  DB->>POOL: 상태 갱신(running/done/failed)
  POOL-->>BE: 변경
  BE-->>FE: /api/stream(SSE) · /api/.../missions
  FE-->>U: 표시
```

### 2.2 시나리오 A — 자율 순찰 + 문진 (patrol)

```mermaid
flowchart TD
  S0([Station 도킹]) --> U0["Undock<br/>(Create3 /robot6/undock)"]
  U0 --> L0["병상 waypoint 획득<br/>ListRooms /robot6/db/list_rooms"]
  L0 --> P0["다음 병실 이동<br/>NavigateToPose /robot6/navigate_to_pose"]
  P0 --> ID["재실+신원 확인<br/>identifier_node → /robot6/patient_identified"]
  ID --> VAL["처방/환자 검증<br/>GetPrescription /robot6/db/get_prescription"]
  VAL --> IV["웹 문진표 작성<br/>/intake → RTDB patients/intake"]
  IV --> Q{남은 병실?}
  Q -- yes --> P0
  Q -- no --> R0["복귀 NavigateToPose(station)"]
  R0 --> D0["Dock /robot6/dock"] --> E0([도킹 완료])
  ID -. "부재/불일치" .-> UVS["UpdateVisitStatus(DB 기록)<br/>→ 마지막 재방문"]
```

### 2.3 시나리오 B — 간호사 투약 보조 (round)

```mermaid
flowchart TD
  B0([Station 도킹]) --> BU["Undock"]
  BU --> TR["간호사 추종 시작<br/>Trigger /robot6/start_tracking"]
  TR --> FOL["추종 주행<br/>tracker_node → /robot6/mode/round/cmd_vel"]
  FOL --> ARR["호실 도착(STANDBY)"]
  ARR --> SC["약품 OCR 검증(반복)<br/>웹 /ocr(GCP Vision) ↔ 처방 step"]
  SC --> Q2{투약 완료?}
  Q2 -- no --> SC
  Q2 -- yes --> BR["복귀 NavigateToPose(station)"]
  BR --> BD["Dock"] --> BE0([도킹 완료])
  FOL -. "전방 장애물" .-> GATE["mission_manager safety_gate<br/>(lidar 0.3m / depth 0.2m)"]
```

### 2.4 회진 풀스크린 모드 (웹 주도, jaehoon)

```mermaid
flowchart TD
  H0["홈 / 최상단 '회진 모드' 배너 클릭"] --> CF{재확인}
  CF -- 확인 --> UD["docked면 undock<br/>pushMission(undock) + dock_status 대기"]
  UD --> RD["saveMode(start, round)<br/>→ round 모드 추종 시작"]
  RD --> OV["FollowOverlay 풀스크린<br/>(자가 SSE pose 구독)"]
  OV --> NP{"약품실/101호1·2<br/>1m 근접?"}
  NP -- yes --> TXT["'OO에 도착' 표시<br/>(로봇은 계속 추종)"]
  NP -- no --> OV
  OV --> RB["'홈 위치로 복귀' 버튼"]
  RB --> RH["saveMode(stop,round) +<br/>goto(dock,dock_after) → 도킹 후 종료"]
```

---

## 3. 주 기능별 노드 아키텍처 (토픽 · 서비스 · 액션 명칭·타입)

### 3.1 미션 중재 허브 — mission_manager_node

```mermaid
graph LR
  DB["db_node"] -->|"/robot6/mission_request<br/>std_msgs/String"| MM
  MM["mission_manager_node"] -->|"/robot6/mission_feedback<br/>std_msgs/String"| DB
  SCAN["RPLIDAR"] -->|"/robot6/scan<br/>sensor_msgs/LaserScan"| MM
  DS["Create3"] -->|"/robot6/dock_status<br/>irobot_create_msgs/DockStatus"| MM
  MM -->|"/robot6/cmd_vel<br/>geometry_msgs/Twist (단독소유)"| BASE["Create3 base"]
  MM -->|"/robot6/robot_mode<br/>std_msgs/String"| MON["모니터/웹"]
  MM -. "내부" .-> ARB["mode_arbiter"]
  MM -. "내부" .-> NEX["nav_executor"]
  MM -. "내부" .-> MEX["mission_executor"]
  MM -. "내부" .-> SEQ["MissionSequencer(patrol)"]
  NEX -->|"navigate_to_pose (nav2_msgs/NavigateToPose)"| NAV2["Nav2 bt_navigator"]
  NEX -->|"dock / undock (irobot_create_msgs)"| C3["Create3"]
  MEX -->|"subprocess: ros2 action send_goal / ssh"| C3
```

### 3.2 모드 중재 — mode_arbiter (REACTIVE 모드 계약)

```mermaid
graph LR
  subgraph MODES["모드 노드(tracker_node 등) — 우선순위: 문진>회진>지시>가이드>순찰"]
    M["mode node<br/>(예: round)"]
  end
  ARB["mode_arbiter<br/>(mission_manager 내부)"] -->|"/robot6/mode/{mode}/set<br/>String (latched)"| M
  M -->|"/robot6/mode/{mode}/cmd_vel<br/>geometry_msgs/Twist"| ARB
  M -->|"/robot6/mode/{mode}/status<br/>String (워치독)"| ARB
  ARB -->|"우선순위 선택 + safety_gate<br/>(전방 lidar 0.3m/depth 0.2m)"| OUT["/robot6/cmd_vel"]
```

### 3.3 시나리오 A 인지 — patient_identifier + db_bridge

```mermaid
graph LR
  OAK["OAK-D"] -->|"/robot6/oakd/rgb/image_raw<br/>sensor_msgs/Image"| ID
  ID["identifier_node<br/>(YOLO + QR + 병실검증)"] -->|"/robot6/patient_identified<br/>medi_interfaces/PatientIdentified"| PAT["patrol_mode_node"]
  ID -->|"/robot6/identify/start (String)"| ID
  ID -->|"GetPrescription 요청<br/>/robot6/db/get_prescription<br/>medi_interfaces/srv"| PS["prescription_server<br/>(db_bridge)"]
  PS -->|"PatientInfo + MedicineInfo[]"| ID
  PS <-->|"RTDB patients/patient_rooms/rooms"| RTDB[("Firebase RTDB")]
  PAT -->|"ListRooms /robot6/db/list_rooms"| RS["rooms_server (db_bridge)"]
  RS -->|"room_ids/xs/ys/yaws"| PAT
  PAT -->|"navigate_to_pose"| NAV2["Nav2"]
```

### 3.4 시나리오 B 추종 — nurse_tracker (round)

```mermaid
graph LR
  OAK["OAK-D"] -->|"/robot6/oakd/rgb/image_raw/compressed<br/>sensor_msgs/CompressedImage"| TR
  OAK -->|"/robot6/oakd/stereo/image_raw/compressedDepth"| TR
  TR["tracker_node<br/>(YOLO11s best.pt + ByteTrack)"] -->|"/robot6/mode/round/cmd_vel<br/>geometry_msgs/Twist"| ARB["mode_arbiter"]
  TR -->|"/robot6/mode/round/status (String)"| ARB
  TR -->|"/nurse_tracker/target (String)"| VIS["시각화/디버그"]
  CALLER["mission_manager / 웹"] -->|"Trigger /robot6/start_tracking<br/>std_srvs/srv/Trigger"| TR
  ARB -. "/robot6/mode/round/set" .-> TR
```

### 3.5 장애물 안전 — obstacle_detector

```mermaid
graph LR
  OAK["OAK-D stereo"] -->|"/robot6/oakd/stereo/image_raw/compressedDepth"| OB
  OAK -->|"/robot6/oakd/stereo/camera_info<br/>sensor_msgs/CameraInfo"| OB
  OB["obstacle_node<br/>(depth→지면 평면 분석 SVD)"] -->|"/obstacle_detector/ground_cloud<br/>sensor_msgs/PointCloud2"| RV["RViz/디버그"]
  OB -->|"/obstacle_detector/ground_status<br/>std_msgs/String"| MM["mission_manager safety_gate"]
```

### 3.6 자율주행 · 하드웨어 (빌트인/외부)

```mermaid
graph LR
  AMCL["AMCL (loc)"] -->|"map→odom TF · /robot6/amcl_pose"| NAV2["Nav2"]
  MAP["map_server"] -->|"/robot6/map (OccupancyGrid)"| NAV2
  RP["RPLIDAR"] -->|"/robot6/scan (LaserScan)"| AMCL
  RP --> NAV2
  NAV2 -->|"navigate_to_pose (action)"| NAV2
  C3["Create3"] -->|"/robot6/odom · /robot6/battery_state · /robot6/dock_status"| WEB["telemetry→RTDB→웹"]
  C3 -->|"dock / undock (action server)"| C3
  OAK["OAK-D"] -->|"/robot6/oakd/rgb/* · /robot6/oakd/stereo/*"| PERC["인지 노드들"]
```

---

## 4. 인터페이스 레퍼런스 (요약 표)

### 토픽
| 토픽 | 타입 | pub → sub |
| --- | --- | --- |
| `/robot6/mission_request` | std_msgs/String | db_node → mission_manager_node |
| `/robot6/mission_feedback` | std_msgs/String | mission_manager_node → db_node |
| `/robot6/cmd_vel` | geometry_msgs/Twist | mission_manager_node(단독) → Create3 |
| `/robot6/robot_mode` | std_msgs/String | mission_manager_node → 모니터 |
| `/robot6/mode/{mode}/cmd_vel` | geometry_msgs/Twist | 모드노드 → mode_arbiter |
| `/robot6/mode/{mode}/status` | std_msgs/String | 모드노드 → mode_arbiter |
| `/robot6/mode/{mode}/set` | std_msgs/String(latched) | mode_arbiter → 모드노드 |
| `/robot6/patient_identified` | medi_interfaces/PatientIdentified | identifier_node → patrol_mode_node |
| `/nurse_tracker/target` | std_msgs/String | tracker_node → 시각화 |
| `/obstacle_detector/ground_cloud` | sensor_msgs/PointCloud2 | obstacle_node → RViz |
| `/obstacle_detector/ground_status` | std_msgs/String | obstacle_node → safety_gate |
| `/robot6/scan` | sensor_msgs/LaserScan | RPLIDAR → amcl/nav2/mission_manager |
| `/robot6/odom` · `/robot6/battery_state` · `/robot6/dock_status` | nav_msgs/Odometry · sensor_msgs/BatteryState · irobot_create_msgs/DockStatus | Create3 → 구독자 |
| `/robot6/amcl_pose` · `/robot6/map` | geometry_msgs/PoseWithCovarianceStamped · nav_msgs/OccupancyGrid | AMCL/map_server → Nav2 |
| `/robot6/oakd/rgb/*` · `/robot6/oakd/stereo/*` | sensor_msgs/Image·CompressedImage·CameraInfo | OAK-D → 인지 |

### 서비스
| 서비스 | 타입 | 서버 → 클라이언트 |
| --- | --- | --- |
| `/robot6/db/get_prescription` | medi_interfaces/GetPrescription | prescription_server → patient_validator(identifier) |
| `/robot6/db/list_rooms` | medi_interfaces/ListRooms | rooms_server → patrol_mode_node |
| `/robot6/start_tracking` | std_srvs/Trigger | tracker_node ← mission_manager/웹 |

### 액션
| 액션 | 타입 | 서버 → 클라이언트 |
| --- | --- | --- |
| `/robot6/navigate_to_pose` | nav2_msgs/NavigateToPose | Nav2 bt_navigator ← nav_executor·patrol_mode·dashboard |
| `/robot6/dock` · `/robot6/undock` | irobot_create_msgs/Dock·Undock | Create3 ← nav_executor·mission_executor·dashboard |

### Firebase RTDB 경로
| 경로 | 용도 |
| --- | --- |
| `robot6/mission_pool` | 미션 큐(웹→로봇), 상태(로봇→웹) |
| `robot6/cmd` | 모드 명령(웹 publish_mode_cmd → db_node) |
| `patients/{pid}/{info,injections,intake,visits,vitals}` | 환자 데이터·문진·생체징후·약품 |
| `rooms` · `targets` | 병실 waypoint · goto 프리셋 |
| `intake_pending` · `display/current_patient` · `ocr/latest` · `{src}/alerts` | 환자 자가문진·디스플레이·OCR·알림 |

> 빌트인(외부): `depthai_ros_driver`(OAK-D) · `rplidar_ros` · `turtlebot4_node` · `nav2_*` · `irobot_create_msgs`. 시나리오 B 일부 srv(ScanMedicine·VerifyMedicine·GetOcrResult 등)는 medi_interfaces에 **선정의·미결선**(`integration_todoList.md` 참고).
