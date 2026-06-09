# MediCart Documentation

병원 순회 로봇(MediCart)의 아키텍처 문서. 에이전트·개발자는 아래 4개 문서를 목적에 맞게 읽는다.

## Documents

| Document | File | Focus |
| --- | --- | --- |
| System architecture | [01_system_architecture.md](01_system_architecture.md) | 미션 흐름, 레이어, **패키지 역할**, **데이터 흐름** |
| ROS2 packages | [02_ros2_packages.md](02_ros2_packages.md) | 패키지별 책임, **입력/출력**, launch |
| ROS2 interfaces | [03_ros2_interfaces.md](03_ros2_interfaces.md) | **Builtin I/F**, `medi_interfaces`, 토픽·서비스·액션 **소유 패키지** |
| DB schema | [04_db_schema.md](04_db_schema.md) | Firestore/SQL 데이터 모델 |
| 🧜 Mermaid 아키텍처 | [05_mermaid_architecture.md](05_mermaid_architecture.md) | **mermaid** — 전체 시스템·워크플로우·**주 기능별 노드+토픽/서비스/액션 명칭** (integration 기준) |
| 🖼️ Diagrams | [diagrams/](diagrams/README.md) | **시각 다이어그램**(HTML) — 시스템 아키텍처·노드 맵·워크플로우 |

## Suggested reading order

1. [01_system_architecture.md](01_system_architecture.md) — 전체 그림
2. [03_ros2_interfaces.md](03_ros2_interfaces.md) — 센서·Nav2·타입 경계 (builtin 우선)
3. [02_ros2_packages.md](02_ros2_packages.md) — 구현 패키지별 I/O
4. [04_db_schema.md](04_db_schema.md) — 처방 데이터