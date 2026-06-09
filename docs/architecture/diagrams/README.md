# MediCart — 아키텍처 다이어그램

`.understand-anything` 코드 분석(commit `a2e555f`) 기반으로 정리한 **시각 다이어그램**.
각 파일은 의존성 없는 자기완결 HTML이며 브라우저에서 바로 열린다. 우측 상단 `⋯` →
📋 Copy / 🖼️ PNG / 📄 PDF 로 내보낼 수 있다.

| # | 파일 | 내용 |
| --- | --- | --- |
| 00 | [00_system_overview.html](00_system_overview.html) | **시스템 아키텍처** — 기능 단위 계층(Web → Firebase 버스 → 로봇 ROS2) |
| 01 | [01_node_map.html](01_node_map.html) | **ROS2 노드 맵** — 주요 노드별 역할·입력(IN)/출력(OUT) |
| 02 | [02_workflows.html](02_workflows.html) | **주요 기능 워크플로우** — 미션 파이프라인 + 시나리오 A/B |

## 핵심 요약

- **3계층**: Web(PC3, ROS 노드 없음) → **Firebase = 유일한 크로스-PC 버스** → 로봇 ROS2(각 AMR PC).
- **미션 경로**: 웹 버튼 → RTDB `mission_pool` → `db_node` → `/mission_request` → `mission_manager`
  (2-lane: system / goto / mode) → Nav2·dock/undock·cmd_vel.
- **단일 소유 원칙**: `mission_manager`만 `/cmd_vel`·Nav2를 소유하고 우선순위 선점 + 전방 안전 게이트로 중재.
- **시나리오 A**(순찰+문진): 신원확인(YOLO+QR) → 웹 문진표 → 병실 반복.
- **시나리오 B**(투약): 간호사 추종 → 약품 OCR 검증.

> 텍스트 상세(토픽/서비스/스키마)는 상위 폴더의 `01_system_architecture.md` ~ `04_db_schema.md` 참고.
