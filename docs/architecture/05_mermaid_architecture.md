# MediCart Architecture (Mermaid · HERA급)

> 통합 브랜치(`integration` = main ↔ jaehoon) 기준. 참조 수준: HERABot System Architecture Diagram.
> namespace 기본 `robot6` — **robot3(AMR1)도 PC1에서 동일 구조로 동작**(노드·토픽 네임스페이스만 `robot3`).
> 구성: §1 마스터 오버뷰 → §2 컴퓨트·네트워크 → §3 ROS 노드 그래프 → §4 상태머신 → §5 시나리오 플로우 → §6 인터페이스 표.
> 텍스트 상세는 `01_system_architecture.md`~`04_db_schema.md`, 시각본은 `diagrams/` 참고.

---

## 1. 마스터 오버뷰 (전체 배치)

```mermaid
graph TD
  USER["운영자·간호사·환자<br/>브라우저"] -->|"HTTPS / cloudflared"| FE

  subgraph PC3["PC3 — 웹 (ROS 노드 없음)"]
    FE["Next.js :3000<br/>/console /map /patients /intake /ocr /display /qr"]
    BE["Flask :5000<br/>REST + SSE · RBAC(admin/staff/patient)"]
    FE -->|"/api/* · /api/stream(SSE)"| BE
  end

  subgraph FB["Firebase RTDB — 크로스-PC 버스"]
    POOL["robot6/mission_pool<br/>+ mission_status / mission_log"]
    DATA["patients · rooms · targets<br/>intake_pending · display · ocr · telemetry · alerts"]
  end

  subgraph PC1["PC1 — robot3 전담"]
    R3["loc3 · nav3 · db_bridge · mission_manager<br/>nurse_tracker · obstacle_detector"]
  end

  subgraph PC2["PC2 — robot6 전담 (FastDDS Discovery :11811 · DOMAIN 6)"]
    DB["db_node<br/>(db_bridge)"]
    MM["mission_manager_node<br/>(중재 허브 · cmd_vel 단독소유)"]
    SRV["prescription_server · rooms_server · display_bridge"]
    PERC["인지: identifier_node(A) · tracker_node(B) · obstacle_node"]
    NAV["Nav2 + AMCL + map_server"]
  end

  subgraph AMR["robot6 (turtlebot4 · RPi4B)"]
    HW["Create3 · OAK-D-Pro · RPLIDAR A1M8"]
  end

  BE <-->|"firebase-admin"| POOL
  BE <-->|"firebase-admin"| DATA
  DB <-->|"listen / write"| POOL
  DB -->|"/robot6/mission_request · mission_cancel"| MM
  MM -->|"/robot6/mission_feedback"| DB
  SRV <-->|"RTDB"| DATA
  MM --> PERC
  MM -->|"navigate_to_pose · dock/undock"| NAV
  MM -->|"/robot6/cmd_vel"| HW
  NAV --> HW
  HW -->|"/scan /oakd/* /odom /battery_state /dock_status"| PERC
  HW -. "telemetry" .-> DB
  PC1 <-->|"firebase-admin"| FB
```

> robot3(AMR1)은 PC1에서 위 robot6 스택과 동일하게 동작하며 네임스페이스만 `robot3`.

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
      APP["앱 패키지 — db_bridge · mission_manager · nurse_tracker · obstacle_detector · medi_interfaces"]
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

## 3. ROS 노드 그래프 (토픽/서비스/액션 — name + type + 값)

### 3.1 미션 오케스트레이션 — db_node ↔ mission_manager

```mermaid
graph LR
  POOL[("RTDB robot6/mission_pool")] -->|"listen"| DB["db_node"]
  DB -->|"status/progress write"| POOL
  DB -->|"/robot6/mission_request<br/>std_msgs/String {id,action,params,mode}"| MM["mission_manager_node"]
  DB -->|"/robot6/mission_cancel<br/>std_msgs/String {id,reason} (선점)"| MM
  MM -->|"/robot6/mission_feedback<br/>std_msgs/String {id,status,detail,ts}"| DB
  MM -->|"/robot6/robot_mode<br/>std_msgs/String"| MON["모니터/웹"]
  MM -->|"/robot6/cmd_vel<br/>geometry_msgs/Twist (단독소유)"| C3["Create3 base"]
  SCAN["RPLIDAR"] -->|"/robot6/scan<br/>sensor_msgs/LaserScan"| MM
  DS["Create3"] -->|"/robot6/dock_status<br/>irobot_create_msgs/DockStatus"| MM
  MM -. "내부" .-> ARB["mode_arbiter"]
  MM -. "내부" .-> NEX["nav_executor"]
  MM -. "내부" .-> MEX["mission_executor"]
  MM -. "내부" .-> SEQ["MissionSequencer (patrol_mission)"]
  NEX -->|"/robot6/navigate_to_pose<br/>nav2_msgs/NavigateToPose · frame_id='map'"| NAV2["Nav2 bt_navigator"]
  NEX -->|"/robot6/dock · /robot6/undock<br/>irobot_create_msgs/action/Dock·Undock"| C3
  MEX -->|"subprocess: ros2 action send_goal / ssh"| C3
```

### 3.2 모드 중재 — mode_arbiter (REACTIVE 계약)

```mermaid
graph LR
  ARB["mode_arbiter<br/>(mission_manager 내부)"] -->|"/robot6/mode/{mode}/set<br/>std_msgs/String (latched) {active,params}"| M["mode node (예: round)"]
  M -->|"/robot6/mode/{mode}/cmd_vel<br/>geometry_msgs/Twist"| ARB
  M -->|"/robot6/mode/{mode}/status<br/>std_msgs/String {state}"| ARB
  OB["obstacle_node"] -->|"/obstacle_detector/ground_status<br/>std_msgs/String"| ARB
  ARB -->|"우선순위 선택 + safety_gate (lidar 0.30m / depth 0.20m)"| OUT["/robot6/cmd_vel<br/>geometry_msgs/Twist"]
```

### 3.3 시나리오 A 인지 — identifier_node + db_bridge

```mermaid
graph LR
  OAK["OAK-D"] -->|"/robot6/oakd/rgb/image_raw<br/>sensor_msgs/Image"| ID["identifier_node<br/>(YOLO + QR + 병실검증)"]
  PAT["patrol_mode_node"] -->|"/robot6/identify/start<br/>std_msgs/String"| ID
  ID -->|"/robot6/patient_identified<br/>medi_interfaces/PatientIdentified"| PAT
  ID -->|"/robot6/patient_identified"| DBR["display_bridge → RTDB display/current_patient"]
  ID -->|"/robot6/db/get_prescription<br/>medi_interfaces/GetPrescription"| PS["prescription_server"]
  PS -->|"PatientInfo + MedicineInfo[]"| ID
  PS <-->|"RTDB patients/rooms"| RTDB[("Firebase RTDB")]
  PAT -->|"/robot6/db/list_rooms<br/>medi_interfaces/ListRooms"| RS["rooms_server"]
  RS -->|"room_ids/xs/ys/yaws"| PAT
  PAT -->|"/robot6/navigate_to_pose<br/>nav2_msgs/NavigateToPose"| NAV2["Nav2"]
```

### 3.4 시나리오 B 추종 — nurse_tracker (round)

```mermaid
graph LR
  OAK["OAK-D"] -->|"/robot6/oakd/rgb/image_raw/compressed<br/>sensor_msgs/CompressedImage"| TR["tracker_node<br/>(YOLO11s best.pt + ByteTrack)"]
  OAK -->|"/robot6/oakd/stereo/image_raw/compressedDepth<br/>sensor_msgs/CompressedImage"| TR
  CALL["mission_manager / 웹"] -->|"/robot6/start_tracking<br/>std_srvs/Trigger"| TR
  TR -->|"/robot6/mode/round/cmd_vel<br/>geometry_msgs/Twist"| ARB["mode_arbiter"]
  TR -->|"/robot6/mode/round/status<br/>std_msgs/String"| ARB
  TR -->|"/nurse_tracker/target<br/>std_msgs/String · /nurse_tracker/annotated_image<br/>sensor_msgs/Image"| VIS["시각화/디버그"]
  ARB -. "/robot6/mode/round/set" .-> TR
```

### 3.5 장애물 안전 — obstacle_detector

```mermaid
graph LR
  OAK["OAK-D stereo"] -->|"/robot6/oakd/stereo/image_raw/compressedDepth<br/>sensor_msgs/CompressedImage"| OB["obstacle_node<br/>(depth→지면 평면 SVD)"]
  OAK -->|"/robot6/oakd/stereo/camera_info<br/>sensor_msgs/CameraInfo"| OB
  OB -->|"/obstacle_detector/ground_cloud<br/>sensor_msgs/PointCloud2"| RV["RViz/디버그"]
  OB -->|"/obstacle_detector/ground_status<br/>std_msgs/String"| MM["mission_manager safety_gate"]
```

### 3.6 자율주행 · 하드웨어

```mermaid
graph LR
  RP["RPLIDAR"] -->|"/robot6/scan<br/>sensor_msgs/LaserScan"| AMCL["AMCL (loc)"]
  RP --> NAV2["Nav2"]
  MAP["map_server"] -->|"/robot6/map<br/>nav_msgs/OccupancyGrid"| NAV2
  AMCL -->|"map→odom TF · /robot6/amcl_pose<br/>geometry_msgs/PoseWithCovarianceStamped"| NAV2
  C3["Create3"] -->|"/robot6/odom · /robot6/battery_state · /robot6/dock_status<br/>nav_msgs/Odometry · sensor_msgs/BatteryState · irobot_create_msgs/DockStatus"| SUB["telemetry→RTDB→웹"]
  OAK["OAK-D"] -->|"/robot6/oakd/rgb/* · /robot6/oakd/stereo/*"| PERC["인지 노드들"]
```

## 4. 상태머신

### 4.1 미션 라이프사이클 (db_node 오케스트레이션 — 신규 동작)

```mermaid
stateDiagram-v2
  [*] --> pending : web push (mission_pool)
  pending --> sent : 우선순위→ts 선택 후 mission_request 발행
  sent --> running : accepted/running 수신
  sent --> failed : 15s 내 accepted 미수신 (START_TIMEOUT)
  running --> done : mission_feedback done
  running --> failed : mission_feedback failed
  running --> preempted : 더 높은 우선순위 도착 (현재 폐기·드롭)
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
  idle --> active : start mode (active set 추가)
  active --> preempted_mode : 더 높은 우선순위 모드 활성
  preempted_mode --> active : 상위 모드 종료 → 복귀
  active --> idle : stop/clear 또는 status done/failed
  active --> lost : status 무응답 3s (lost abort)
  lost --> idle
  note right of active
    우선순위: goto 7 (운영자) > intake 5 > round 4 > errand 3 > guide 2 > patrol 1
    REACTIVE 모드: cmd_vel은 safety_gate 통과 (전방 lidar 0.30m / depth 0.20m, 전진만 차단)
  end note
```
