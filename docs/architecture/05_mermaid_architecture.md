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
