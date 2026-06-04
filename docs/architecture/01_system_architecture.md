# MediCart System Architecture

병원 순회 로봇의 **미션 흐름**, **레이어 구조**, **패키지 역할**, **데이터 입출력**을 정리한다. ROS2 토픽·서비스 상세는 [03_ros2_interfaces.md](03_ros2_interfaces.md), 패키지별 책임·디렉터리는 [02_ros2_packages.md](02_ros2_packages.md)를 참고한다.

## 패키지 역할 요약

| 패키지 | 역할 | 주요 입력 | 주요 출력 |
| --- | --- | --- | --- |
| `dashboard` | 운영자 UI·미션 명령 | `/robot6/robot_state` | `/robot6/start_tracking`, `/robot6/scan_*`, `/robot6/move_home`, `/robot6/emergency_stop` |
| `mission_manager` | 상태기·처방 세션·Nav2/도킹 조율 | `/robot6/target_pose`, `/robot6/emergency_stop`, 서비스 요청 | `/robot6/robot_state`, `/robot6/navigate_to_pose`, `/robot6/undock`, `/robot6/dock` |
| `nurse_tracker` | 간호사 추적 (호스트 추론, OCL+ReID) | `/robot6/oakd/image_raw`, `/robot6/oakd/depth_image`, `/tf` | `/robot6/target_pose`, `/robot6/target_bbox` |
| `obstacle_detector` | pure-vision depth 추론 → 장애물 point cloud (모델 미확정) | `/robot6/oakd/image_raw` | `/robot6/vision_obstacles` |
| `ocr_detector` | 약품 라벨 OCR | `/robot6/oakd/image_raw` | `/robot6/ocr/get_result` (service) |
| `scanner` | OCR+처방 step 검증 | `/robot6/scanner/verify_medicine` | `/robot6/ocr/get_result`, `/robot6/db/verify_medicine` |
| `db_bridge` | Firestore 처방·검증 | `/robot6/db/get_prescription`, `/robot6/db/verify_medicine` | patient/medicines |
| `medi_bringup` | launch·Nav2 yaml 통합 | — | 전 노드 기동 |
| `medi_interfaces` | 커스텀 msg/srv 정의 | — | 타입만 제공 |

외부(빌트인): `depthai_ros_driver`(Pi), `rplidar_ros`, `turtlebot4_node`, Nav2, Create3 dock/undock — [03_ros2_interfaces.md § Builtin](03_ros2_interfaces.md#builtin--external-interfaces).

## 미션 전체 흐름

```mermaid
flowchart TD
    docked["Station 도킹"]
    undock["Undock /robot6/undock"]
    follow["Following: /robot6/target_pose → Nav2"]
    arrive["호실 도착"]
    scan["/robot6/scan_patient → /robot6/scan_medicine 반복"]
    returnHome["/robot6/navigate_to_pose station"]
    dock["Dock /robot6/dock"]
    done["도킹 완료"]

    docked --> undock --> follow --> arrive --> scan --> returnHome --> dock --> done
```

`mission_manager` 상태: `IDLE → UNDOCK → FOLLOW → SCAN → RETURN → DOCK → IDLE`

## 레이어와 데이터 흐름

```mermaid
flowchart TB
    subgraph command [Command]
        dash["dashboard"]
        mm["mission_manager"]
        dash -->|services| mm
    end

    subgraph perception [Perception — host 추론]
        oakd["OAK-D raw via Pi"]
        nt["nurse_tracker"]
        od["obstacle_detector"]
        ocr["ocr_detector"]
        lidar["LiDAR /robot6/scan"]
        oakd -->|/robot6/oakd/image_raw depth_image| nt
        oakd -->|/robot6/oakd/image_raw| od
        oakd -->|/robot6/oakd/image_raw| ocr
    end

    subgraph nav [Navigation]
        nav2["Nav2"]
        costmap["costmap: /robot6/scan + /robot6/vision_obstacles"]
        nav2 --- costmap
    end

    subgraph robot [Robot]
        tb["TurtleBot4 / Gazebo"]
    end

    subgraph data [Data]
        db["db_bridge"]
        sc["scanner"]
        mm --> sc
        sc --> ocr
        sc --> db
        mm --> db
    end

    mm -->|/robot6/navigate_to_pose undock dock| nav2
    nt -->|/robot6/target_pose| mm
    od -->|/robot6/vision_obstacles| costmap
    lidar --> costmap
    nav2 -->|/robot6/cmd_vel| tb
    mm -->|/robot6/robot_state| dash
```

- **Command**: dashboard만 operator-facing service 발행 (`/robot6/start_tracking`, `/robot6/scan_*`, `/robot6/move_home`, `/robot6/cancel_mission`); Nav2/action은 mission_manager만 호출.
- **Perception**: OAK-D는 VPU 추론 없이 raw만 Pi→호스트. 추론은 `nurse_tracker`(OCL+ReID), `obstacle_detector`(pure-vision depth, 모델 미확정), `ocr_detector`.
- **Navigation**: `/robot6/cmd_vel` 단일 소스(Nav2). emergency 시 mission_manager가 `Twist(0)` 직접 발행.
- **Data**: `db_bridge`는 수직 독립; `scanner`·`mission_manager`가 처방 조회·검증에 사용.

## OAK-D → 호스트 데이터 경로

```mermaid
flowchart LR
    oakd["OAK-D Pro"]
    pi["Raspberry Pi\ndepthai_ros_driver"]
    host["Host PC"]
    nt["nurse_tracker"]
    od["obstacle_detector"]
    ocr["ocr_detector"]

    oakd -->|USB| pi
    pi -->|/robot6/oakd/image_raw /robot6/oakd/depth_image| host
    host --> nt
    host --> od
    host --> ocr
```

## 모드별 시퀀스

### Following Mode

```mermaid
sequenceDiagram
    participant D as dashboard
    participant M as mission_manager
    participant N as nurse_tracker
    participant O as obstacle_detector
    participant Nav as Nav2
    participant Cam as OAK-D via Pi

    D->>M: /robot6/start_tracking
    M->>M: UNDOCK → FOLLOW
    M->>N: /robot6/tracker/reset

    loop every frame
        Cam->>N: /robot6/oakd/image_raw depth_image
        Cam->>O: /robot6/oakd/image_raw
        N->>M: /robot6/target_pose
        O->>Nav: /robot6/vision_obstacles
    end

    loop 1-5Hz
        M->>Nav: cancelTask /robot6/navigate_to_pose
    end

    M->>D: /robot6/robot_state FOLLOW
```

### Scan Patient

```mermaid
sequenceDiagram
    participant D as dashboard
    participant M as mission_manager
    participant B as db_bridge

    D->>M: /robot6/scan_patient
    M->>B: /robot6/db/get_prescription
    B-->>M: patient medicines admin_order
    M->>M: session current_step=0
    M-->>D: medicines total_steps
```

`medicines[]` 순서 = `admin_order` 오름차순(투약 순서).

### Scan Medicine (반복)

```mermaid
sequenceDiagram
    participant D as dashboard
    participant M as mission_manager
    participant S as scanner
    participant O as ocr_detector

    D->>M: /robot6/scan_medicine
    M->>S: /robot6/scanner/verify_medicine step_index
    S->>O: /robot6/ocr/get_result
    O-->>S: cleaned_text
    alt match
        M->>M: current_step++
        M->>D: success
    else mismatch
        M->>D: order/medicine error
    end
```

현재 `current_step`의 expected 약만 검증.

### Return Home

```mermaid
sequenceDiagram
    participant D as dashboard
    participant M as mission_manager
    participant Nav as Nav2
    participant TB as TurtleBot4

    D->>M: /robot6/move_home
    M->>Nav: /robot6/navigate_to_pose station
    Nav-->>M: goal reached
    M->>TB: /robot6/dock
    M->>D: /robot6/robot_state IDLE
```

### Emergency Stop

```mermaid
flowchart TD
    D["dashboard /robot6/emergency_stop"]
    M["mission_manager"]
    Nav["Nav2 cancelTask"]
    Z["/robot6/cmd_vel zero"]
    M --> Nav
    M --> Z
    M -->|state IDLE| D
```
