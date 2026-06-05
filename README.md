# MediCart

ROS2 기반 병원 순회 로봇 시스템입니다. 하나의 플랫폼(TurtleBot4 + OAK-D + RPLIDAR)에서 두 가지 시나리오를 운영합니다.

- **시나리오 A — 자율 순찰 + 문진 보조**: Nav2로 병실을 순회하며 환자 재실·신원 확인(YOLO+QR), 웹 문진표 작성, DB 업데이트.
- **시나리오 B — 간호사 투약 보조**: 간호사 추종으로 호실 이동, 처방 로드, OAK-D 카메라 OCR 약품 검증.

공통: Nav2 자율주행, Firestore 처방·환자 데이터 연동. 아키텍처 문서는 [docs/architecture](docs/architecture/README.md) 참고.