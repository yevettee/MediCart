# MediCart

ROS2 기반 병원 순회 로봇 시스템입니다. 동일 플랫폼(TurtleBot4 + OAK-D + RPLIDAR)을 **모드 전환**으로 운영하며, 로봇은 평소 Station에 도킹되어 있고 **관리자 web(dashboard)에서 모드를 선택**해 미션을 시작합니다.

- **시나리오 A — 자율 순찰 + 문진 보조**: Nav2로 병실을 순회하며 환자 재실·신원 확인(YOLO+QR), 웹 문진표 작성, 방문 상태 DB 기록.
- **시나리오 B — 투약 보조**: **(기본)** Nav2 자율주행으로 약 제조실·호실 이동 후 처방 로드·OAK-D 카메라 OCR 약품 검증, **(챌린지)** 간호사 추종 이동.

공통: Nav2 자율주행, Firestore 처방·환자 데이터 연동. 멀티로봇 운용 시 namespace 분리 + Fast DDS Discovery Server. 아키텍처 문서는 [docs/architecture](docs/architecture/README.md) 참고.