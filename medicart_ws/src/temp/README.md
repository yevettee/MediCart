# temp/capture_gui — robot6 RGB 뷰어 + YOLO11 데이터셋 캡처

robot6(192.168.109.106) OAK-D **compressed RGB만** ~10fps 표시 + **dualsense_teleop 자동 기동**(수동 주행)
+ **[캡처] 토글 ON** 시 0.5초마다 1장 저장(`temp/dataset/`).

> colcon 패키지 아님(임시 도구) — `python3` 로 직접 실행.

## 실행
RGB 수신에 필요한 디스커버리 env(RMW=rmw_fastrtps_cpp · ROS_DISCOVERY_SERVER · 도메인)는
**GUI가 `MediCart/common/robot.env` 에서 자동 설정**한다(셸 소싱 불필요). 로봇이 FastDDS
디스커버리 서버 뒤에 있어 이게 없으면 0 수신이라, 이 self-config 가 핵심.

```bash
source /opt/ros/humble/setup.bash
source ~/rokey_ws/install/setup.bash               # (선택) dualsense_teleop 주행용 — 미소싱 시 뷰·캡처만 동작
python3 ~/MediCart/medicart_ws/src/temp/capture_gui.py
```
- RGB 뷰·캡처: 위만으로 동작(robot.env 기반 self-config).
- dualsense 주행: `ros2 run dualsense_teleop teleop` 가 resolve 되려면 `rokey_ws/install` source 필요(서브프로세스가 GUI env 상속 → 디스커버리는 자동).

## 사용
- 창에 robot6 RGB가 ~10fps로 표시(프레임 안 오면 디스커버리/로봇 확인).
- **dualsense_teleop**이 자동 기동돼 컨트롤러로 robot6 주행(→ `/robot6/cmd_vel`). ⚠ 실제 로봇 이동.
- **[캡처 시작]** 누르면 0.5초마다 `temp/dataset/frame_<시각>.jpg` 저장, 다시 누르면 정지.
- 저장 장수·경로는 하단 상태바 표시. 창 닫으면 teleop도 종료.

## 메모
- RGB는 사전에 10fps로 발행되도록 튜닝돼 있음(OAK-D). GUI는 들어오는 프레임을 표시·저장.
- dualsense_teleop 미기동 시(rokey_ws 미source 등) 캡처/뷰는 정상 동작, 주행만 불가.
- 데이터셋만 모을 거면 컨트롤러 없이도 [캡처]로 저장 가능.
