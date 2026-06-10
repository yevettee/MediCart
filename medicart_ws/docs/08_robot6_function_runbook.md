# ROBOT6 기능, 패키지, 실행, 웹 버튼 동작 정리

기준: 2026-06-10, `origin/main` pull 이후 로컬 코드 확인 기준.

주의: 이 문서는 코드와 launch 파일을 기준으로 정리한 것이다. 실제 로봇에서 전체 시나리오를 끝까지 주행 검증한 결과는 아니다.

## 1. ROBOT6 한 줄 요약

ROBOT6는 약품실 이동, 약품 OCR 대기, 간호사 추종, 홈 복귀와 도킹을 수행하는 간호사 카트 로봇이며, 웹 명령은 Firebase RTDB `robot6/mission_pool`을 거쳐 ROS2 `db_node`와 `mission_manager_node`가 처리한다.

## 2. ROBOT6에서 되는 기능

### 2.1 Nav2 기반 자율 이동

- 기능: 웹이나 대시보드에서 좌표를 보내면 `/robot6/navigate_to_pose` Nav2 action으로 이동한다.
- 사용 노드: `mission_manager_node` 내부 `NavExecutor`, Nav2 stack.
- 선행 조건: `loc6.launch.py`로 AMCL localization, RViz 초기 pose 설정, `nav6.launch.py`로 Nav2 active 상태.
- 이동 frame: `map`.
- 도킹 상태에서 일반 지점으로 가면 먼저 `/robot6/undock`을 실행한 뒤 이동한다.
- `dock_after=true` 목표면 Nav2 도착 후 `/robot6/dock`을 실행한다.

### 2.2 웹 mission_pool 명령 수신

- 기능: 웹이 Firebase RTDB `robot6/mission_pool`에 명령을 쌓으면 로봇 쪽 `db_node`가 하나씩 가져와 실행한다.
- 경로: Web button -> Flask API -> RTDB `robot6/mission_pool` -> `db_node` -> `/robot6/mission_request` -> `mission_manager_node`.
- 결과 경로: `mission_manager_node` -> `/robot6/mission_feedback` -> `db_node` -> RTDB `mission_log`, `mission_status`, `mission_pool` 삭제.
- 이유: 웹 브라우저가 ROS2 네트워크에 직접 붙지 않아도 원격 명령을 안정적으로 보낼 수 있게 하려고 DB를 중간 큐로 둔다.

### 2.3 시스템 명령

현재 코드에서 되는 시스템 명령:

- `dock`: `/robot6/dock` action 실행.
- `undock`: `/robot6/undock` action 실행.
- `ros_restart`: SSH로 로봇 PC의 `turtlebot4.service` 재시작.
- `reboot`: SSH로 로봇 PC 재부팅.
- `shutdown`: SSH로 로봇 PC 종료.

주의:

- `ros_restart`, `reboot`, `shutdown`은 `DISCOVERY_IP` 또는 launch 인자 `discovery_ip`가 필요하다.
- 기본 ROBOT6 IP는 `common/robot.env` 기준 `192.168.109.106`.

### 2.4 시나리오 B: 간호사 카트 회진

웹의 `회진 시작`은 `nurse_cart_mission`을 넣고, 로봇은 아래 순서로 움직인다.

1. `GOTO_PHARMACY`: 약품실 좌표로 이동.
2. `WAIT_OCR`: 약품실 도착 후 웹 OCR 완료 신호를 기다림.
3. `GOTO_STANDBY`: 약품실 입구 또는 추종 시작 위치로 이동.
4. `START_ROUND`: `round` 모드를 켜고 간호사 추종 시작.
5. `WAIT_ROUND_DONE`: 웹에서 회진 종료 신호를 기다림.
6. `GOTO_HOME`: 홈 좌표로 복귀.
7. `DOCK`: 도킹까지 수행.

기본 좌표:

- 약품실: `x=-0.302782`, `y=-3.3757`, `yaw=-0.0545105`
- 대기 위치: `x=-0.9296`, `y=-3.3393`, `yaw=2.8293`
- 홈: `x=-0.354229`, `y=-0.118972`, `yaw=-0.0042011`, `dock_after=true`

### 2.5 간호사 추종

- 기능: OAK-D RGB-D와 YOLO로 `nurse` class를 찾고, 목표 거리 약 `0.4m`를 유지하며 따라간다.
- 사용 패키지: `nurse_tracker`.
- 입력 topic:
  - `/robot6/oakd/rgb/camera_info`
  - `/robot6/oakd/rgb/image_raw/compressed`
  - `/robot6/oakd/stereo/image_raw/compressedDepth`
- 출력 topic:
  - `/robot6/mode/round/cmd_vel`
  - `/robot6/mode/round/status`
  - `/nurse_tracker/target`
  - `/nurse_tracker/annotated_image`
- 실제 `/robot6/cmd_vel` 발행은 `mission_manager_node`가 mode arbiter를 거쳐 담당한다.
- 이유: 추종 노드가 바로 base를 움직이면 Nav2, 도킹, 다른 모드와 충돌할 수 있으므로 `mission_manager_node`가 속도 명령의 최종 게이트 역할을 한다.

### 2.6 안전 게이트

- `mission_manager_node`는 `/robot6/scan`을 보고 전방 가까운 장애물이 있으면 전진 속도만 0으로 제한한다.
- 회전과 후진은 막지 않는다.
- 기준: 전방 LiDAR clearance 약 `0.30m` 미만이면 전진 차단.

### 2.7 바닥 요철 감지

- 선택 기능: `robot6_bringup.launch.py obstacle_detector:=true`일 때 `obstacle_node`가 뜬다.
- 입력: `/robot6/oakd/stereo/image_raw/compressedDepth`
- 동작: depth 하단 중앙 ROI를 3D 점군으로 만들고 지면 평탄도를 분석한다.
- 출력:
  - `/obstacle_detector/ground_cloud`
  - `/obstacle_detector/ground_status`
- 주의: 현재 Nav2 costmap에 직접 넣는 구조라기보다 standalone 감지, 시각화, 상태 발행에 가깝다.

### 2.8 약품 OCR과 투약 검증

- OCR 자체는 ROBOT6 ROS 노드가 아니라 웹 프론트의 브라우저 카메라와 Flask backend가 처리한다.
- `/ocr` 페이지에서 웹캠 캡처 -> Flask `/api/ocr` -> GCP Vision 또는 fallback OCR -> 처방 데이터와 비교한다.
- 검증 성공 시 Firebase 환자 injection status를 `confirmed`로 바꾼다.
- OCR 완료 버튼은 로봇에게 “이제 추종 시작 위치로 이동해도 된다”는 신호를 보낸다.

### 2.9 웹 관제와 telemetry

- Next/Flask 웹은 `/api/stream`, `/api/amrs`로 RTDB snapshot을 읽어 로봇 위치, 속도, 배터리, 도킹 상태, scan 등을 보여준다.
- 단, 이 snapshot을 RTDB에 써주는 producer bridge는 이 launch들 안에서 직접 뜨지 않는다.
- `common/robot.env` 주석상 `ward_bridge`가 별도 telemetry producer 역할을 하는 것으로 보인다.
- 따라서 관제 화면이 살아 있으려면 robot6 telemetry를 RTDB에 쓰는 외부 브리지가 같이 동작해야 한다.

### 2.10 standalone ROS dashboard

- `medicart_ws/src/dashboard` 패키지는 별도 웹 대시보드다.
- 이 대시보드는 Firebase를 거치지 않고 ROS action을 직접 호출한다.
- 기능:
  - 지도 클릭 또는 preset target 클릭 -> `/robot6/navigate_to_pose`
  - Dock, Undock, ROS Restart, Reboot, Shutdown
  - `/robot6/amcl_pose` 기반 AMR 위치 표시
  - OAK-D RGB-D compressed stream 표시
  - RGB-D 화면 캡처 저장
- 실행 포트 기본 예시: `http://127.0.0.1:8080`

## 3. ROBOT6에 쓰이는 패키지

### 3.1 ROS 패키지

`mission_manager`

- 실행 노드:
  - `mission_manager_node`
  - `patrol_mode_node`
  - `stub_mode_node`
- ROBOT6 핵심 역할:
  - `/robot6/mission_request` 수신.
  - `goto`, `dock`, `undock`, `nurse_cart_mission`, mode start/stop 처리.
  - mode arbitration.
  - 최종 `/robot6/cmd_vel` 관리.
  - `/robot6/mission_feedback` 발행.

`db_bridge`

- 실행 노드:
  - `db_node`
  - `prescription_server`
  - `rooms_server`
  - `display_bridge`
- ROBOT6 핵심 역할:
  - RTDB `robot6/mission_pool` listen.
  - `/robot6/mission_request` publish.
  - `/robot6/mission_feedback` subscribe.
  - `robot6/nurse_cart/ocr_done`, `robot6/nurse_cart/round_done`을 ROS topic으로 변환.

`nurse_tracker`

- 실행 노드:
  - `tracker_node`
- ROBOT6 핵심 역할:
  - OAK-D RGB-D + YOLO 기반 nurse detection.
  - `round` mode에서 추종용 cmd_vel 후보 발행.

`obstacle_detector`

- 실행 노드:
  - `obstacle_node`
- ROBOT6 선택 역할:
  - OAK-D depth 기반 하단 지면 평탄도 분석.

`dashboard`

- 실행 노드:
  - `dashboard_node`
- 역할:
  - 독립 ROS 웹 대시보드.
  - Nav2 goal, dock/undock, 카메라 보기, 캡처.

### 3.2 common launch와 설정

`common/discovery.sh`

- `common/robot.env`를 읽어서 ROS domain, discovery server, namespace 관련 환경을 export한다.
- 현재 `common/robot.env`:
  - `ROBOT_NAMESPACE=robot6`
  - `DISCOVERY_IP=192.168.109.106`
  - `DISCOVERY_SERVER_ID=6`
  - `ROBOT_DOMAIN_ID=6`

`common/loc6.launch.py`

- robot6 localization launch.
- 내부적으로 `common/localization_bondpatched.launch.py`를 include한다.
- 주요 Nav2 localization node:
  - `map_server`
  - `amcl`
  - `lifecycle_manager_localization`

`common/nav6.launch.py`

- robot6 Nav2 launch.
- 내부적으로 `common/navigation_bondpatched.launch.py`를 include한다.
- 주요 Nav2 node:
  - `controller_server`
  - `smoother_server`
  - `planner_server`
  - `behavior_server`
  - `bt_navigator`
  - `waypoint_follower`
  - `velocity_smoother`
  - `lifecycle_manager_navigation`
- `/robot6/global_costmap/scan`, `/robot6/local_costmap/scan`을 `/robot6/scan`으로 remap한다.

### 3.3 웹 패키지

`web/backend`

- Flask backend.
- Firebase Admin SDK로 RTDB 읽기/쓰기.
- REST API, SSE, auth, OCR, injection verification 담당.

`web/frontend`

- Next.js frontend.
- 홈, 관제, 제어, 지도, 처치실, 문진, 디버그 화면 제공.
- 브라우저는 Firebase를 직접 만지지 않고 Flask API만 호출한다.

## 4. 전체 연결 구조

### 4.1 일반 웹 명령

```text
웹 버튼
  -> Flask /api/robots/<ns>/missions
  -> fb_read.push_mission(ns, action, params, mode)
  -> RTDB robot6/mission_pool/<mission_id>
  -> db_node listen
  -> ROS /robot6/mission_request
  -> mission_manager_node
  -> Nav2 action / system command / mode start-stop / sequencer
  -> ROS /robot6/mission_feedback
  -> db_node
  -> RTDB mission_log 기록, mission_pool 삭제, mission_status 갱신
```

이 구조의 이유:

- 웹은 병동망이나 외부망에서 접근하고, ROS2 DDS는 로봇 내부망과 discovery server에 묶인다.
- RTDB를 중간 큐로 두면 웹과 ROS2 네트워크를 분리하면서도 명령 이력과 상태를 남길 수 있다.
- `mission_pool`은 여러 명령이 들어와도 `db_node`가 FIFO에 가깝게 하나씩 처리한다.

### 4.2 간호사 카트 시나리오 B

```text
홈 화면 회진 시작
  -> POST /api/nurse_cart/start
  -> RTDB robot6/mission_pool: action=nurse_cart_mission
  -> db_node
  -> /robot6/mission_request
  -> mission_manager_node
  -> nurse_cart_sequencer
  -> NavExecutor: 약품실 이동
  -> feedback detail=pharmacy_arrived
  -> db_node: robot6/nurse_cart/phase=arrived
  -> display page: /login?next=/ocr 로 이동
  -> /ocr 페이지에서 OCR 완료 버튼
  -> RTDB robot6/nurse_cart/ocr_done=true
  -> db_node: /robot6/nurse_cart/ocr_done publish
  -> sequencer: 약품실 입구 이동 후 round mode start
  -> nurse_tracker: 간호사 추종
  -> 웹 회진 종료 버튼
  -> RTDB robot6/nurse_cart/round_done=true
  -> db_node: /robot6/nurse_cart/round_done publish
  -> sequencer: round stop, home 이동, dock
```

### 4.3 추종 제어

```text
OAK-D RGB-D compressed topics
  -> nurse_tracker PerceptionPipeline
  -> YOLO target class nurse detection
  -> depth bbox에서 거리 추정
  -> TF로 robot base 기준 좌표 계산
  -> follow_control
  -> /robot6/mode/round/cmd_vel
  -> mission_manager mode arbiter
  -> safety gate
  -> /robot6/cmd_vel
```

이 구조의 이유:

- detection과 base command를 분리해서 perception, control, arbitration 책임을 나눈다.
- `round` 모드가 꺼져 있으면 추종 노드는 속도 명령을 내지 않는다.
- 최종 base command는 `mission_manager_node`가 담당해서 Nav2, 도킹, 수동 모드와 충돌을 줄인다.

### 4.4 Nav2 interaction

```text
mission_manager NavExecutor
  -> 필요 시 /robot6/undock
  -> /robot6/navigate_to_pose goal(PoseStamped, frame_id=map)
  -> Nav2 bt_navigator
  -> planner_server 경로 생성
  -> controller_server 경로 추종
  -> local/global costmap은 /robot6/scan 사용
  -> 성공 시 필요하면 /robot6/dock
```

Nav2 stack에서 localization은 `loc6.launch.py`의 `amcl`이 담당하고, 주행은 `nav6.launch.py`의 planner/controller/bt navigator가 담당한다.

## 5. ROBOT6 실행 방법

### 5.1 최초 또는 코드 변경 후 build

```bash
cd ~/MediCart/medicart_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install
source install/setup.bash
```

### 5.2 공통 ROS 환경

모든 ROBOT6 ROS 터미널에서 먼저 실행한다.

```bash
source ~/MediCart/common/discovery.sh
cd ~/MediCart/medicart_ws
source install/setup.bash
```

확인:

```bash
echo $ROBOT_NAMESPACE
echo $ROS_DOMAIN_ID
echo $ROS_DISCOVERY_SERVER
```

현재 repo 기준 기대값:

```text
ROBOT_NAMESPACE=robot6
ROS_DOMAIN_ID=6
DISCOVERY_IP=192.168.109.106
```

### 5.3 localization 실행

터미널 1:

```bash
source ~/MediCart/common/discovery.sh
source ~/MediCart/medicart_ws/install/setup.bash
ros2 launch /home/rokey/MediCart/common/loc6.launch.py \
  namespace:=robot6 \
  map:=/home/rokey/MediCart/common/maps/ninety.yaml
```

역할:

- `map_server`가 map을 띄운다.
- `amcl`이 `/robot6/scan`과 map을 비교해 `map -> odom` localization을 만든다.

### 5.4 RViz 초기 pose 설정

터미널 2 또는 GUI:

```bash
rv 6
```

주의:

- `rv 6` alias는 repo 내부에서 정의되어 있지는 않고 팀 환경 alias로 보인다.
- RViz에서 `2D Pose Estimate`로 실제 로봇 위치와 방향을 찍어야 AMCL이 제대로 시작된다.
- 초기 pose가 없으면 Nav2가 goal을 받아도 경로 추종이 실패할 수 있다.

### 5.5 Nav2 실행

터미널 3:

```bash
source ~/MediCart/common/discovery.sh
source ~/MediCart/medicart_ws/install/setup.bash
ros2 launch /home/rokey/MediCart/common/nav6.launch.py \
  namespace:=robot6 \
  params_file:=/home/rokey/MediCart/common/nav6.yaml
```

확인:

```bash
ros2 action info /robot6/navigate_to_pose
```

정상 기대:

```text
Action servers: 1
```

### 5.6 시나리오 B 앱 노드 실행

터미널 4:

```bash
source ~/MediCart/common/discovery.sh
cd ~/MediCart/medicart_ws
source install/setup.bash
ros2 launch mission_manager scenario_b.launch.py nurse_tracker:=true
```

실행되는 노드:

- `db_bridge/db_node`
- `mission_manager/mission_manager_node`
- `nurse_tracker/tracker_node`

Firebase key가 기본 경로와 다르면:

```bash
ros2 launch mission_manager scenario_b.launch.py \
  namespace:=robot6 \
  nurse_tracker:=true \
  fb_cred:=/path/to/serviceAccountKey.json \
  fb_db_url:=https://medi-cart-ea39f-default-rtdb.asia-southeast1.firebasedatabase.app \
  discovery_ip:=192.168.109.106
```

### 5.7 범용 ROBOT6 bringup 실행

시나리오 B가 아니라 일반 ROBOT6 앱 노드를 한 번에 띄우려면:

```bash
source ~/MediCart/common/discovery.sh
cd ~/MediCart/medicart_ws
source install/setup.bash
ros2 launch mission_manager robot6_bringup.launch.py \
  nurse_tracker:=true \
  obstacle_detector:=false
```

차이:

- `scenario_b.launch.py`: 간호사 카트 시나리오 B에 맞춰 tracker 기본값이 true.
- `robot6_bringup.launch.py`: 일반 bringup이고 tracker, obstacle detector를 선택적으로 켠다.

### 5.8 수동 테스트 스크립트

```bash
python3 ~/MediCart/medicart_ws/src/mission_manager/scripts/trigger_nurse_cart.py start
python3 ~/MediCart/medicart_ws/src/mission_manager/scripts/trigger_nurse_cart.py ocr_done
python3 ~/MediCart/medicart_ws/src/mission_manager/scripts/trigger_nurse_cart.py round_done
python3 ~/MediCart/medicart_ws/src/mission_manager/scripts/trigger_nurse_cart.py status
```

주의: `scenario_b.launch.py` 주석에는 `inject_ocr_done.py`가 언급되지만, 현재 실제 파일은 `trigger_nurse_cart.py`다.

## 6. 웹 실행 방법

### 6.1 backend 실행

최초 1회:

```bash
cd ~/MediCart/web/backend
pip install -r requirements.txt
cp .env.example .env
```

`.env`에서 ROBOT6 시연에 중요한 값:

```text
FB_CRED=/path/to/serviceAccountKey.json
FB_DB_URL=https://medi-cart-ea39f-default-rtdb.asia-southeast1.firebasedatabase.app
PRIMARY_NS=robot6
SECONDARY_NS=robot3
INTEL_PASSWORD=rokey1234
INTEL_AUTH_TOKEN=<staff token>
INTEL_ADMIN_PASSWORD=<admin password>
INTEL_ADMIN_TOKEN=<admin token>
FRONTEND_ORIGIN=http://localhost:3000
COOKIE_SECURE=0
PORT=5000
```

실행:

```bash
cd ~/MediCart/web/backend
set -a && source .env && set +a
python3 app.py
```

주소:

```text
http://localhost:5000
```

중요:

- `PRIMARY_NS`가 기본값이면 `robot3`가 된다.
- ROBOT6 회진 버튼이 robot6에 들어가려면 backend `PRIMARY_NS=robot6`이 반드시 필요하다.

### 6.2 frontend 실행

최초 1회:

```bash
cd ~/MediCart/web/frontend
npm install
```

`.env.local` 권장:

```text
NEXT_PUBLIC_API_BASE=http://localhost:5000
NEXT_PUBLIC_PRIMARY_NS=robot6
NEXT_PUBLIC_SECONDARY_NS=robot3
INTEL_AUTH_TOKEN=<backend INTEL_AUTH_TOKEN과 동일>
INTEL_ADMIN_TOKEN=<backend INTEL_ADMIN_TOKEN과 동일>
```

실행:

```bash
cd ~/MediCart/web/frontend
npm run dev -- --port 3000
```

주소:

```text
http://localhost:3000
```

주의:

- `npm run dev`만 실행하면 backend `.env`의 `PORT=5000`을 상속해서 port conflict가 날 수 있다.
- 반드시 `-- --port 3000`을 붙이는 것이 안전하다.

### 6.3 standalone dashboard 실행

이건 Next/Flask 웹과 다른 직접 ROS 대시보드다.

```bash
cd ~/MediCart/medicart_ws
source ~/MediCart/common/discovery.sh
source install/setup.bash
ros2 run dashboard dashboard_node --ros-args \
  -p action_name:=/robot6/navigate_to_pose \
  -p rgb_topic:=/robot6/oakd/rgb/image_raw/compressed \
  -p depth_topic:=/robot6/oakd/stereo/image_raw/compressedDepth \
  -p capture_dir:=$HOME/MediCart/medicart_ws/src/dashboard/captures \
  -p port:=8080
```

브라우저:

```text
http://127.0.0.1:8080
```

## 7. 웹에서 뭘 누르면 뭐가 되는지

### 7.1 홈 `/`

`회진 시작`

- 권한: staff 이상.
- 프론트 함수: `startRound()`.
- API: `POST /api/nurse_cart/start`.
- DB: `PRIMARY_NS/mission_pool`에 `action=nurse_cart_mission` push.
- ROBOT6 조건: `PRIMARY_NS=robot6`.
- 결과: ROBOT6가 약품실로 이동하고, 도착하면 `nurse_cart/phase=arrived`.

`회진 시작 확인`

- 실제 mission push가 일어나는 버튼.
- 성공하면 `RoundOverlay`가 뜨고 phase를 2초마다 polling한다.

`RoundOverlay`의 `회진 종료 · 복귀`

- API: `POST /api/nurse_cart/round_done`.
- DB: `robot6/nurse_cart/round_done=true`.
- ROS: `db_node`가 `/robot6/nurse_cart/round_done` publish.
- 결과: 추종 종료, 홈 복귀, 도킹.

`순회 문진 시작`

- `patrol_intake_mission`을 쓰는 별도 시나리오다.
- ROBOT6 핵심 회진 시나리오와는 분리해서 설명하는 것이 좋다.
- `PRIMARY_NS=robot6`이면 robot6로 들어갈 수 있으므로, 문진 시나리오를 robot3에 남기려면 namespace 설정을 주의해야 한다.

### 7.2 처치실 `/ocr`

`OCR 완료`

- API: `POST /api/nurse_cart/ocr_done`.
- DB: `robot6/nurse_cart/ocr_done=true`.
- ROS: `db_node`가 `/robot6/nurse_cart/ocr_done` publish.
- 결과: `nurse_cart_sequencer`가 `WAIT_OCR`에서 빠져나와 약품실 입구로 이동한 뒤 `round` 모드를 시작한다.

`회진 종료`

- API: `POST /api/nurse_cart/round_done`.
- 결과: 추종 정지, 홈 복귀, 도킹.

`스캔 & OCR`

- 브라우저 카메라 frame capture.
- API: `POST /api/ocr`.
- 결과: Flask backend가 OCR 텍스트를 반환한다.
- 환자와 주사 처방이 선택되어 있으면 즉시 `verifyInjection`까지 호출한다.

`약품 적합성 검증 & DB 저장`

- API: `POST /api/patients/<pid>/injections/<inj_id>/verify`.
- 결과:
  - 일치: injection status `confirmed`.
  - 불일치: injection status `mismatch`.

`QR 환자 확인 모드`

- 브라우저에서 `jsQR`로 QR을 계속 스캔한다.
- QR이 선택 환자와 일치하고 약품 준비가 완료되어 있으면 `confirmInjection`으로 최종 확정한다.
- 환자가 다르거나 약품이 준비되지 않았으면 차단 메시지를 보여준다.

### 7.3 관리자 콘솔 `/console`

로봇 선택 `ROBOT6`

- 이후 버튼들은 선택한 namespace `robot6`로 mission을 넣는다.

시스템 명령 버튼:

- `도킹`: `POST /api/robots/robot6/missions`, action `dock`.
- `언도킹`: action `undock`.
- `ROS 재시작`: action `ros_restart`.
- `재부팅`: action `reboot`.
- `종료`: action `shutdown`.

모드 버튼:

- `회진(추종) 시작`: action `start`, mode `round`.
- `회진(추종) 정지`: action `stop`, mode `round`.
- `문진`, `지시`, `가이드`, `순찰`도 같은 방식으로 mode start/stop을 넣는다.
- 주의: ROBOT6에서 실제 의미가 있는 것은 현재 코드 기준 `round`가 가장 명확하다. 다른 mode는 registry에 있지만 해당 mode node가 실행되어야 실제 기능이 된다.

전체 해제:

- action `clear`.
- `mission_manager_node`의 mode arbiter가 활성 모드를 비운다.

이동 target 버튼:

- API: `POST /api/robots/robot6/missions`.
- action: `goto`.
- params: `{x, y, yaw, dock_after, label}`.
- 결과: `NavExecutor`가 `/robot6/navigate_to_pose` goal을 보낸다.

지도 클릭:

- embedded `MapView`에서 클릭 좌표를 ROS map 좌표로 변환한다.
- action `goto`, label `맵 클릭`.

mission_pool 패널:

- `GET /api/robots/robot6/missions`로 RTDB queue를 보여준다.

MapToolbar의 `자율 맵 생성`

- API: `/api/mode`.
- 현재 `fb_read.save_mode()`가 `PRIMARY_NS/cmd`에 쓰는 legacy 경로다.
- `mission_pool -> db_node -> mission_manager` 경로와 다르므로, ROBOT6 현재 핵심 미션 경로로 설명하지 않는 것이 좋다.

### 7.4 로봇 제어 `/control`

- `/console`보다 단순한 제어 화면이다.
- 대상 로봇 선택 후 시스템 명령과 mode start/stop을 `mission_pool`에 넣는다.
- goto target이나 지도 클릭 기능은 없다.

### 7.5 지도 `/map`

- RTDB telemetry 기반으로 AMR 위치와 map을 보여준다.
- 지도 클릭 시 선택된 namespace로 `goto` mission을 넣는다.
- 관제 기능은 telemetry producer bridge가 살아 있어야 정확히 보인다.

### 7.6 디버그 `/debug`

- 명령을 보내는 화면이 아니라 telemetry, battery, velocity, LiDAR snapshot, raw JSON, alerts를 보는 화면이다.
- RTDB snapshot/SSE가 필요하다.

### 7.7 공용 display `/display`

- QR 환자 스캔이 감지되면 `/intake?pid=...`로 이동한다.
- `nurse_cart/phase`를 2초마다 polling한다.
- phase가 `arrived`가 되면 `/login?next=/ocr`로 이동한다.
- 즉, ROBOT6가 약품실에 도착하면 처치실 OCR 화면으로 자연스럽게 이어지게 하는 공용 대기 화면이다.

### 7.8 standalone dashboard `:8080`

지도 target 클릭 또는 임의 지도 클릭:

- `/api/goals` POST.
- `dashboard_node`가 직접 `/robot6/navigate_to_pose` goal을 보낸다.

`Dock`

- `/api/commands` command `dock`.
- `/robot6/dock` action 실행.

`Undock`

- `/api/commands` command `undock`.
- `/robot6/undock` action 실행.

`ROS Restart`, `Reboot`, `Shutdown`

- `/api/commands`로 allowlist된 SSH 명령 실행.

`Capture ON/OFF`

- 화면에 표시 중인 RGB/depth 이미지를 브라우저에서 JPEG로 줄여 `/api/captures`에 업로드한다.
- 저장 위치는 `capture_dir` 파라미터.

`Clear`

- dashboard 화면 로그를 지운다.

## 8. 질문 들어올 가능성이 큰 포인트

### Q1. 왜 웹이 ROS topic을 직접 publish하지 않고 Firebase를 거치나?

웹과 ROS2 DDS 네트워크를 분리하고, 원격 접근, 인증, mission queue, 이력 저장을 쉽게 하기 위해서다.

### Q2. `mission_pool`은 뭐냐?

웹이 로봇에게 실행하라고 넣어두는 Firebase 명령 대기열이고, `db_node`가 pending mission을 하나씩 ROS `mission_request`로 바꾼다.

### Q3. `mission_request` 수신은 뭐냐?

`db_node`가 Firebase 명령을 ROS topic `/robot6/mission_request`로 발행하고, `mission_manager_node`가 이 topic을 받아 실제 실행하는 것이다.

### Q4. ROBOT6에서 핵심 시나리오는 뭐냐?

시나리오 B, 즉 약품실 이동 -> OCR 대기 -> 간호사 추종 -> 홈 복귀 -> 도킹이다.

### Q5. `round` 모드는 뭐냐?

간호사 추종 모드이며, `nurse_tracker`가 OAK-D와 YOLO로 간호사를 찾아 `/robot6/mode/round/cmd_vel`을 만든다.

### Q6. 왜 `mission_manager_node`가 cmd_vel을 최종 발행하나?

Nav2, 추종, 도킹, 안전 정지 같은 여러 제어권이 충돌하지 않도록 한 곳에서 mode priority와 safety gate를 적용하기 위해서다.

### Q7. localization은 어디냐?

`common/loc6.launch.py`가 띄우는 `map_server`와 `amcl`이고, `/robot6/scan`과 map을 비교해서 로봇 pose를 추정한다.

### Q8. Nav2 stack은 어디냐?

`common/nav6.launch.py`가 띄우는 `controller_server`, `planner_server`, `behavior_server`, `bt_navigator`, `velocity_smoother`, costmap 관련 노드들이 Nav2 stack이다.

### Q9. detection은 어디냐?

간호사 detection은 `nurse_tracker/perception.py`이며, OAK-D RGB-D와 YOLO로 nurse를 찾는다. 바닥 요철 detection은 선택 노드 `obstacle_detector/obstacle_node.py`다.

### Q10. 웹의 `tracking`, `done` phase는 실제로 쓰이나?

프론트에는 `idle`, `arrived`, `tracking`, `done`이 정의되어 있지만, 현재 `db_node` 코드에서 실제로 RTDB에 쓰는 nurse cart phase는 `arrived`와 mission 종료 시 `idle`만 확인된다. 발표에서는 “화면 상태 정의는 확장되어 있지만 현재 브리지 구현은 arrived 중심”이라고 말하는 것이 안전하다.

### Q11. `PRIMARY_NS`가 왜 중요하나?

`/api/nurse_cart/start`, `/api/nurse_cart/ocr_done`, `/api/nurse_cart/round_done`은 모두 backend의 `PRIMARY_NS`를 사용하므로, ROBOT6 시연에서는 backend와 frontend 모두 `robot6`로 맞춰야 한다.

### Q12. Next/Flask 웹과 dashboard 웹 차이는?

Next/Flask 웹은 Firebase mission_pool을 통해 로봇을 제어하고, dashboard 웹은 ROS action을 직접 호출하는 별도 운영자용 대시보드다.

## 9. 현재 코드 기준 주의점

1. `PRIMARY_NS` 기본값은 `robot3`다. ROBOT6 시연은 env override가 필요하다.
2. `nurse_cart/phase=tracking`, `done`을 RTDB에 쓰는 코드가 현재 확인되지 않는다.
3. telemetry SSE 화면은 RTDB snapshot producer bridge가 별도로 필요하다.
4. `scenario_b.launch.py` 주석의 `inject_ocr_done.py`는 현재 파일명과 맞지 않는다. 실제 파일은 `trigger_nurse_cart.py`다.
5. `obstacle_detector`는 선택 실행이며 현재 mission_manager safety gate와 직접 연결된 구조는 아니다.
6. OCR은 robot6 ROS 노드가 아니라 웹 backend와 브라우저 카메라 중심이다.
7. `dashboard` 패키지 파일 두 개가 로컬에서 수정된 상태였으므로, dashboard 쪽 설명은 현재 로컬 수정 포함 코드 기준이다.

## 10. 발표용 짧은 설명

ROBOT6는 Firebase mission queue를 통해 웹 명령을 받고, `db_node`가 이를 ROS `mission_request`로 변환하며, `mission_manager_node`가 Nav2 이동, 도킹, 모드 전환, 간호사 추종 시나리오를 총괄합니다. 시나리오 B에서는 웹의 회진 시작 버튼이 `nurse_cart_mission`을 만들고, 로봇은 약품실로 이동한 뒤 OCR 완료 신호를 기다렸다가 간호사 추종을 시작하며, 회진 종료 신호를 받으면 홈으로 복귀해 도킹합니다. 간호사 추종은 OAK-D RGB-D와 YOLO 기반 `nurse_tracker`가 담당하고, 최종 속도 명령은 `mission_manager_node`가 safety gate와 mode priority를 적용해 `/robot6/cmd_vel`로 내보냅니다.
