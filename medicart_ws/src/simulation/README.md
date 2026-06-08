# simulation

MediCart 병원 Gazebo(Ignition Fortress) 시뮬레이션 패키지.

**turtlebot4_ws 를 수정하지 않습니다.** 설치된 `turtlebot4_ignition_bringup` /
`turtlebot4_navigation` launch 를 include 하되, world·params·map 을 인자로 주입해
이 패키지 안에서 self-contained 로 동작합니다. 팀원은 `turtlebot4_ws` 표준 설치 +
이 repo `colcon build` 만 하면 됩니다.

## 선행 조건
- `turtlebot4_ws` 가 빌드/설치되어 `source ~/turtlebot4_ws/install/setup.bash` 가능
- Ignition(Gazebo) Fortress, `ros_gz_sim` 설치

## 빌드
```bash
cd ~/MediCart/medicart_ws
colcon build --packages-select simulation
source install/setup.bash
```

## 환경 설정 (팀원 각자 1회)
`.bashrc` 는 repo 에 포함되지 않으므로, 매 터미널 자동 적용하려면 각자 추가하세요
(`turtlebot4_ws` source 와 `IGNITION_VERSION=fortress` 는 이미 있다고 가정):
```bash
echo '[ -f ~/MediCart/medicart_ws/install/setup.bash ] && source ~/MediCart/medicart_ws/install/setup.bash' >> ~/.bashrc
```
시뮬은 SIM 모드(`ROS_DOMAIN_ID=0`, `ROS_LOCALHOST_ONLY=1`)에서 실행하세요.

## 실행
```bash
# 1) 병원 world + TurtleBot4 spawn (방 중앙 원점)
ros2 launch simulation hospital_sim.launch.py            # rviz:=true 가능

# 2) 매핑 (별도 터미널): SLAM 띄우고 teleop 으로 방 한 바퀴
ros2 launch simulation slam.launch.py
ros2 run nav2_map_server map_saver_cli -f \
  ~/MediCart/medicart_ws/src/simulation/maps/hospital_map

# 3) 자율주행: 저장한 맵 위에서 localization + Nav2
ros2 launch simulation nav2.launch.py
```

## world 구조
- 현재: 6.0 x 4.75 m 사각형 방 + 시나리오 A 소품(병상 + 환자). 방 중심 = 원점.
- 생성기: [worlds/generate_hospital_world.py](worlds/generate_hospital_world.py)
  (self-contained, SDF 헤더 내장). 상수(W/H, 침대 위치)를 바꾸고 재생성:
  ```bash
  python3 worlds/generate_hospital_world.py            # hospital.sdf 재생성
  python3 worlds/generate_hospital_world.py --preview  # ASCII 미리보기
  ```
- 복도/병실 확장 시 `make_walls()` 의 벽 선분 리스트에 `(x1,y1,x2,y2)` 추가.

## 파일
| 경로 | 설명 |
|------|------|
| `worlds/hospital.sdf` | 생성된 병원 world (커밋됨) |
| `worlds/generate_hospital_world.py` | world 생성기 |
| `config/slam.yaml` | 방 크기에 맞춘 SLAM 튜닝 (max_laser_range 8.0 등) |
| `config/nav2.yaml` | 좁은 공간 costmap inflation 튜닝 |
| `maps/` | SLAM 으로 저장한 맵 (`hospital_map.{pgm,yaml}`) |
| `launch/hospital_sim.launch.py` | world + 로봇 + 브릿지 |
| `launch/slam.launch.py` | tb4 SLAM 래퍼 (우리 slam.yaml 주입) |
| `launch/nav2.launch.py` | tb4 localization+Nav2 래퍼 (우리 nav2.yaml/map 주입) |
