# OCR 데모

이미지/웹캠에서 텍스트를 추출하는 Gradio 웹 UI 데모입니다.

| 파일 | 방식 | 특징 |
|---|---|---|
| `ocr_demo.py` | Google Cloud Vision API | 높은 정확도, API 키 필요 |
| `ocr_realtime.py` | EasyOCR (로컬) | 설치만으로 실행, 실시간 웹캠 |

---

## ocr_demo.py (Google Cloud Vision)

### 사전 준비

**1. gcloud CLI 설치 및 인증**

```bash
curl -sSL https://sdk.cloud.google.com | bash
source ~/google-cloud-sdk/path.bash.inc
gcloud auth application-default login
```

**2. 환경변수 설정**

```bash
export GOOGLE_CLOUD_PROJECT="본인의_프로젝트_ID"
```

> Google Cloud Console 상단에서 프로젝트 ID 확인 가능

**3. 라이브러리 설치**

```bash
pip install -r requirements.txt
```

### 실행

```bash
python3 ocr_demo.py
```

브라우저에서 http://127.0.0.1:7860 접속

> Google Cloud Vision API는 월 1,000건까지 무료입니다.

---

## ocr_realtime.py (EasyOCR - 로컬)

API 키 없이 로컬에서 실행되는 실시간 OCR입니다.  
최초 실행 시 모델을 자동으로 다운로드합니다 (약 500MB).

### 사전 준비

```bash
pip install -r requirements.txt
```

### 실행

```bash
python3 ocr_realtime.py
```

브라우저에서 http://127.0.0.1:7863 접속

---

## 주의사항

> **GCP 서비스 계정 키(`*.json`)는 절대 GitHub에 올리지 마세요.**  
> 이 레포지토리의 `.gitignore`가 `*.json` 파일을 자동으로 제외합니다.
