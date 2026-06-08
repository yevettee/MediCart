# MediCart — Gazebo 시뮬레이션 설치 & 실행 가이드

병원 환경 TurtleBot4 시뮬레이션을 **처음부터** 세팅하는 안내서입니다.
**turtlebot4_ws 같은 별도 워크스페이스가 없어도** 됩니다 — 이 repo 의
`simulation` 패키지가 필요한 TurtleBot4 시뮬 패키지를 `package.xml` 의존성으로
선언하고 있어, `rosdep` 이 apt 로 전부 설치해 줍니다. (기존 `turtlebot4_ws` 는
**전혀 수정하지 않습니다.**)

> 동작 환경: **Ubuntu 22.04 + ROS 2 Humble + Ignition Gazebo Fortress**

---

## 0. 한눈에 보기 (이미 ROS2/Gazebo 가 깔린 사람)

```bash
# 1) repo 클론
cd ~ && git clone <이 repo 주소> MediCart

# 2) 의존성 설치 (turtlebot4 시뮬 + Gazebo Fortress 까지 자동)
cd ~/MediCart/medicart_ws
rosdep install --from-paths src --ignore-src -r -y

# 3) 빌드
colcon build
source install/setup.bash

# 4) 실행 (병원 world + TB4 1대)
ros2 launch simulation hospital_sim.launch.py
```

처음 세팅이면 아래 1~5 단계를 따르세요.

---

## 1. ROS 2 Humble 설치

이미 있으면 건너뛰세요. 없으면 공식 문서대로 `ros-humble-desktop` 설치:
- https://docs.ros.org/en/humble/Installation/Ubuntu-Install-Debs.html

```bash
source /opt/ros/humble/setup.bash
ros2 --version    # 확인
```

`rosdep` 최초 1회 초기화:
```bash
sudo apt install python3-rosdep
sudo rosdep init   # 이미 했으면 에러 무시
rosdep update
```

---

## 2. Ignition Gazebo Fortress 설치

ROS 2 용 `ros-gz`(브리지)와 Ignition Fortress 를 설치합니다.
**대부분 아래 3단계의 `rosdep` 으로 자동 설치**되지만, 수동으로 미리 깔려면:

```bash
sudo apt-get update && sudo apt-get install lsb-release wget gnupg
sudo wget https://packages.osrfoundation.org/gazebo.gpg -O /usr/share/keyrings/pkgs-osrf-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/pkgs-osrf-archive-keyring.gpg] http://packages.osrfoundation.org/gazebo/ubuntu-stable $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/gazebo-stable.list > /dev/null
sudo apt-get update
sudo apt-get install ignition-fortress
```
- 공식 설치 문서: https://gazebosim.org/docs/fortress/install_ubuntu
- 확인: `ign gazebo --version`  (Fortress = 6.x)

---

## 3. MediCart 클론 & 의존성 설치

```bash
cd ~
git clone https://github.com/yevettee/MediCart.git
cd ~/MediCart/medicart_ws

# simulation/package.xml 의 의존성을 apt 로 설치한다.
# → turtlebot4_ignition_bringup, turtlebot4_navigation, ros_gz_sim,
#   nav2_map_server 및 그 의존(create3 시뮬, description, ros-gz, ignition fortress)이 깔린다.
rosdep install --from-paths src --ignore-src -r -y
```

> `rosdep` 이 turtlebot4 패키지를 못 찾으면 직접 apt 설치:
> ```bash
> sudo apt install ros-humble-turtlebot4-simulator ros-humble-turtlebot4-navigation \
>                  ros-humble-turtlebot4-description ros-humble-nav2-map-server
> ```

---

## 4. 빌드

```bash
cd ~/MediCart/medicart_ws
colcon build
source install/setup.bash
```

---

## 5. `.bashrc` 설정 (각자 1회)

매 터미널에서 자동 적용되도록 `~/.bashrc` 끝에 추가합니다.
**`.bashrc` 는 repo 에 포함되지 않으므로 각자 추가해야 합니다.**

```bash
# ===== ROS 2 / MediCart 시뮬 =====
source /opt/ros/humble/setup.bash
# MediCart 워크스페이스 (빌드 전이면 조용히 skip)
[ -f ~/MediCart/medicart_ws/install/setup.bash ] && source ~/MediCart/medicart_ws/install/setup.bash

export IGNITION_VERSION=fortress

# 시뮬은 SIM 모드: 같은 PC 안에서만 통신(localhost), 도메인 0
export ROS_DOMAIN_ID=0
export ROS_LOCALHOST_ONLY=1
unset ROS_DISCOVERY_SERVER ROS_SUPER_CLIENT
```

> **turtlebot4_ws 를 source 빌드로 따로 쓰는 경우에만** 그 워크스페이스도 source 하세요
> (`source ~/turtlebot4_ws/install/setup.bash`). apt(rosdep)로 깔았다면 불필요합니다.

적용:
```bash
source ~/.bashrc
```

---

## 6. 실행

```bash
# (A) 병원 world + TurtleBot4 1대 (도킹스테이션 위치에 spawn)
ros2 launch simulation hospital_sim.launch.py            # rviz:=true 가능

# 토픽 확인 (시뮬이 떠 있는 상태에서, 다른 터미널)
ros2 topic list | grep -E "scan|oakd"
ros2 run rqt_image_view rqt_image_view    # /oakd/rgb/preview/image_raw 선택
```

### 매핑(SLAM) → 맵 저장
```bash
# 1) 위 hospital_sim 을 띄워둔 채로, 다른 터미널에서:
ros2 launch simulation slam.launch.py
# 2) teleop 으로 방을 한 바퀴 돌며 매핑
ros2 run teleop_twist_keyboard teleop_twist_keyboard
# 3) 맵 저장
ros2 run nav2_map_server map_saver_cli -f \
  ~/MediCart/medicart_ws/src/simulation/maps/hospital_map
```

### 자율주행(Nav2)
```bash
ros2 launch simulation nav2.launch.py     # maps/hospital_map.yaml 사용
```

> 자세한 world/launch 구조는 [medicart_ws/src/simulation/README.md](medicart_ws/src/simulation/README.md) 참고.

---

## 7. 트러블슈팅

| 증상 | 원인 / 해결 |
|------|------|
| `package 'simulation' not found` | 빌드 후 `source install/setup.bash` 안 함. 새 터미널은 `.bashrc` 설정(5장) 필요 |
| Gazebo 는 뜨는데 `/scan`·카메라 토픽이 없음 | SIM 모드 환경변수 미설정. `ROS_DOMAIN_ID=0`, `ROS_LOCALHOST_ONLY=1` 확인. 토픽은 **시뮬이 떠 있는 동안만** 보임 |
| `package '...' not found` 가 launch 중 발생 (예: 지워진 패키지) | `--symlink-install` 잔재. `rm -rf build install log && colcon build` 로 클린 재빌드 |
| `ign gazebo --version` 없음 | 2장 Gazebo Fortress 설치 |
| 실로봇 모드와 충돌 | 실로봇은 `ROS_DOMAIN_ID=6` + discovery server 사용. 시뮬은 도메인 0/localhost 로 **분리** — 새 터미널에서 시뮬 환경변수로 실행 |

---

## 참고: 설계 원칙

- 이 시뮬은 **turtlebot4_ws(또는 apt 설치된 tb4 패키지)를 수정하지 않습니다.**
  설치된 `turtlebot4_ignition_bringup` / `turtlebot4_navigation` launch 를
  include 하되, **world·params·map 을 인자로 주입**해 `simulation` 패키지 안에서
  self-contained 로 동작합니다.
- 병원 world 는 `simulation/worlds/generate_hospital_world.py` 로 생성됩니다
  (SDF 헤더 내장, 좌하단 원점, 벽 두께/높이·방 치수 상수화).
