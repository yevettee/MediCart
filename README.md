## jeon 브랜치에서 추가된 내용

약품을 카메라에 비추면 OCR로 텍스트를 읽고, 환자의 처방 주사 정보와 비교해서 맞는 약인지 확인하고 Firebase DB에 결과를 저장하는 시스템입니다.

### 🔑 시작 전에 — 키 파일 준비

#### Firebase 키 (각자 이미 가지고 있는 파일)

Firebase 키는 별도로 받을 필요 없어요.  
`~/rokey_ws/db_test/` 안에 `medi-cart-*firebase*.json` 파일이 있으면 **자동으로 찾아서 연결**돼요.

파일이 없거나 다른 곳에 있으면 환경변수로 알려주세요:
```bash
export FIREBASE_KEY_PATH=~/내파일경로/firebase키파일.json
```

#### GCP Vision API 키 (슬랙에서 받기)

유료 버전(GCP)을 쓰려면 슬랙에서 `gcp_vision_key.json` 파일을 받아서 아래 위치에 넣어주세요.

```bash
mkdir -p ~/ocr_ws/src/ocr_detector/credentials
```

| 파일 이름 | 넣어야 할 경로 |
|-----------|---------------|
| `gcp_vision_key.json` | `~/ocr_ws/src/ocr_detector/credentials/gcp_vision_key.json` |

> 무료 버전(EasyOCR)만 쓸 거라면 GCP 키 없어도 돼요.

### 📦 필요한 패키지 설치

```bash
pip install easyocr gradio firebase-admin google-cloud-vision
```

### 🔨 빌드

```bash
cd ~/ocr_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install
```

`Summary: 2 packages finished` 가 뜨면 성공이에요!

### ▶️ 실행

```bash
cd ~/ocr_ws
source install/setup.bash

# 무료 버전 (EasyOCR)
ros2 launch ocr_detector ocr_web.launch.py engine:=easyocr

# 유료 버전 (GCP Vision API, 인식률 더 높음)
ros2 launch ocr_detector ocr_web.launch.py engine:=gcp
```

> ⏳ EasyOCR은 처음 실행 시 모델 로딩에 10~30초 정도 걸려요.

### 🌐 웹 화면 열기

브라우저에서 아래 주소로 접속하세요:

```
http://localhost:7864
```

### 📷 사용 방법

1. **환자 선택** 드롭다운에서 환자 고르기
2. 오른쪽에 **처방 주사 정보** 자동 표시
3. 약품을 웹캠에 비추기
4. **📷 OCR 스캔** 버튼 클릭 → 약품 텍스트 인식
5. **✅ 투약 확인 (DB 업데이트)** 버튼 클릭
6. 결과 확인
   - `✅ 일치` → Firebase DB 상태가 **완료**로 바뀜
   - `⚠️ 불일치` → Firebase DB 상태가 **불일치**로 바뀜

### 🚧 자주 나오는 오류

**웹캠이 안 열릴 때**
```bash
ros2 launch ocr_detector ocr_web.launch.py engine:=easyocr webcam_device:=0
```

**포트가 이미 사용 중일 때**
```bash
pkill -f ocr_web
```

**키 파일이 없다는 오류가 날 때**
```bash
ls ~/ocr_ws/src/ocr_detector/credentials/
# gcp_vision_key.json 과 firebase_key.json 두 파일이 보여야 해요
```

### 🔥 Firebase DB 확인

```
https://console.firebase.google.com/project/medi-cart-ea39f/database/medi-cart-ea39f-default-rtdb/data
```
