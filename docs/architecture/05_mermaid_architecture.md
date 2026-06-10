# MediCart Architecture (Mermaid · HERA급)

> 통합 브랜치(`integration` = main ↔ jaehoon) 기준. 참조 수준: HERABot System Architecture Diagram.
> namespace 기본 `robot6` — **robot3(AMR1)도 PC1에서 동일 구조로 동작**(노드·토픽 네임스페이스만 `robot3`).
> 구성: §0 범례 → §1 마스터 오버뷰 → §2 컴퓨트·네트워크 → §3 ROS 노드 그래프 → §4 상태머신 → §5 워크플로우 → §6 인터페이스·노드 역할 표.
> 텍스트 상세는 `01_system_architecture.md`~`04_db_schema.md`, 시각본은 `diagrams/` 참고.

---

## 0. 범례 (통신 종류 · 노드 역할)

**통신 종류 = 화살표 모양**으로 구분한다.

```mermaid
graph LR
  P1["발행 노드"] -->|"topic /name &lt;Type&gt;"| P2["구독 노드"]
  C1["클라이언트"] -.->|"srv /name (Type) · 요청/응답"| S1["서비스 서버"]
  A1["클라이언트"] ==>|"action /name (Type) · goal·feedback·result"| AS1["액션 서버"]
  W1["웹/RTDB"] -.->|"RTDB path (ROS 아님)"| W2["로봇 노드"]
  classDef orch fill:#fde68a,stroke:#b45309,color:#111
  classDef srv fill:#ddd6fe,stroke:#6d28d9,color:#111
  classDef app fill:#bbf7d0,stroke:#15803d,color:#111
  classDef nav fill:#bfdbfe,stroke:#1d4ed8,color:#111
  classDef hw fill:#e5e7eb,stroke:#374151,color:#111
  class P1 orch
  class S1 srv
  class P2 app
  class AS1 nav
  class C1,A1,W1,W2 hw
```

- `-->` 실선 = **topic** (publish → subscribe)
- `-.->` 점선 = **service** (client → server, 요청/응답 1회)
- `==>` 굵은선 = **action** (client → server, goal → feedback(다회) → result)
- `-.->` + `RTDB` 라벨 = Firebase RTDB 읽기/쓰기(ROS 통신 아님)

**노드 역할 = 색**: 🟨 오케스트레이터 · 🟪 서비스 서버 · 🟩 인지/모드 노드 · 🟦 자율주행(Nav2/AMCL) · ⬜ 하드웨어/드라이버.

---

## 1. 마스터 오버뷰 (전체 배치)

```mermaid
graph TD
  USER["운영자·간호사·환자<br/>브라우저"] -->|"HTTPS / cloudflared"| FE

  subgraph PC3["PC3 — 웹 (ROS 노드 없음)"]
    FE["Next.js :3000"]
    BE["Flask :5000 · RBAC"]
    FE -->|"/api/* · SSE"| BE
  end

  subgraph FB["Firebase RTDB — 크로스-PC 버스"]
    POOL["robot6/mission_pool<br/>(미션 큐)"]
    CMD["robot6/cmd<br/>(모드 명령, 큐 우회)"]
    DATA["patients · rooms · targets<br/>display · ocr · telemetry"]
  end

  subgraph PC2["PC2 — robot6 전담 (FastDDS Discovery :11811 · DOMAIN 6)"]
    DB["db_node<br/><i>오케스트레이터</i>"]
    MM["mission_manager_node<br/><i>중재 허브 · action client</i>"]
    SRV["prescription_server · rooms_server<br/><i>서비스 서버</i>"]
    PERC["identifier_node(A) · tracker_node(B)<br/>obstacle_node · display_bridge<br/><i>인지/모드</i>"]
    NAV["Nav2 · AMCL · map_server<br/><i>action server</i>"]
  end

  subgraph AMR["robot6 (turtlebot4)"]
    HW["Create3 · OAK-D-Pro · RPLIDAR A1M8<br/><i>action server / 센서</i>"]
  end

  PC1["PC1 — robot3 전담 (동일 구조)"]

  BE -.->|"RTDB write/read"| POOL
  BE -.->|"RTDB write (saveMode)"| CMD
  BE -.->|"RTDB"| DATA
  POOL -.->|"RTDB listen"| DB
  CMD -.->|"RTDB listen → 즉시 중계"| DB
  DB -->|"topic mission_request · mission_cancel &lt;String&gt;"| MM
  MM -->|"topic mission_feedback &lt;String&gt;"| DB
  MM ==>|"action navigate_to_pose · dock · undock"| NAV
  MM ==>|"action dock · undock"| HW
  MM -->|"topic cmd_vel &lt;Twist&gt;"| HW
  MM --> PERC
  SRV -.->|"RTDB"| DATA
  NAV --> HW
  HW -->|"topic scan · oakd · odom · battery · dock_status"| PERC
  HW -.->|"telemetry → RTDB"| DB
  PC1 -.->|"RTDB"| FB

  classDef orch fill:#fde68a,stroke:#b45309,color:#111
  classDef srv fill:#ddd6fe,stroke:#6d28d9,color:#111
  classDef app fill:#bbf7d0,stroke:#15803d,color:#111
  classDef nav fill:#bfdbfe,stroke:#1d4ed8,color:#111
  classDef hw fill:#e5e7eb,stroke:#374151,color:#111
  class DB orch
  class MM orch
  class SRV srv
  class PERC app
  class NAV nav
  class HW hw
```

> robot3(AMR1)은 PC1에서 위 robot6 스택과 동일하게 동작하며 네임스페이스만 `robot3`.
> **모드 명령(start/stop/clear)은 `robot6/cmd`로 들어와 큐(mission_pool)를 우회**한다 — 모드는 arbiter 우선순위 선점이라 직렬 큐에 넣으면 앞선 goto/undock에 막혀 활성화가 지연된다.

---

## 2. 컴퓨트 & 네트워크 레이아웃

```mermaid
graph TB
  subgraph NET["네트워크 — ROS2 Humble · WiFi6 AP · Gigabit Ethernet Switch · cloudflared(외부)"]
    direction TB

    subgraph OPC["운영 PC (PC1=robot3 / PC2=robot6 동일 구성)"]
      OS["Ubuntu 22.04 LTS · ROS2 Humble · FastDDS Discovery Server :11811 (DOMAIN 6)"]
      VIZ["RViz2 — 시각화 /scan /map /tf /odom /image_raw · Set Goal Pose→Nav2 · Set Initial Pose→AMCL"]
      LOC["loc6 — AMCL (bond_timeout 10s 패치)"]
      NV["nav6 — Nav2 bt_navigator · controller_server · planner_server · map_server (bond 패치)"]
      APP["앱 패키지 — db_bridge · mission_manager · nurse_tracker · obstacle_detector · patient_identifier · medi_interfaces"]
    end

    subgraph TB4["robot6 — turtlebot4 (RPi 4B)"]
      BR["turtlebot4_bringup — robot_state_publisher(/robot_description /tf /tf_static) · rplidar_ros(/scan) · depthai_ros_driver(/oakd/rgb /oakd/stereo /camera_info) · diagnostics(/battery_state) · HMI(버튼/LED/오디오)"]
      TNAV["turtlebot4_navigation — AMCL · controller_server · planner_server · bt_navigator · map_server"]
      HWB["HW — iRobot Create3 · RPLIDAR A1M8 · OAK-D-Pro · 배터리 · Status LED(MTR/COMM/WiFi/Battery/Power)"]
    end

    subgraph WPC["PC3 — 웹"]
      WEB["Next.js :3000 · Flask :5000 · cloudflared 터널 (ROS 노드 없음, RTDB 읽기/쓰기만)"]
    end
  end

  OPC <-->|"FastDDS (sensor·TF·cmd_vel)"| TB4
  WPC <-->|"Firebase RTDB"| OPC
```

---

## 3. ROS 노드 그래프 (역할 + 통신 종류)

> 화살표: 실선 `-->` topic · 점선 `-.->` service · 굵은선 `==>` action. 색: §0 범례.

### 3.1 미션 오케스트레이션 — db_node ↔ mission_manager

```mermaid
graph LR
  POOL[("RTDB mission_pool")] -.->|"RTDB listen"| DB["db_node<br/><i>오케스트레이터</i>"]
  CMD[("RTDB cmd")] -.->|"RTDB listen → 큐 우회 중계"| DB
  DB -.->|"RTDB status/progress/log write"| POOL
  DB -->|"topic mission_request &lt;String&gt; {id,action,params,mode}"| MM["mission_manager_node<br/><i>중재 허브 · action client</i>"]
  DB -->|"topic mission_cancel &lt;String&gt; (선점)"| MM
  MM -->|"topic mission_feedback &lt;String&gt; {status: accepted→running→done/failed}"| DB
  MM -->|"topic robot_mode &lt;String&gt;"| MON["모니터/웹"]
  MM -->|"topic cmd_vel &lt;Twist&gt; (단독소유)"| C3["Create3 base"]
  SCAN["RPLIDAR"] -->|"topic scan &lt;LaserScan&gt;"| MM
  DS["Create3"] -->|"topic dock_status &lt;DockStatus&gt;"| MM
  MM ==>|"action navigate_to_pose (NavigateToPose) frame_id='map'"| NAV2["Nav2 bt_navigator<br/><i>action server</i>"]
  MM ==>|"action dock · undock (Dock·Undock)"| C3
  MM -. "내부: mode_arbiter · nav_executor · mission_executor · MissionSequencer" .-> MM

  classDef orch fill:#fde68a,stroke:#b45309,color:#111
  classDef nav fill:#bfdbfe,stroke:#1d4ed8,color:#111
  classDef hw fill:#e5e7eb,stroke:#374151,color:#111
  class DB,MM orch
  class NAV2 nav
  class C3,SCAN,DS,MON hw
```

### 3.2 모드 중재 — mode_arbiter (REACTIVE 계약)

```mermaid
graph LR
  ARB["mode_arbiter<br/><i>mission_manager 내부</i>"] -->|"topic mode/{mode}/set &lt;String&gt; latched {active,params}"| M["mode node (예: round)<br/><i>모드 노드</i>"]
  M -->|"topic mode/{mode}/cmd_vel &lt;Twist&gt;"| ARB
  M -->|"topic mode/{mode}/status &lt;String&gt; {state}"| ARB
  OB["obstacle_node"] -->|"topic ground_status &lt;String&gt;"| ARB
  ARB -->|"우선순위 선택 + safety_gate (lidar 0.30m / depth 0.20m) → topic cmd_vel &lt;Twist&gt;"| OUT["Create3 base"]

  classDef orch fill:#fde68a,stroke:#b45309,color:#111
  classDef app fill:#bbf7d0,stroke:#15803d,color:#111
  classDef hw fill:#e5e7eb,stroke:#374151,color:#111
  class ARB orch
  class M,OB app
  class OUT hw
```

### 3.3 시나리오 A 인지 — identifier_node + db_bridge

```mermaid
graph LR
  OAK["OAK-D"] -->|"topic oakd/rgb/image_raw &lt;Image&gt;"| ID["identifier_node<br/><i>인지 · srv client</i>"]
  PAT["patrol_mode_node<br/><i>모드 · action·srv client</i>"] -->|"topic identify/start &lt;String&gt;"| ID
  ID -->|"topic patient_identified &lt;PatientIdentified&gt;"| PAT
  ID -->|"topic patient_identified"| DBR["display_bridge<br/><i>구독→RTDB</i>"]
  ID -.->|"srv db/get_prescription (GetPrescription) · PatientValidator"| PS["prescription_server<br/><i>서비스 서버</i>"]
  PS -.->|"RTDB patients/rooms"| RTDB[("Firebase RTDB")]
  DBR -.->|"RTDB display/current_patient"| RTDB
  PAT -.->|"srv db/list_rooms (ListRooms)"| RS["rooms_server<br/><i>서비스 서버</i>"]
  PAT ==>|"action navigate_to_pose (NavigateToPose)"| NAV2["Nav2"]

  classDef srv fill:#ddd6fe,stroke:#6d28d9,color:#111
  classDef app fill:#bbf7d0,stroke:#15803d,color:#111
  classDef nav fill:#bfdbfe,stroke:#1d4ed8,color:#111
  classDef hw fill:#e5e7eb,stroke:#374151,color:#111
  class ID,PAT,DBR app
  class PS,RS srv
  class NAV2 nav
  class OAK hw
```

### 3.4 시나리오 B 추종 — nurse_tracker (round)

```mermaid
graph LR
  OAK["OAK-D"] -->|"topic oakd/rgb/image_raw/compressed &lt;CompressedImage&gt;"| TR["tracker_node<br/><i>모드 · srv server</i><br/>(perception · follow_control)"]
  OAK -->|"topic oakd/stereo/image_raw/compressedDepth &lt;CompressedImage&gt;"| TR
  CALL["mission_manager / 웹"] -.->|"srv start_tracking (Trigger)"| TR
  TR -->|"topic mode/round/cmd_vel &lt;Twist&gt;"| ARB["mode_arbiter"]
  TR -->|"topic mode/round/status &lt;String&gt;"| ARB
  TR -->|"topic /nurse_tracker/target &lt;String&gt; · /nurse_tracker/annotated_image &lt;Image&gt;"| VIS["시각화/디버그"]
  ARB -->|"topic mode/round/set &lt;String&gt; latched"| TR

  classDef orch fill:#fde68a,stroke:#b45309,color:#111
  classDef app fill:#bbf7d0,stroke:#15803d,color:#111
  classDef hw fill:#e5e7eb,stroke:#374151,color:#111
  class TR app
  class ARB orch
  class OAK,CALL,VIS hw
```

### 3.5 장애물 안전 — obstacle_detector

```mermaid
graph LR
  OAK["OAK-D stereo"] -->|"topic oakd/stereo/image_raw/compressedDepth &lt;CompressedImage&gt;"| OB["obstacle_node<br/><i>인지 (depth→지면 SVD)</i>"]
  OAK -->|"topic oakd/stereo/camera_info &lt;CameraInfo&gt;"| OB
  OB -->|"topic ground_cloud &lt;PointCloud2&gt;"| RV["RViz/디버그"]
  OB -->|"topic ground_status &lt;String&gt;"| MM["mission_manager safety_gate"]

  classDef orch fill:#fde68a,stroke:#b45309,color:#111
  classDef app fill:#bbf7d0,stroke:#15803d,color:#111
  classDef hw fill:#e5e7eb,stroke:#374151,color:#111
  class OB app
  class MM orch
  class OAK,RV hw
```

### 3.6 자율주행 · 하드웨어

```mermaid
graph LR
  RP["RPLIDAR"] -->|"topic scan &lt;LaserScan&gt;"| AMCL["AMCL (loc)<br/><i>측위</i>"]
  RP -->|"topic scan"| NAV2["Nav2<br/><i>action server</i>"]
  MAP["map_server"] -->|"topic map &lt;OccupancyGrid&gt;"| NAV2
  AMCL -->|"TF map→odom · topic amcl_pose &lt;PoseWithCovarianceStamped&gt;"| NAV2
  CLI["nav_executor · patrol_mode · dashboard"] ==>|"action navigate_to_pose (NavigateToPose)"| NAV2
  CLI ==>|"action dock · undock (Dock·Undock)"| C3["Create3<br/><i>action server / HW</i>"]
  C3 -->|"topic odom &lt;Odometry&gt; · battery_state &lt;BatteryState&gt; · dock_status &lt;DockStatus&gt;"| SUB["telemetry→RTDB→웹"]
  OAK["OAK-D"] -->|"topic oakd/rgb/* · oakd/stereo/*"| PERC["인지 노드들"]

  classDef nav fill:#bfdbfe,stroke:#1d4ed8,color:#111
  classDef hw fill:#e5e7eb,stroke:#374151,color:#111
  class AMCL,NAV2,MAP nav
  class RP,C3,OAK,SUB,PERC,CLI hw
```

---

## 4. 상태머신

### 4.1 미션 라이프사이클 (db_node 오케스트레이션)

```mermaid
stateDiagram-v2
  [*] --> pending : web push — mission_pool
  pending --> sent : 우선순위→ts 선택 후 mission_request 발행
  sent --> running : accepted/running 수신
  sent --> failed : 15s 내 accepted 미수신 — START_TIMEOUT
  running --> done : mission_feedback done
  running --> failed : mission_feedback failed
  running --> preempted : 더 높은 우선순위 도착 — 현재 폐기·드롭
  done --> [*]
  failed --> [*]
  preempted --> [*]
  note right of running
    완료 타임아웃 없음 (무제한 대기)
    NON_PREEMPTIBLE(dock/undock/시스템/patrol_mission)은 선점 안 함
    nav_executor는 create3 진행 중 cancel을 goal 취소 없이 안전 처리
  end note
```

### 4.2 모드 중재 — 우선순위 선점/복귀 + safety_gate

```mermaid
stateDiagram-v2
  [*] --> idle
  idle --> active : start mode — active set 추가 · cmd 경로 큐우회
  active --> preempted_mode : 더 높은 우선순위 모드 활성
  preempted_mode --> active : 상위 모드 종료 → 복귀
  active --> idle : stop/clear 또는 status done/failed
  active --> lost : status 무응답 3s — lost abort
  lost --> idle
  note right of active
    우선순위: goto 7 (운영자) > intake 5 > round 4 > errand 3 > guide 2 > patrol 1
    REACTIVE 모드: cmd_vel은 safety_gate 통과 (전방 lidar 0.30m / depth 0.20m, 전진만 차단)
  end note
```

---

## 5. 워크플로우 (통신 종류 명시)

### 5.0 미션 파이프라인 시퀀스 (topic · service · action 구분)

```mermaid
sequenceDiagram
  autonumber
  participant U as 웹(브라우저)
  participant BE as Flask
  participant RT as RTDB
  participant DB as db_node
  participant MM as mission_manager
  participant N as Nav2/Create3

  U->>BE: POST 미션/모드
  BE->>RT: RTDB write (mission_pool 또는 cmd)
  RT-->>DB: RTDB listen 이벤트
  Note over DB: 미션=큐(우선순위→ts) · 모드=cmd 큐우회
  DB->>MM: topic mission_request &lt;String&gt;
  MM-->>DB: topic mission_feedback accepted
  Note over DB: 15s 시작 워치독 해제 · 완료 무제한
  MM->>N: action goal (navigate_to_pose / dock / undock)
  N-->>MM: action feedback (다회)
  N-->>MM: action result (succeeded/aborted)
  MM-->>DB: topic mission_feedback done|failed
  DB->>RT: RTDB log 아카이브 + pool 비움
  RT-->>BE: RTDB 변경 → SSE
  BE-->>U: 표시
  Note over DB,MM: 더 높은 우선순위 도착 시 DB→MM topic mission_cancel, 현재 폐기(드롭)
```

### 5.1 시나리오 A — 자율순찰 + QR신원 + 문진

```mermaid
flowchart TD
  S0([Station 도킹]) --> U0["Undock — action undock"]
  U0 --> L0["병상 waypoint — srv list_rooms"]
  L0 --> P0["다음 병실 이동 — action navigate_to_pose"]
  P0 --> ID["재실+신원 확인 — topic identify/start → patient_identified"]
  ID --> Q0{"재실·신원 일치?"}
  Q0 -- no --> UVS["UpdateVisitStatus (DB 기록) → 마지막 재방문"]
  UVS --> Q1
  Q0 -- yes --> VAL["처방 검증 — srv get_prescription"]
  VAL --> IV["웹 문진표 — RTDB patients/intake"]
  IV --> Q1{"남은 병실?"}
  Q1 -- yes --> P0
  Q1 -- no --> R0["복귀 — action navigate_to_pose(station)"]
  R0 --> D0["Dock — action dock"] --> E0([도킹 완료])
```

### 5.2 시나리오 B — 간호사 추종 + 약품 OCR

```mermaid
flowchart TD
  B0([Station 도킹]) --> BU["Undock — action undock"]
  BU --> TR["추종 시작 — srv start_tracking (Trigger)"]
  TR --> FOL["추종 주행 — topic mode/round/cmd_vel"]
  FOL --> GATE{"전방 장애물?<br/>lidar 0.30m / depth 0.20m"}
  GATE -- yes --> STOP["safety_gate 전진 차단"] --> FOL
  GATE -- no --> ARR["호실 도착 (STANDBY)"]
  ARR --> SC["약품 OCR — 웹 /ocr(GCP Vision) ↔ 처방 step"]
  SC --> Q2{"투약 완료?"}
  Q2 -- no --> SC
  Q2 -- yes --> BR["복귀 — action navigate_to_pose(station)"]
  BR --> BD["Dock — action dock"] --> BE0([도킹 완료])
```

### 5.3 회진 풀스크린 모드 (웹 주도)

```mermaid
flowchart TD
  H0["홈 / '회진 모드' 배너 클릭"] --> CF{"재확인"}
  CF -- 확인 --> UD["docked면 undock — RTDB mission_pool(undock) + dock_status 대기"]
  UD --> RD["saveMode(start, round) — RTDB cmd (큐 우회) → topic mode/round/set"]
  RD --> OV["FollowOverlay 풀스크린 (SSE pose 구독)"]
  OV --> NP{"약품실/101호 1·2<br/>1m 근접?"}
  NP -- yes --> TXT["'OO에 도착' 표시 (로봇은 계속 추종)"]
  TXT --> OV
  NP -- no --> OV
  OV --> RB["'홈 위치로 복귀' 버튼"]
  RB --> RH["saveMode(stop,round) + goto(dock,dock_after) → 도킹 후 종료"]
```

---

## 6. 인터페이스 · 노드 역할

### 6.1 노드 역할 표 (각 노드가 무슨 노드인가)

| 노드 | 패키지 | 역할 | ROS 통신 |
| --- | --- | --- | --- |
| `db_node` | db_bridge | 오케스트레이터(RTDB↔ROS) | **pub** mission_request·mission_cancel · **sub** mission_feedback · RTDB listen(mission_pool·cmd)/write(status·log) |
| `mission_manager_node` | mission_manager | 중재 허브 | **sub** mission_request·mission_cancel·scan · **pub** mission_feedback·cmd_vel·robot_mode · **action client** navigate_to_pose·dock·undock · pub mode/*/set · sub mode/*/cmd_vel·status |
| `prescription_server` | db_bridge | 서비스 서버 | **srv server** GetPrescription (RTDB read) |
| `rooms_server` | db_bridge | 서비스 서버 | **srv server** ListRooms (RTDB read) |
| `display_bridge` | db_bridge | 구독→RTDB 브리지 | **sub** patient_identified → RTDB display/current_patient |
| `identifier_node` | patient_identifier | 인지(시나리오A) | **sub** oakd/rgb/image_raw·identify/start · **pub** patient_identified · **srv client** GetPrescription(PatientValidator) |
| `patrol_mode_node` | mission_manager | 모드 노드(시나리오A) | **pub** identify/start·mode/patrol/status · **sub** patient_identified·mode/patrol/set · **action client** navigate_to_pose · **srv client** ListRooms |
| `tracker_node` | nurse_tracker | 모드 노드(시나리오B) | **sub** oakd rgb/compressed·stereo/compressedDepth·mode/round/set · **pub** mode/round/cmd_vel·status·/nurse_tracker/target·annotated_image · **srv server** start_tracking |
| `obstacle_node` | obstacle_detector | 인지(안전) | **sub** oakd stereo/compressedDepth·camera_info · **pub** ground_cloud·ground_status |
| `Nav2 bt_navigator` | nav2 | 자율주행 | **action server** navigate_to_pose |
| `AMCL` | nav2 | 측위 | **sub** scan · **pub** amcl_pose · TF(map→odom) |
| `map_server` | nav2 | 정적맵 | **pub** map |
| `Create3` | irobot_create | 베이스 HW | **action server** dock·undock · **pub** odom·battery_state·dock_status · **sub** cmd_vel |

### 6.2 토픽
| 토픽 | 타입 | pub → sub |
| --- | --- | --- |
| `/robot6/mission_request` | std_msgs/String | db_node → mission_manager_node |
| `/robot6/mission_feedback` | std_msgs/String | mission_manager_node → db_node |
| `/robot6/mission_cancel` | std_msgs/String | db_node → mission_manager_node (선점) |
| `/robot6/cmd_vel` | geometry_msgs/Twist | mission_manager_node(단독) → Create3 |
| `/robot6/robot_mode` | std_msgs/String | mission_manager_node → 모니터 |
| `/robot6/mode/{mode}/set` | std_msgs/String (latched) | mode_arbiter → 모드노드 |
| `/robot6/mode/{mode}/cmd_vel` | geometry_msgs/Twist | 모드노드 → mode_arbiter |
| `/robot6/mode/{mode}/status` | std_msgs/String | 모드노드 → mode_arbiter |
| `/robot6/identify/start` | std_msgs/String | patrol_mode_node → identifier_node |
| `/robot6/patient_identified` | medi_interfaces/PatientIdentified | identifier_node → patrol_mode_node, display_bridge |
| `/nurse_tracker/target` | std_msgs/String | tracker_node → 시각화 |
| `/nurse_tracker/annotated_image` | sensor_msgs/Image | tracker_node(perception) → 시각화 |
| `/obstacle_detector/ground_cloud` | sensor_msgs/PointCloud2 | obstacle_node → RViz |
| `/obstacle_detector/ground_status` | std_msgs/String | obstacle_node → safety_gate |
| `/robot6/scan` | sensor_msgs/LaserScan | RPLIDAR → amcl/nav2/mission_manager |
| `/robot6/odom` · `/robot6/battery_state` · `/robot6/dock_status` | nav_msgs/Odometry · sensor_msgs/BatteryState · irobot_create_msgs/DockStatus | Create3 → 구독자 |
| `/robot6/amcl_pose` · `/robot6/map` | geometry_msgs/PoseWithCovarianceStamped · nav_msgs/OccupancyGrid | AMCL/map_server → Nav2 |
| `/robot6/oakd/rgb/*` · `/robot6/oakd/stereo/*` | sensor_msgs/Image·CompressedImage·CameraInfo | OAK-D → 인지 |

### 6.3 서비스 (요청/응답)
| 서비스 | 타입 | server ← client |
| --- | --- | --- |
| `/robot6/db/get_prescription` | medi_interfaces/GetPrescription | prescription_server ← identifier_node(PatientValidator) |
| `/robot6/db/list_rooms` | medi_interfaces/ListRooms | rooms_server ← patrol_mode_node |
| `/robot6/start_tracking` | std_srvs/Trigger | tracker_node ← mission_manager/웹 |

### 6.4 액션 (goal·feedback·result)
| 액션 | 타입 | server ← client |
| --- | --- | --- |
| `/robot6/navigate_to_pose` | nav2_msgs/NavigateToPose | Nav2 bt_navigator ← nav_executor·patrol_mode·dashboard |
| `/robot6/dock` · `/robot6/undock` | irobot_create_msgs/action/Dock·Undock | Create3 ← nav_executor·mission_executor·dashboard |

### 6.5 Firebase RTDB 경로 (ROS 아님)
| 경로 | 용도 |
| --- | --- |
| `robot6/mission_pool` | 미션 큐(웹→로봇) + 상태(로봇→웹) — action·params·status·ts |
| `robot6/cmd` | **모드 명령(start/stop/clear, mode)** — db_node가 mission_request로 즉시 중계(큐 우회) |
| `robot6/mission_status` · `robot6/mission_log` | db_node 하트비트 · 종료 아카이브 |
| `patients/{pid}/{info,injections,intake,visits,vitals}` | 환자 데이터·문진·생체징후·약품 |
| `rooms` · `targets` | 병실 waypoint · goto 프리셋(ninety 좌표) |
| `intake_pending` · `display/current_patient` · `ocr/latest` · `{src}/alerts` · `telemetry` | 환자 자가문진·디스플레이·OCR·알림·텔레메트리 |

> **medi_interfaces 선정의·미결선**(integration_todoList 참고): srv `GetOcrResult·ScanMedicine·VerifyMedicine·ScanPatient·StartMedication·StartPatrol·MoveHome·UpdateVisitStatus`, msg `MedicineInfo·PatientInfo·RobotState·TargetBBox`.
> 빌트인(외부): `depthai_ros_driver`(OAK-D) · `rplidar_ros` · `turtlebot4_node` · `nav2_*` · `irobot_create_msgs`.
