# Dashboard 코드리뷰 가이드

내가 구현한 dashboard는 한마디로 **Robot System Monitoring & Control Dashboard**다.

순수 system monitor라기보다는 아래 두 가지가 합쳐진 구조다.

- Monitoring: 로봇 위치, Dock 상태, RGB-D 카메라, 실시간 로그 표시
- Control: 맵 클릭 이동, Dock, Undock, ROS Restart, Reboot, Shutdown

---

## 0. 설명 순서와 파일 여는 순서

코드는 **1번 라인부터 끝까지 읽어 내려가는 방식으로 설명하지 않는다.**  
이 파일들은 `dashboard_node.py` 하나만 해도 길기 때문에, 강사님 앞에서는 "사용자 동작 하나가 코드에서 어떻게 흘러가는지"를 따라가면 된다.

추천 설명 순서:

```text
1. 내가 만든 기능 한 줄 소개
2. 화면 구조(index.html)
3. 브라우저 동작(app.js)
4. Python HTTP endpoint(dashboard_node.py / DashboardRequestHandler)
5. ROS action/topic 연결(dashboard_node.py / DashboardNode)
6. 실시간 로그와 위치/카메라 갱신(EventBroker + SSE)
7. 패키징(setup.py)
```

파일 여는 순서:

```text
1. src/dashboard/dashboard/web/static/index.html
2. src/dashboard/dashboard/web/static/app.js
3. src/dashboard/dashboard/dashboard_node.py
4. src/dashboard/dashboard/web/maps/ninety.yaml
5. src/dashboard/setup.py
6. src/dashboard/dashboard/web/static/styles.css
```

각 파일에서 볼 부분:

| 순서 | 파일 | 볼 부분 | 설명할 말 |
| --- | --- | --- | --- |
| 1 | `index.html` | `topbar`, `map-card`, `camera-card`, `log-card` | 화면이 상단 명령, 지도, 카메라, 로그로 나뉨 |
| 2 | `app.js` | `load()`, `sendGoal()`, `runCommand()`, `connectEvents()` | 브라우저 클릭/버튼/SSE 처리 |
| 3 | `dashboard_node.py` | `DashboardRequestHandler.do_GET/do_POST` | 브라우저 API 요청을 Python이 받음 |
| 4 | `dashboard_node.py` | `DashboardNode.__init__` | ROS action client와 topic subscription 생성 |
| 5 | `dashboard_node.py` | `send_navigation_goal()` | 맵 클릭 좌표를 Nav2 goal로 변환 |
| 6 | `dashboard_node.py` | `_send_dock()`, `_send_undock_only()` | Dock/Undock 버튼과 Create3 action 연결 |
| 7 | `dashboard_node.py` | `_handle_pose()`, `_handle_rgbd()`, `_publish_log()` | 위치/카메라/로그를 웹으로 전달 |
| 8 | `ninety.yaml` | `resolution`, `origin`, `image` | 웹 지도 좌표 변환의 기준 |
| 9 | `setup.py` | `package_data` | 웹 파일과 맵 파일을 ROS 패키지에 포함 |

설명할 때 따라갈 대표 시나리오:

```text
맵 클릭 이동:
index.html 지도 영역
  -> app.js mapStage click
  -> app.js pixelToWorld()
  -> app.js sendGoal()
  -> POST /api/goals
  -> dashboard_node.py do_POST()
  -> DashboardNode.send_navigation_goal()
  -> DashboardNode._send_navigation_only()
  -> /robot6/navigate_to_pose
  -> _handle_feedback() / _handle_result()
  -> _publish_log()
  -> app.js connectEvents()
  -> 로그 패널 갱신
```

이 순서 하나만 확실히 설명해도 핵심은 전달된다.

시간이 부족할 때 생략해도 되는 부분:

- `styles.css`의 세부 속성
- `_read_simple_map_yaml()` 같은 fallback parser
- `_extract_image_payload()`의 PNG/JPEG 세부 처리
- capture 저장 세부 구현
- SSH reboot/shutdown 세부 옵션

시간이 충분하면 추가로 설명할 부분:

- Docking Station의 `dock_after: true`
- `auto_undock`으로 이동 전 자동 undock 처리
- `EventBroker`로 여러 브라우저 listener에게 SSE 이벤트 전달
- `message_filters.ApproximateTimeSynchronizer`로 RGB/Depth 동기화

---

## 1. 먼저 이렇게 설명하면 된다

> 제가 구현한 부분은 `src/dashboard` 패키지 안에 있는 웹 기반 로봇 관제 대시보드입니다.  
> Python ROS2 노드가 HTTP 서버를 같이 띄우고, 브라우저에서 버튼이나 맵을 클릭하면 HTTP API로 Python 노드에 요청이 들어갑니다.  
> Python 노드는 그 요청을 Nav2 action, Create3 Dock/Undock action, SSH 명령으로 바꿔서 robot6에 전달합니다.  
> 반대로 로봇의 위치, Dock 상태, 카메라 영상, 로그는 ROS topic/action callback에서 받아 SSE로 브라우저에 실시간 표시합니다.

이 말을 먼저 하면 전체 구조를 잡고 들어갈 수 있다.

---

## 2. 봐야 하는 파일

핵심 파일:

- `src/dashboard/dashboard/dashboard_node.py`
  - ROS2 node
  - Python HTTP server
  - HTTP API endpoint
  - SSE 실시간 이벤트
  - Nav2 goal 전송
  - Dock/Undock action 전송
  - ROS Restart/Reboot/Shutdown SSH 명령
  - AMCL pose, dock status, RGB-D topic 구독

- `src/dashboard/dashboard/web/static/index.html`
  - 화면 구조
  - 상단 버튼
  - 지도 영역
  - 카메라 영역
  - 로그 영역

- `src/dashboard/dashboard/web/static/app.js`
  - 브라우저에서 실행되는 로직
  - 맵 클릭 처리
  - 버튼 클릭 처리
  - `/api/goals`, `/api/commands`, `/api/captures` 호출
  - `/api/events` SSE 수신

- `src/dashboard/dashboard/web/static/styles.css`
  - 화면 레이아웃과 색상

- `src/dashboard/dashboard/web/maps/`
  - 웹에 띄우는 지도 파일
  - `ninety.yaml`, `ninety.pgm`, `ninety.png`

- `src/dashboard/setup.py`
  - `web/static`, `web/maps` 파일이 ROS package에 포함되게 설정

---

## 3. 전체 데이터 흐름

### 맵 클릭으로 로봇 이동

```text
사용자 브라우저에서 지도 클릭
  -> app.js mapStage click event
  -> pixelToWorld()로 지도 pixel을 ROS map 좌표 x/y/yaw로 변환
  -> sendGoal()
  -> HTTP POST /api/goals
  -> DashboardRequestHandler.do_POST()
  -> DashboardNode.send_navigation_goal()
  -> 필요하면 /robot6/undock action
  -> /robot6/navigate_to_pose Nav2 action
  -> action feedback/result callback
  -> EventBroker로 log 이벤트 발행
  -> 브라우저 /api/events SSE
  -> 오른쪽 로그 패널 갱신
```

### Dock 버튼

```text
사용자 Dock 버튼 클릭
  -> app.js runCommand("dock")
  -> HTTP POST /api/commands
  -> DashboardNode.run_operator_command()
  -> DashboardNode._send_dock()
  -> /robot6/dock Create3 Dock action
  -> 결과 callback
  -> 로그 패널에 성공/실패 표시
```

### Undock 버튼

```text
사용자 Undock 버튼 클릭
  -> app.js runCommand("undock")
  -> HTTP POST /api/commands
  -> DashboardNode.run_operator_command()
  -> DashboardNode._send_undock_only()
  -> /robot6/undock Create3 Undock action
  -> 결과 callback
  -> 로그 패널에 성공/실패 표시
```

### ROS Restart 버튼

```text
사용자 ROS Restart 버튼 클릭
  -> app.js runCommand("ros_restart")
  -> HTTP POST /api/commands
  -> DashboardNode.run_operator_command()
  -> DashboardNode._run_remote_command()
  -> SSH ubuntu@192.168.109.106
  -> sudo systemctl restart turtlebot4.service
  -> 완료/실패 로그 표시
```

### 위치 표시

```text
/robot6/amcl_pose topic
  -> DashboardNode._handle_pose()
  -> quaternion을 yaw로 변환
  -> EventBroker pose 이벤트
  -> /api/events SSE
  -> app.js connectEvents()
  -> AMR marker 위치/방향 갱신
```

### 카메라 표시

```text
/robot6/oakd/rgb/image_raw/compressed
/robot6/oakd/stereo/image_raw/compressedDepth
  -> DashboardNode가 CompressedImage 구독
  -> image bytes를 data:image/... base64 URL로 변환
  -> SSE rgb/depth/rgbd 이벤트
  -> app.js가 <img> src를 갱신
```

---

## 4. `dashboard_node.py`에서 중요한 클래스

### `NavigationTarget`

목적지 하나를 표현하는 dataclass다.

필드:

- `x`: map frame x 좌표
- `y`: map frame y 좌표
- `yaw`: 로봇 방향
- `name`: 화면/로그에 보이는 이름
- `dock_after`: True면 목표 도착 후 자동 dock

`DEFAULT_TARGETS`에 들어있는 값들이 이 구조로 변환된다.

### `EventBroker`

브라우저에 실시간 이벤트를 보내는 중간 관리자다.

왜 필요한가:

- ROS callback은 언제든 로그/위치/영상 이벤트를 만든다.
- 브라우저는 `/api/events`로 SSE 연결을 열어둔다.
- `EventBroker`가 그 사이에서 이벤트를 Queue에 넣고 여러 브라우저 listener에게 뿌린다.

### `DashboardRequestHandler`

Python HTTP server의 요청 처리 클래스다.

중요한 endpoint:

- `GET /`: dashboard HTML 반환
- `GET /api/config`: 맵 정보, 기본 target, 현재 상태 반환
- `GET /api/events`: SSE 실시간 이벤트 연결
- `POST /api/goals`: Nav2 이동 요청
- `POST /api/commands`: Dock/Undock/Restart/Reboot/Shutdown
- `POST /api/captures`: 카메라 캡쳐 저장

### `DashboardNode`

실제 ROS2 노드다.

하는 일:

- ROS parameter 선언
- Nav2/Dock/Undock action client 생성
- DockStatus, AMCL pose, RGB-D topic subscription 생성
- HTTP server 시작
- 브라우저 요청을 ROS action/SSH 명령으로 변환
- ROS callback 결과를 웹 로그로 발행

---

## 5. `dashboard_node.py`에서 중요한 함수

### `get_client_config()`

브라우저가 처음 열릴 때 `/api/config`로 받는 초기 설정을 만든다.

포함 내용:

- map metadata
- DEFAULT_TARGETS
- 현재 status

### `get_status()`

현재 dashboard 상태를 JSON으로 만든다.

포함 내용:

- 현재 goal 상태
- active goal
- action/topic 이름
- dock 여부
- AMR pose

### `send_navigation_goal(payload)`

맵 클릭이나 marker 클릭으로 들어온 목적지를 처리한다.

받는 값:

- 브라우저가 보낸 JSON payload
- `x`, `y`, `yaw`, `name`, `dock_after`

하는 일:

1. `_target_from_payload()`로 JSON 검증
2. 현재 goal이 진행 중인지 확인
3. dock 상태면 필요 시 undock 먼저 수행
4. Nav2 goal 전송
5. Docking Station이면 도착 후 dock 수행

### `_send_navigation_only(target)`

Nav2 `NavigateToPose` action을 실제로 보내는 함수다.

보내는 대상:

- `/robot6/navigate_to_pose`

받는 대상:

- robot6의 Nav2 bt_navigator action server

### `_send_undock_then_navigation(target, strict)`

도킹 상태에서 일반 목적지를 눌렀을 때 실행된다.

흐름:

1. `/robot6/undock` action
2. undock 성공
3. `_send_navigation_only(target)`

### `_send_dock(target)`

Docking Station 도착 후 dock action을 보낸다.

보내는 대상:

- `/robot6/dock`

받는 대상:

- robot6의 Create3 dock action server

### `_handle_pose(message)`

AMCL pose topic callback이다.

받는 topic:

- `/robot6/amcl_pose`

하는 일:

- pose position x/y 저장
- quaternion orientation을 yaw로 변환
- 브라우저에 `pose` SSE 이벤트 발행

### `_handle_rgbd()`, `_handle_rgb_frame()`, `_handle_depth_frame()`

카메라 topic callback이다.

받는 topic:

- `/robot6/oakd/rgb/image_raw/compressed`
- `/robot6/oakd/stereo/image_raw/compressedDepth`

하는 일:

- CompressedImage를 브라우저에서 표시 가능한 data URL로 변환
- `rgb`, `depth`, `rgbd` SSE 이벤트 발행

### `run_operator_command(payload)`

상단 command 버튼을 처리한다.

받는 command:

- `dock`
- `undock`
- `ros_restart`
- `reboot`
- `shutdown`

---

## 6. `app.js`에서 중요한 함수

### `load()`

페이지가 열릴 때 처음 실행된다.

하는 일:

- `/api/config` 호출
- map metadata 저장
- 기본 target 저장
- 지도 이미지 로딩
- SSE 연결 시작

### `worldToPixel()`

ROS map 좌표를 웹 지도 pixel 좌표로 변환한다.

쓰는 곳:

- target marker 표시
- AMR marker 표시

### `pixelToWorld()`

웹 지도 클릭 pixel을 ROS map 좌표로 변환한다.

쓰는 곳:

- 지도 빈 곳 클릭 이동

### `sendGoal(target)`

목적지를 Python 서버로 보낸다.

보내는 endpoint:

- `POST /api/goals`

### `runCommand(command)`

상단 버튼 명령을 Python 서버로 보낸다.

보내는 endpoint:

- `POST /api/commands`

### `connectEvents()`

SSE 연결을 연다.

받는 이벤트:

- `log`: 오른쪽 로그 패널 추가
- `pose`: AMR marker 위치 갱신
- `rgbd`: RGB/Depth 동시 갱신
- `rgb`: RGB만 갱신
- `depth`: Depth만 갱신

---

## 7. 예상 질문과 답변

### Q. 이건 system monitor인가요?

넓게 보면 system monitor 성격이 있지만, 더 정확히는 **Robot System Monitoring & Control Dashboard**입니다. 위치, 카메라, dock 상태, 로그를 모니터링하고, 동시에 이동/dock/undock/restart 명령도 보냅니다.

### Q. 맵 클릭하면 어떻게 로봇이 움직이나요?

브라우저의 `app.js`가 클릭 pixel을 map 좌표로 변환해서 `/api/goals`로 보냅니다. Python의 `DashboardNode.send_navigation_goal()`이 그 값을 `PoseStamped`로 바꿔 `/robot6/navigate_to_pose` Nav2 action에 goal을 보냅니다.

### Q. Docking Station은 왜 누르면 dock까지 하나요?

`DEFAULT_TARGETS`에서 Docking Station target만 `dock_after: True`로 되어 있습니다. Nav2 goal이 성공하면 `_handle_result()`에서 이 값을 보고 `_send_dock()`을 호출합니다.

### Q. 브라우저 로그는 어떻게 실시간으로 뜨나요?

Python HTTP server의 `/api/events`가 SSE 연결을 유지합니다. ROS callback에서 `_publish_log()`를 호출하면 `EventBroker`가 log 이벤트를 만들고, 브라우저 `app.js`의 `connectEvents()`가 받아서 로그 패널에 추가합니다.

### Q. 카메라는 어떻게 웹에 보이나요?

ROS `CompressedImage` topic을 Python이 구독하고, 이미지 bytes를 base64 data URL로 바꿔 SSE로 브라우저에 보냅니다. 브라우저는 `<img>` 태그의 `src`를 그 data URL로 갱신합니다.

### Q. ROS Restart는 ROS action인가요?

아닙니다. SSH로 robot6 PC에 들어가서 `sudo systemctl restart turtlebot4.service`를 실행합니다.

### Q. dashboard 말고 다른 패키지도 봐야 하나요?

내가 구현한 웹 dashboard 자체는 `src/dashboard`만 보면 됩니다. 다만 실제 동작은 외부 ROS action/topic에 의존합니다. 예를 들면 `/robot6/navigate_to_pose`, `/robot6/dock`, `/robot6/undock`, `/robot6/amcl_pose`, OAK-D camera topic이 살아 있어야 합니다.

---

## 8. 발표 때 열 파일 순서

1. `src/dashboard/dashboard/web/static/index.html`
   - 화면 구조 설명

2. `src/dashboard/dashboard/web/static/app.js`
   - 클릭/버튼/SSE 처리 설명

3. `src/dashboard/dashboard/dashboard_node.py`
   - HTTP endpoint와 ROS action 연결 설명

4. `src/dashboard/setup.py`
   - web/static, web/maps 파일을 패키지에 포함한 점 설명

---

## 9. 한 줄 요약

> 이 dashboard는 브라우저 UI와 ROS2 action/topic을 연결해서, robot6의 위치와 카메라를 모니터링하고 맵 클릭 이동, Dock/Undock, 시스템 명령을 수행할 수 있게 만든 관제 대시보드입니다.
