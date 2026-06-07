# dashboard

Operator dashboard for MediCart command and monitoring.

## Web navigation dashboard

The `dashboard_node` hosts a small web UI and sends clicked map coordinates to
Nav2 through the `NavigateToPose` action.

Build:

```bash
colcon build --packages-select dashboard
source install/setup.bash
```

Run with the default Nav2 action:

```bash
ros2 run dashboard dashboard_node
```

Run with the robot6 namespace:

```bash
ros2 run dashboard dashboard_node --ros-args \
  -p action_name:=/robot6/navigate_to_pose \
  -p host:=0.0.0.0 \
  -p port:=8080
```

Open `http://127.0.0.1:8080` in a browser. Clicking a preset target or any
point on the map sends a goal in the `map` frame. The log panel streams goal
request, send completion, movement feedback, arrival, cancel, and failure
events in real time.

## robot6 실행 순서

아래 순서로 실행해야 웹 대시보드에서 클릭한 좌표로 robot6가 이동한다.
각 명령은 터미널을 나눠서 실행한다.

### 1. Localization 실행

```bash
loc 6 ~/MediCart/medicart_ws/maps/ninety.yaml
```

대시보드 지도 좌표는 `ninety.yaml` 기준이므로 localization도 같은 맵을
사용해야 한다.

### 2. RViz 실행 후 초기 위치 설정

```bash
rv 6
```

RViz가 뜨면 `2D Pose Estimate`로 맵 위의 실제 로봇 위치와 방향을 찍는다.
초기 위치를 잡지 않으면 AMCL이 `map -> odom` 변환을 만들지 못해서 Nav2가
정상 동작하지 않는다.

### 3. Nav2 실행

```bash
nav 6
```

Nav2가 정상 준비됐는지 확인하려면 아래 명령을 사용한다.

```bash
ros2 action info /robot6/navigate_to_pose
```

정상 상태에서는 `Action servers: 1`이 보이고 server가
`/robot6/bt_navigator`로 표시된다.

### 4. Dashboard 실행

```bash
cd ~/MediCart/medicart_ws
source install/setup.bash
ros2 run dashboard dashboard_node --ros-args \
  -p action_name:=/robot6/navigate_to_pose \
  -p port:=8080
```

브라우저에서 `http://127.0.0.1:8080`에 접속한다. 지도 위의 지정 위치 또는
임의 좌표를 클릭하면 robot6에 목표가 전송되고, 오른쪽 로그 패널에 목표
전송/이동 중/도착 완료 상태가 실시간으로 표시된다.

현재 화면은 한 페이지 안에서 다음 항목을 동시에 보여준다.

- 스캔된 2D 맵, 주요 호출 지점, `Docking Station`, 실시간 AMR 위치
- 지도 클릭 또는 마커 클릭을 통한 Nav2 목표 전송
- message_filters approximate sync로 맞춘 compressed RGB/depth 10fps 뷰
- RGB-D 캡쳐 토글. ON 상태에서는 화면에 표시된 RGB/depth 이미지를
  약 0.75초마다 저화질 JPEG 파일로 저장한다.
- Dock, Undock, ROS Restart, Reboot, Shutdown 버튼
- 실시간 로그

기본 topic/command는 robot6 기준이다.

```bash
ros2 run dashboard dashboard_node --ros-args \
  -p action_name:=/robot6/navigate_to_pose \
  -p rgb_topic:=/robot6/oakd/rgb/image_raw/compressed \
  -p depth_topic:=/robot6/oakd/stereo/image_raw/compressedDepth \
  -p port:=8080
```

실제 compressed topic 이름이 다르면 `rgb_topic`, `depth_topic`만 바꿔서
실행한다. AMR 위치는 기본적으로 `/robot6/amcl_pose`를 사용한다.

캡쳐 파일은 RGB와 depth가 각각 따로 저장된다.
저장 형식은 `.jpg`이며, 파일명은 저장 시각과 이미지 종류를 포함한다.

```text
20260607_142125_649_rgb.jpg
20260607_142125_649_depth.jpg
```

저장 전에 브라우저에서 화면 이미지를 약 65% 크기로 줄이고 JPEG 품질을
낮춰 저장하므로 원본 topic 이미지보다 화질이 낮다.

기본 저장 위치는 dashboard 패키지 내부의 `captures` 디렉터리다.
다만 `ros2 run`으로 실행하면 install 경로 아래 패키지 디렉터리에
저장될 수 있으므로, 팀 공용 사용 시에는 `capture_dir` 파라미터로
저장 위치를 고정하는 것을 권장한다.

```bash
ros2 run dashboard dashboard_node --ros-args \
  -p action_name:=/robot6/navigate_to_pose \
  -p capture_dir:=$HOME/MediCart/medicart_ws/src/dashboard/captures \
  -p port:=8080
```

위처럼 실행하면 캡쳐 파일은 아래 위치에 저장된다.

```text
~/MediCart/medicart_ws/src/dashboard/captures
```

전원/서비스 메뉴는 고정 명령만 실행한다.

- Dock: `/robot6/dock`
- Undock: `/robot6/undock`
- ROS Restart: `ssh ubuntu@192.168.109.106` 후
  `sudo systemctl restart turtlebot4.service`
- Reboot: `ssh ubuntu@192.168.109.106` 후 `sudo reboot`
- Shutdown: `ssh ubuntu@192.168.109.106` 후 `sudo shutdown now`

원격 host나 sudo password가 다르면 아래 파라미터로 변경한다.

```bash
ros2 run dashboard dashboard_node --ros-args \
  -p action_name:=/robot6/navigate_to_pose \
  -p remote_host:=ubuntu@192.168.109.106 \
  -p remote_sudo_password:=turtlebot4 \
  -p port:=8080
```

기본 타깃에는 `Docking Station`도 포함되어 있다.

- 위치: `x=-8`, `y=-6`, `yaw=-0.00142`
- 로봇이 dock 상태에서 일반 지점을 클릭하면 dashboard가 먼저
  `/robot6/undock`을 호출한 뒤 Nav2 이동을 시작한다.
- `Docking Station`을 클릭하면 먼저 해당 좌표로 이동하고,
  `목표 도착 완료` 로그 후 자동으로 `/robot6/dock`을 호출한다.
- dock 진행 중에는 `도킹 중...`, 완료 시에는 `Docking Station 도킹 완료!`
  로그가 표시된다.

### 문제 확인

`Nav2 액션 서버 연결 실패`가 뜨면 먼저 action server 개수를 확인한다.

```bash
ros2 action info /robot6/navigate_to_pose
```

`Action servers: 0`이면 Nav2가 아직 active 상태가 아니다. RViz에서 초기
위치를 찍었는지 확인하고, 필요하면 lifecycle manager startup을 호출한다.

```bash
ros2 service call /robot6/lifecycle_manager_navigation/manage_nodes \
  nav2_msgs/srv/ManageLifecycleNodes "{command: 1}"
```

## 구현 구조

팀원이 Claude Code 등으로 이어서 수정할 때는 아래 파일을 보면 된다.

```text
dashboard/
├── dashboard/
│   ├── dashboard_node.py        # ROS2 node, HTTP server, SSE, Nav2/dock/camera/capture logic
│   └── web/
│       ├── maps/                # dashboard에서 표시하는 ninety map asset
│       └── static/
│           ├── index.html       # 한 화면 dashboard layout
│           ├── app.js           # browser UI, SSE 연결, map/camera/capture interaction
│           └── styles.css       # compact single-page layout
├── package.xml                  # ROS dependency
├── setup.py                     # web/static, web/maps package_data 포함
└── README.md
```

`dashboard_node.py`는 별도 프론트엔드 빌드 도구 없이 Python HTTP server로
정적 파일을 서빙한다. 브라우저는 HTTP API와 SSE를 사용한다.

- `/`: `web/static/index.html` 반환
- `/app.js`, `/styles.css`: 정적 UI 파일 반환
- `/maps/...`: `web/maps` 안의 map 파일 반환
- `/api/state`: map metadata, target 목록, 현재 설정값 반환
- `/api/goals`: 클릭 좌표 또는 target goal을 Nav2로 전송
- `/api/commands`: Dock, Undock, ROS Restart, Reboot, Shutdown 실행
- `/api/captures`: 브라우저가 저화질 JPEG로 변환한 RGB/depth 이미지 저장
- `/events`: Server-Sent Events. 로그, AMR pose, RGB-D frame을 실시간 전달

ROS 연동은 robot6 기준 기본값을 사용한다.

- Nav2 이동: `/robot6/navigate_to_pose`
- Dock action: `/robot6/dock`
- Undock action: `/robot6/undock`
- Dock 상태: `/robot6/dock_status`
- AMR 위치: `/robot6/amcl_pose`
- RGB compressed: `/robot6/oakd/rgb/image_raw/compressed`
- Depth compressed: `/robot6/oakd/stereo/image_raw/compressedDepth`

RGB-D는 `message_filters.ApproximateTimeSynchronizer`로 RGB와 depth를
동기화해서 보내고, sync가 안 잡히는 상황에서도 화면이 비지 않도록 RGB와
depth 각각의 direct subscription fallback도 둔다. 브라우저에는 base64
data URL 형태로 전달된다.

지도 target은 `dashboard_node.py`의 `DEFAULT_TARGETS`에 있다.
`Docking Station` target은 `x=-8`, `y=-6`, `yaw=-0.00142`이며
`dock_after_arrival=True`로 설정되어 있다. dock 상태에서 일반 target을
누르면 먼저 undock 후 Nav2 goal을 보내고, Docking Station에 도착하면
도착 로그 후 dock action을 호출한다.

전원/서비스 버튼은 안전을 위해 고정된 allowlist 명령만 실행한다.
원격 명령은 `remote_host`, `remote_sudo_password` 파라미터를 사용한다.

캡쳐는 서버가 원본 ROS 이미지를 직접 저장하는 방식이 아니다.
브라우저에 현재 표시된 RGB/depth 이미지를 canvas에 그린 뒤,
가로/세로 65%로 줄이고 `image/jpeg` 품질 `0.45`로 변환해
`/api/captures`로 업로드한다. 서버는 전달받은 JPEG data URL을
`capture_dir` 아래에 저장한다.

## 전달용 압축 권장

팀원에게는 `src/dashboard` 패키지 폴더만 전달하면 된다. 단, 아래 생성물은
압축에서 제외하는 것을 권장한다.

- `__pycache__/`
- `.pytest_cache/`
- `captures/`

예시:

```bash
cd ~/MediCart/medicart_ws/src
zip -r dashboard.zip dashboard \
  -x 'dashboard/**/__pycache__/*' \
  -x 'dashboard/.pytest_cache/*' \
  -x 'dashboard/.pytest_cache/**' \
  -x 'dashboard/captures/*'
```

받는 쪽은 workspace의 `src/` 아래에 압축을 풀고 아래처럼 빌드한다.

```bash
cd ~/MediCart/medicart_ws
colcon build --packages-select dashboard
source install/setup.bash
```
