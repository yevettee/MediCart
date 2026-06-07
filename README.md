# MediCart

ROS2 기반 병원 순회 로봇 시스템입니다.

간호사 추종, Nav2 자율주행, OAK-D 카메라 OCR 약품 검증, Firestore 처방 연동 기능을 제공합니다.

## sunghyun 브랜치에서 추가된 내용

이 브랜치는 기존 `main`에 없던 `/robot6`용 웹 대시보드를 추가한 브랜치입니다.

쉽게 말하면, 노트북 브라우저에서 지도를 보고 버튼을 누르면 robot6가 움직이고,
카메라 화면과 로그도 한 화면에서 볼 수 있게 만든 것입니다.

## main과 다른 점

- `dashboard` 패키지에 웹 화면이 들어갔습니다.
- 지도 파일 `ninety.yaml`, `ninety.pgm`, `ninety.png`가 dashboard 안에 들어갔습니다.
- 브라우저에서 지도를 클릭하면 robot6가 그 위치로 이동합니다.
- `Docking Station` 버튼을 누르면 도킹 스테이션으로 간 뒤 자동으로 dock 합니다.
- robot6가 dock 상태일 때 다른 위치를 누르면 먼저 undock 하고 이동합니다.
- RGB-D 카메라 화면을 브라우저에서 볼 수 있습니다.
- RGB-D 화면을 캡쳐해서 저화질 `.jpg` 파일로 저장할 수 있습니다.
- Dock, Undock, ROS Restart, Reboot, Shutdown 버튼이 생겼습니다.
- 실행 방법과 구조 설명이 `medicart_ws/src/dashboard/README.md`에 자세히 적혀 있습니다.
- 전체 시스템 구조 문서가 `docs/architecture/05_multi_robot_system_architecture.md`에 추가됐습니다.

## 가능한 기능

- 2D 지도 보기
- robot6 현재 위치 보기
- 지도 위 목표 지점 클릭해서 이동시키기
- 미리 만든 위치 버튼 클릭해서 이동시키기
- 이동 로그 실시간 보기
- RGB 카메라 보기
- Depth 카메라 보기
- RGB-D 캡쳐 저장 켜기/끄기
- Dock 하기
- Undock 하기
- TurtleBot4 서비스 재시작하기
- robot6 재부팅하기
- robot6 종료하기

## 구현 방식

- `dashboard_node.py`가 ROS2 node입니다.
- 같은 파일 안에서 작은 HTTP 서버도 같이 켭니다.
- 브라우저 화면은 `medicart_ws/src/dashboard/dashboard/web/static/` 안에 있습니다.
- 지도 이미지는 `medicart_ws/src/dashboard/dashboard/web/maps/` 안에 있습니다.
- 브라우저와 ROS2 node는 HTTP API와 SSE로 통신합니다.
- SSE는 로그, 로봇 위치, 카메라 이미지를 실시간으로 보내는 통로입니다.
- 이동은 Nav2 `NavigateToPose` action을 사용합니다.
- 도킹과 언도킹은 Create3 `Dock`, `Undock` action을 사용합니다.
- 카메라는 compressed RGB topic과 compressed depth topic을 받습니다.
- 캡쳐는 브라우저가 화면 이미지를 작게 줄이고 JPEG 품질을 낮춘 뒤 서버로 보냅니다.

## 기본 ROS2 이름

```text
Nav2 action: /robot6/navigate_to_pose
Dock action: /robot6/dock
Undock action: /robot6/undock
Dock status: /robot6/dock_status
AMR pose: /robot6/amcl_pose
RGB topic: /robot6/oakd/rgb/image_raw/compressed
Depth topic: /robot6/oakd/stereo/image_raw/compressedDepth
```

## 실행 명령어

### Terminal 1

```bash
loc 6 ~/MediCart/medicart_ws/maps/ninety.yaml
```

### Terminal 2

```bash
rv 6
```

### Terminal 3

```bash
nav 6
```

### Terminal 4

```bash
cd ~/MediCart/medicart_ws
source install/setup.bash
ros2 run dashboard dashboard_node --ros-args -p action_name:=/robot6/navigate_to_pose -p port:=8080 -p capture_dir:=$HOME/MediCart/medicart_ws/src/dashboard/captures
```

### Browser

```text
http://127.0.0.1:8080
```

## 꼭 해야 하는 것

RViz가 뜨면 `2D Pose Estimate`로 로봇의 처음 위치를 찍어야 합니다.

이걸 안 하면 robot6가 자기 위치를 몰라서 이동을 못 합니다.

## 캡쳐 저장

캡쳐 버튼은 처음에는 꺼져 있습니다.

켜면 RGB와 Depth가 따로 저장됩니다.

```text
20260607_142125_649_rgb.jpg
20260607_142125_649_depth.jpg
```

저장 위치는 위 실행 명령어 기준으로 아래입니다.

```text
~/MediCart/medicart_ws/src/dashboard/captures
```
