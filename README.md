# MediCart 🤖🏥

**병원에서 일하는 똑똑한 도우미 로봇 시스템**

---

## 🩺 MediCart가 뭐예요?

MediCart는 **병원 안을 혼자 돌아다니면서 간호사를 도와주는 로봇**이에요.

로봇이 병실을 직접 찾아다니면서 환자가 제대로 있는지 확인하고,
간호사 선생님을 졸졸 따라다니면서 약이 맞는지 카메라로 확인해줘요.

컴퓨터 화면(웹 대시보드)에서 버튼 하나로 로봇을 움직일 수 있어요.

---

## 🔧 어떤 장비를 써요?

| 장비 | 역할 |
|------|------|
| **TurtleBot4** | 바퀴 달린 로봇 본체 |
| **OAK-D 카메라** | 사람·약품·깊이(거리)를 인식하는 눈 |
| **RPLIDAR** | 장애물을 감지하는 레이더 |
| **라즈베리파이 + 호스트 PC** | 카메라 데이터 전송 및 AI 추론 |

---

## 🚀 두 가지 운영 모드

### 모드 A — 자율 순찰 🚶‍♂️

> 로봇이 스스로 병실을 하나씩 돌아다녀요.

1. 도킹 스테이션에서 출발
2. 병실마다 들어가서 **환자가 있는지** 확인 (YOLO 카메라)
3. QR 코드로 **환자 신원** 확인
4. 확인이 끝나면 **웹 화면에서 문진표 작성**
5. 모든 병실을 다 돌면 다시 스테이션으로 복귀

```
도킹 스테이션 → 병실 1 → 병실 2 → ... → 마지막 병실 → 도킹 스테이션
```

### 모드 B — 간호사 보조 💊

> 로봇이 간호사 선생님을 따라다니면서 약을 확인해줘요.

1. 도킹 스테이션에서 출발
2. 카메라로 간호사를 인식하고 **졸졸 따라감**
3. 병실에 도착하면 **STANDBY** (기다려요)
4. 약품 라벨을 카메라에 보여주면 **AI가 글자를 읽어서** 처방전과 비교
5. 약이 맞으면 ✅, 틀리면 ❌ 알려줘요
6. 다 끝나면 스테이션으로 복귀

---

## 📦 안에 들어있는 것들

```
MediCart/
├── medicart_ws/          # 로봇 두뇌 (ROS2 패키지들)
│   └── src/
│       ├── mission_manager/    # 로봇의 총 지휘관
│       ├── dashboard/          # 운영자 화면 (ROS2 노드)
│       ├── patient_identifier/ # 환자 인식 (YOLO + QR)
│       ├── nurse_tracker/      # 간호사 추적
│       ├── ocr_detector/       # 약품 라벨 글자 읽기
│       ├── scanner/            # OCR 결과 처방 비교
│       ├── db_bridge/          # Firebase DB 연결
│       ├── obstacle_detector/  # 장애물 감지
│       ├── medi_interfaces/    # ROS2 메시지/서비스 타입 정의
│       └── simulation/         # Gazebo 시뮬레이션
├── web/                  # 웹 대시보드
│   ├── backend/          # Flask 서버 (포트 5000)
│   └── frontend/         # Next.js 화면 (포트 3000)
└── docs/                 # 설계 문서
```

---

## 🗺️ 전체 구조 한눈에 보기

```
[ 웹 대시보드 ] ←→ [ mission_manager ] ←→ [ Nav2 자율주행 ]
                           ↕                      ↕
               [ patient_identifier ]       [ TurtleBot4 ]
               [ nurse_tracker      ]
               [ ocr_detector       ]
                           ↕
               [ db_bridge (Firebase) ]
```

- 운영자가 웹 화면에서 버튼을 누르면 `mission_manager`가 받아서 처리해요
- `mission_manager`는 Nav2에 "여기로 가!" 하고 명령해요
- 카메라 패키지들이 사람/약품을 인식하고 결과를 `mission_manager`에 보내요
- 처방 정보는 Firebase DB에서 가져와요

---

## 🖥️ 웹 대시보드 기능

브라우저에서 `http://localhost:3000` 접속하면 아래 기능을 사용할 수 있어요.

| 페이지 | 기능 |
|--------|------|
| `/map` | 실시간 로봇 위치 지도 |
| `/control` | 로봇 제어 (이동·도킹·긴급정지) |
| `/patients` | 환자 목록 |
| `/intake` | 문진표 작성 |
| `/ocr` | 처치실 — 약품 OCR 검증 |

---

## ⚙️ 처음 설치하기

### 필요한 환경

- Ubuntu 22.04
- ROS 2 Humble
- Python 3.10+
- Node.js 18+

### 1단계 — 저장소 받기

```bash
git clone https://github.com/yevettee/MediCart.git
cd MediCart
```

### 2단계 — ROS2 패키지 빌드

```bash
cd medicart_ws
rosdep install --from-paths src --ignore-src -r -y
colcon build
source install/setup.bash
```

### 3단계 — 웹 백엔드 설치

```bash
cd web/backend
pip install -r requirements.txt
cp .env.example .env
# .env 파일 안에 Firebase 키 경로, DB URL 등을 입력하세요
```

### 4단계 — 웹 프론트엔드 설치

```bash
cd web/frontend
npm install
```

### 필요한 키 파일 2개 (팀원에게 받아야 해요)

| 파일 | 용도 |
|------|------|
| Firebase 서비스 계정 키 (`.json`) | 환자 DB 접근 |
| GCP Vision API 키 (`gcp_vision_key.json`) | 약품 라벨 OCR |

> Firebase 키는 `~/rokey_ws/db_test/` 에 두면 자동으로 인식돼요.
> GCP Vision 키는 `web/backend/credentials/gcp_vision_key.json` 위치에 놓으세요.
> **두 파일 모두 절대로 git에 올리지 마세요!** (`.gitignore`에 등록됨)

---

## ▶️ 실행하기

### 로봇 실행 (터미널 4개 필요)

```bash
# 터미널 1 — 지도 서버
loc 6 ~/MediCart/medicart_ws/maps/ninety.yaml

# 터미널 2 — RViz (시각화)
rv 6

# 터미널 3 — Nav2 자율주행
nav 6

# 터미널 4 — 대시보드 노드
cd ~/MediCart/medicart_ws
source install/setup.bash
ros2 run dashboard dashboard_node \
  --ros-args \
  -p action_name:=/robot6/navigate_to_pose \
  -p port:=8080 \
  -p capture_dir:=$HOME/MediCart/medicart_ws/src/dashboard/captures
```

> ⚠️ RViz가 뜨면 반드시 **2D Pose Estimate**로 로봇의 초기 위치를 찍어야 해요.
> 안 하면 로봇이 자기 위치를 몰라서 움직이지 못해요.

### 웹 대시보드 실행 (터미널 2개 필요)

```bash
# 터미널 1 — 백엔드
cd MediCart/web/backend
set -a && source .env && set +a
python3 app.py
# → http://localhost:5000

# 터미널 2 — 프론트엔드
cd MediCart/web/frontend
npm run dev -- --port 3000
# → http://localhost:3000
```

### Gazebo 시뮬레이션으로 테스트하기

실제 로봇 없이도 테스트할 수 있어요!

```bash
cd medicart_ws
source install/setup.bash
ros2 launch simulation hospital_sim.launch.py
```

---

## 📡 주요 ROS2 토픽

```
/robot6/navigate_to_pose    # 목표 위치 이동 명령
/robot6/dock                # 도킹 (충전 스테이션 연결)
/robot6/undock              # 언도킹
/robot6/robot_state         # 현재 로봇 상태
/robot6/patient_identified  # 환자 인식 결과
/robot6/target_pose         # 간호사 추적 위치
/robot6/oakd/rgb/image_raw/compressed       # RGB 카메라
/robot6/oakd/stereo/image_raw/compressedDepth  # 깊이 카메라
```

---

## 🔥 자주 겪는 문제

| 증상 | 원인 | 해결 방법 |
|------|------|-----------|
| 로그인해도 `/login`으로 계속 튕김 | 프론트·백엔드 `INTEL_AUTH_TOKEN` 값이 다름 | 두 `.env` 파일의 토큰값을 똑같이 맞추기 |
| 프론트가 포트 5000 충돌 | 백엔드 `.env`의 `PORT` 값을 상속 | `npm run dev -- --port 3000` 으로 실행 |
| OCR 오류 "키 파일을 찾을 수 없음" | `gcp_vision_key.json` 미배치 | `web/backend/credentials/` 에 파일 놓기 |
| 로봇이 위치를 못 찾고 멈춤 | RViz에서 초기 위치 미설정 | **2D Pose Estimate**로 위치 찍기 |
| Firebase DB 데이터 없음 | 환자 데이터 미입력 | 팀 DB 관리자에게 시딩 요청 |

---

## 📁 상세 문서

더 자세한 내용은 `docs/` 폴더를 확인하세요.

| 문서 | 내용 |
|------|------|
| [시스템 아키텍처](docs/architecture/01_system_architecture.md) | 전체 구조·데이터 흐름 |
| [ROS2 패키지 설명](docs/architecture/02_ros2_packages.md) | 패키지별 역할·구현 현황 |
| [ROS2 인터페이스](docs/architecture/03_ros2_interfaces.md) | 토픽·서비스·액션 목록 |
| [DB 스키마](docs/architecture/04_db_schema.md) | Firebase 데이터 구조 |
| [웹 대시보드](web/README.md) | 웹 앱 설치·실행·사용법 |
| [Gazebo 시뮬레이션](gazebo_readme.md) | 시뮬레이션 세팅 가이드 |

---

> 로봇이 이동하려면 **Nav2 + 지도 서버 + RViz 초기 위치 설정**이 모두 갖춰져야 해요.
> 하나라도 빠지면 로봇이 움직이지 않으니 순서대로 실행하세요!
