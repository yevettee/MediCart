# MediCart OCR 약물 검증 시스템

약품을 카메라에 비추면 OCR로 텍스트를 읽고, 환자의 처방 정보와 비교해서 맞는 약인지 확인해주는 시스템이에요.

---

## 📁 전체 구조

```
ocr_ws/
├── src/
│   ├── ocr_interfaces/        # ROS2 서비스 메시지 정의
│   └── ocr_detector/          # OCR 노드 패키지
│       ├── credentials/       # ← 키 파일을 여기에 넣어야 해요! (GitHub에는 없음)
│       │   ├── gcp_vision_key.json    (슬랙에서 받은 파일)
│       │   └── firebase_key.json      (슬랙에서 받은 파일)
│       ├── ocr_detector/
│       │   ├── web_node.py    # 웹 화면 (Gradio)
│       │   ├── ocr_node.py    # ROS2 노드
│       │   ├── db_bridge.py   # Firebase 연동
│       │   ├── medicine_checker.py  # 약물 대조
│       │   └── engines/
│       │       ├── easyocr_engine.py  # 무료 OCR
│       │       └── gcp_engine.py      # 유료 OCR (GCP)
│       └── launch/
│           ├── ocr_web.launch.py      # 웹UI 실행용 (주로 이거 씀)
│           └── ocr_webcam.launch.py   # 웹UI 없이 실행
└── README.md
```

---

## 🔑 1단계 — 키 파일 받아서 넣기

> 슬랙에서 키 파일 2개를 받아주세요.
> - `gcp_vision_key.json`
> - `firebase_key.json`

### 키 파일 넣는 위치

터미널을 열고 아래 명령어를 입력하세요.

```bash
# credentials 폴더 만들기
mkdir -p ~/ocr_ws/src/ocr_detector/credentials
```

받은 키 파일 2개를 이 폴더 안에 넣어주세요.

| 파일 이름 | 넣어야 할 경로 |
|-----------|---------------|
| `gcp_vision_key.json` | `~/ocr_ws/src/ocr_detector/credentials/gcp_vision_key.json` |
| `firebase_key.json` | `~/ocr_ws/src/ocr_detector/credentials/firebase_key.json` |

**파일 탐색기로 넣는 방법:**

1. 파일 탐색기 열기
2. 주소창에 `/home/rokey/ocr_ws/src/ocr_detector/credentials` 입력
3. 받은 파일 2개를 이 폴더에 복사

> ⚠️ 폴더 이름, 파일 이름이 정확히 같아야 해요. 오타 나면 실행이 안 돼요.

---

## 💻 2단계 — 필요한 패키지 설치

터미널에서 아래를 하나씩 입력해주세요.

```bash
# EasyOCR 설치
pip install easyocr

# Gradio 설치 (웹 화면)
pip install gradio

# Firebase 설치
pip install firebase-admin

# GCP Vision API 설치
pip install google-cloud-vision
```

---

## 🔨 3단계 — 빌드하기

```bash
# ocr_ws 폴더로 이동
cd ~/ocr_ws

# ROS2 환경 불러오기
source /opt/ros/humble/setup.bash

# 빌드
colcon build --symlink-install
```

`Summary: 2 packages finished` 라고 뜨면 성공이에요!

---

## ▶️ 4단계 — 실행하기

```bash
# ocr_ws 폴더로 이동
cd ~/ocr_ws

# 빌드 결과 불러오기
source install/setup.bash

# 실행 (무료 EasyOCR 버전)
ros2 launch ocr_detector ocr_web.launch.py engine:=easyocr
```

실행하면 터미널에 이런 메시지가 뜨면서 로딩이 시작돼요:

```
Using CPU. Note: This module is much faster with a GPU.
[INFO] ocr_web_node started  engine=easyocr  webcam=2  port=7864
```

> ⏳ EasyOCR 모델 로딩에 10~30초 정도 걸려요. 기다려 주세요!

---

## 🌐 5단계 — 웹 화면 열기

브라우저(크롬 등)를 열고 주소창에 입력해주세요:

```
http://localhost:7864
```

---

## 📷 사용 방법

1. **환자 선택** 드롭다운에서 환자 이름 선택
2. 오른쪽에 **처방 주사 정보** 자동으로 표시됨
3. 약품을 웹캠에 비추기
4. **📷 OCR 스캔** 버튼 클릭 → 약품 텍스트 인식
5. **✅ 투약 확인 (DB 업데이트)** 버튼 클릭
6. 검증 결과 확인
   - `✅ 일치` → Firebase DB에서 상태가 **완료**로 바뀜
   - `⚠️ 불일치` → Firebase DB에서 상태가 **불일치**로 바뀜

---

## 🔄 GCP Vision API (유료) 버전으로 실행하기

인식률이 더 높은 버전이에요. (월 1,000회 무료)

```bash
ros2 launch ocr_detector ocr_web.launch.py engine:=gcp
```

---

## 🚧 자주 발생하는 오류

### "Cannot open webcam device 2"
외부 웹캠이 연결되어 있는지 확인하세요. 다른 번호를 써야 할 수도 있어요:
```bash
ros2 launch ocr_detector ocr_web.launch.py engine:=easyocr webcam_device:=0
```

### "OSError: Cannot find empty port in range: 7864"
이미 실행 중인 프로그램이 있어요. 터미널에서 아래 명령어로 종료하세요:
```bash
pkill -f ocr_web
```

### 키 파일 관련 오류
`credentials` 폴더 안에 파일이 제대로 들어있는지 확인하세요:
```bash
ls ~/ocr_ws/src/ocr_detector/credentials/
# 아래 두 파일이 보여야 해요:
# gcp_vision_key.json
# firebase_key.json
```

---

## 📡 ROS2 토픽

OCR 결과는 ROS2 토픽으로도 확인할 수 있어요:

```bash
ros2 topic echo /ocr_result
```

---

## 🔥 Firebase DB 확인

```
https://console.firebase.google.com/project/medi-cart-ea39f/database/medi-cart-ea39f-default-rtdb/data
```
