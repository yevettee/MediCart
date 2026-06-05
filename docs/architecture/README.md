# MediCart Documentation

병원 순회 로봇(MediCart)의 아키텍처 문서. 에이전트·개발자는 아래 5개 문서를 목적에 맞게 읽는다.

## Documents

| Document | File | Focus |
| --- | --- | --- |
| Multi-robot system architecture | [05_multi_robot_system_architecture.md](05_multi_robot_system_architecture.md) | `/robot3`, `/robot6` 운영 구조, 노드 생성, Topic/Service/Action 계약 |
| System architecture | [01_system_architecture.md](01_system_architecture.md) | 미션 흐름, 레이어, **패키지 역할**, **데이터 흐름** |
| ROS2 packages | [02_ros2_packages.md](02_ros2_packages.md) | 패키지별 책임, **입력/출력**, launch |
| ROS2 interfaces | [03_ros2_interfaces.md](03_ros2_interfaces.md) | **Builtin I/F**, `medi_interfaces`, 토픽·서비스·액션 **소유 패키지** |
| DB schema | [04_db_schema.md](04_db_schema.md) | Firestore/SQL 데이터 모델 |

## Suggested reading order

1. [05_multi_robot_system_architecture.md](05_multi_robot_system_architecture.md) — `/robot3`, `/robot6` 전체 계약
2. [01_system_architecture.md](01_system_architecture.md) — 기존 단일 플랫폼 전체 그림
3. [03_ros2_interfaces.md](03_ros2_interfaces.md) — 센서·Nav2·타입 경계 (builtin 우선)
4. [02_ros2_packages.md](02_ros2_packages.md) — 구현 패키지별 I/O
5. [04_db_schema.md](04_db_schema.md) — 처방 데이터
