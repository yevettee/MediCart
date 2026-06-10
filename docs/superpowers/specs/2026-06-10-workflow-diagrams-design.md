# 워크플로우 아키텍처 다이어그램 — 간호사 투약 · 순회 문진 (설계)

- 작성일 2026-06-10 · 산출물: `docs/architecture/diagrams/*.drawio` (mxGraph XML, diagrams.net/VSCode drawio로 열람·편집)
- 목적: 두 메인 시나리오의 **워크플로우 진행**을 따라가며 ROS 노드·노드간 통신(토픽/서비스/액션)·패키지 내 `.py` 사용처를 상세 표현. 전체 아키텍처가 아니라 **워크플로우 중심**.
- drawio MCP 미연결 → `.drawio` XML을 생성기 스크립트(`gen_workflow_drawio.py`)로 직접 작성. 좌표를 계산 배치해 라벨/박스 겹침 없음.

## 레이아웃 규약 (겹침 방지)
- 세로 레인(컬럼) = 서브시스템, 위→아래 = 시간 흐름. 레인 폭 270 / 간격 300px, 박스 234px, 단계 간격 140px.
- 노드 박스: 굵은 제목 + 그 아래 `· 사용 .py / 핵심 동작` 목록. 통신 = 직교 화살표 + 라벨(토픽/서비스/액션 명 + 메시지 타입).
- 레인 배경 색상으로 서브시스템 구분, 우상단 범례(메시지 종류·ns 약어 robot3/robot6).
- 분할: 시나리오별 2장 + 공통 1장 (정보량 과다로 단일 캔버스 겹침 방지).

## 다이어그램 1 — 간호사 투약 (robot6, nurse_cart_mission)
`medicart-nurse-cart-workflow.drawio`. 레인: Web(Next/Flask) │ RTDB │ db_bridge │ mission_manager │ nurse_tracker/mode │ nav/Create3.
흐름: 홈 버튼(startRound) → `/api/nurse_cart/start`(push_mission) → RTDB `robot6/mission_pool` → `db_node`(mission_queue·firebase_client) → `/robot6/mission_request` → `MissionManagerNode` → `NurseCartSequencer`(undock→약품실 goto→WAIT_OCR→추종→round→복귀). 핸드셰이크: 처치실 `/ocr`→RTDB `nurse_cart/ocr_done`→db_node→`/robot6/nurse_cart/ocr_done`→signal_ocr_done; `round_done` 동일 경로. 추종: `tracker_node`(perception→yolo_helper, follow_control 85cm)→`/robot6/mode/nurse_tracker/cmd_vel`→`ModeArbiter`(cmd_vel 단독소유)→`/robot6/cmd_vel`. `NavExecutor`(navigate_to_pose/dock/undock). `ocr_detector`(medicine_checker/text_cleaner/engines) 보조 표시.

## 다이어그램 2 — 순회 문진 (robot3, patrol_intake_mission)
`medicart-patrol-intake-workflow.drawio`. 레인: Web │ RTDB │ db_bridge │ mission_manager │ patient_identifier/rooms │ nav/Create3.
흐름: 홈(RoundsIntakeOverlay) → `/api/patrol/start`(clear+reset+startPatrol{stops,home}) → RTDB `robot3/mission_pool` → db_node → `/robot3/mission_request` → `PatrolIntakeSequencer`(undock→정차 루프→복귀). 정차 루프: NavExecutor goto → 도착(`robot3/patrol/phase=arrived`) → 웹 getPatrolPhase → QR 배정환자 검증(verifyIdentify/getPatient) → 문진 submit/부재중 → `/api/patrol/advance` → RTDB → `/robot3/patrol/intake_done` → 다음 stop. `rooms_server`(ListRooms·room_lookup), `patient_identifier`(identifier_node·patient_validator·PersonDetector) ROS측 식별 옵션 표시.

## 다이어그램 3 — 공통 인프라 (양 시나리오 공유)
`medicart-common-infra.drawio`. 레인: Web │ RTDB 스키마 │ db_bridge(6 노드) │ mission_manager/robot.
RTDB 중심 배관: `amr_bridge`(텔레메트리→RTDB), `db_node`(mission_pool↔mission_request + feedback + 3 핸드셰이크 브리지), `camera_bridge`(annotated/rgb/depth), `prescription_server`(GetPrescription), `rooms_server`(ListRooms), `display_bridge`. Web(Flask app.py 라우트·auth RBAC·SSE, Next.js lib/api·auth·telemetry). `ModeArbiter` cmd_vel 단독소유 + `NavExecutor` + Create3/AMR. firebase_client.FirebaseClient 공유.

## 검증
- 생성기 출력 XML이 well-formed(파싱) + drawio 열람 가능. 노드/엣지 좌표 비겹침(레인 그리드).
- 내용 정확성: 토픽/서비스/액션·import는 코드(grep) 기준.
