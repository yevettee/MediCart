# MediCart 시스템 아키텍처 다이어그램 (drawio) — 설계

- **작성일**: 2026-06-09
- **목표**: `SystemArchitectureDiagram_MASTER_VERSION.pdf`(HERABot) 급의 고밀도·정교한 **MediCart** 시스템 아키텍처를 drawio로 작도
- **도구**: drawio MCP (`drawio-mcp-server`, editor :3030) — `import-diagram(format:xml, mode:new-page)`로 mxGraphModel 주입, `export-diagram`로 SVG/PNG 저장
- **콘텐츠 출처**: `docs/architecture/05_mermaid_architecture.md`(검증된 MediCart 아키텍처)

## 확정 결정
- **로봇 표현**: robot6 상세 + robot3 주석(동일 구조, ns=robot3)
- **색상**: 역할별 컬러코딩(🟨orch · 🟪srv · 🟩인지/모드 · 🟦nav · ⬜HW · 청록 웹 · 🟧RTDB)
- **범위**: 코어 메가시트 = 배치 + 미션 오케스트레이션 + mode_arbiter + 인지노드 전부 + 상태머신 2개 + topic/srv/action·RTDB 배선 + 범례·네트워크. **인지노드 5개 전부, 상태머신 2개 포함.** 시나리오 플로우차트는 제외.

## 범례 규칙
- **노드 모양**: 프로세스=둥근 사각, 결정=다이아몬드, 토픽/IO=평행사변형(작은 글씨), 터미네이터=스타디움, 컨테이너=스윔레인.
- **엣지=통신종류**: topic 실선(→) · service 점선(⇢) · action 굵은선(⟹, strokeWidth 3) · RTDB 회색 점선(라벨 RTDB).
- **역할 색 스타일**
  - orch `fillColor=#fde68a;strokeColor=#b45309`
  - srv `fillColor=#ddd6fe;strokeColor=#6d28d9`
  - 인지/모드 `fillColor=#bbf7d0;strokeColor=#15803d`
  - nav `fillColor=#bfdbfe;strokeColor=#1d4ed8`
  - HW `fillColor=#e5e7eb;strokeColor=#374151`
  - 웹 `fillColor=#ccfbf1;strokeColor=#0f766e`
  - RTDB `shape=cylinder3;fillColor=#fef3c7;strokeColor=#b45309`

## 레이아웃 (세로형 메가시트 · 좌중앙 배치열 + 우측 상태머신/범례열)
1. **사용자 + PC3 웹**(상단): 브라우저 →HTTPS/cloudflared→ PC3[Next.js :3000 → Flask :5000·RBAC].
2. **RTDB 버스 밴드**: mission_pool · cmd(큐우회) · patients/rooms/targets/display/ocr/telemetry(실린더). 웹⇢RTDB⇢db_node.
3. **PC2 robot6 운영 스택**(대형 스윔레인): db_node(orch)→mission_manager(orch, 내부 mode_arbiter·nav_executor·mission_executor·MissionSequencer) · prescription/rooms(srv) · identifier·patrol_mode·tracker·obstacle·display_bridge(인지/모드) · Nav2·AMCL·map_server(nav). 좌측 PC1/robot3 주석.
4. **mode_arbiter 패널**: mode/*/cmd_vel·status + obstacle ground_status → 우선순위 선택 + safety_gate(lidar 0.30m/depth 0.20m) → cmd_vel → Create3.
5. **상태머신 2패널**(우측열): ①미션 라이프사이클(pending→sent→running→done/failed/preempted, 15s START_TIMEOUT·완료 무제한) ②모드 중재(idle→active→preempted/lost, 우선순위 goto7>intake5>round4>errand3>guide2>patrol1).
6. **robot6 turtlebot4 스택**(하단 스윔레인): turtlebot4_bringup(rsp/rplidar/depthai/diag/HMI)·navigation · HW[Create3·RPLIDAR A1M8·OAK-D-Pro·26Wh·Status LED]. robot3 주석.
7. **마진 토픽 배선**: 레인 간 평행사변형 IO 노드 + 교차 엣지(scan·oakd/rgb·oakd/stereo·odom·battery·dock_status·cmd_vel·patient_identified·ground_status 등).
8. **범례 + 네트워크 박스**: ROS2 Humble·WiFi6 AP·Gigabit Switch·FastDDS Discovery :11811 DOMAIN 6·cloudflared.

## 진행 방식
승인된 설계 → mxGraphModel XML 작성 → `import-diagram` 주입 → `export-diagram(svg)` 육안 검증(겹침/교차/오타) → 국소 수정 반복 → 최종 SVG/PNG를 `docs/architecture/diagrams/`에 저장. 단일 시각 산출물이라 TDD 플랜 없이 작도→검증→반복.
