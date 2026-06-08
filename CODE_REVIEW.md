# 처치실 약품 OCR 검증 시스템 — 코드 리뷰 자료

## 1. 시스템 개요

병동 순찰 로봇(MediCart)이 약품실에 도착했을 때, 간호사가 약품 라벨을 웹캠으로 스캔하여  
**처방된 환자에게 맞는 약인지 자동으로 검증하고 DB에 기록**하는 시스템.

---

## 2. 전체 시스템 아키텍처

```
┌─────────────────────────────────────────────────────┐
│                   Browser (Next.js)                  │
│                                                      │
│  처치실 페이지 (/ocr)                                 │
│  ① 환자 선택  ② 처방 확인  ③ 웹캠 스캔  ④ 검증      │
└───────────────────┬─────────────────────────────────┘
                    │ REST API (HTTP)
                    ▼
┌─────────────────────────────────────────────────────┐
│                 Flask Backend (:5000)                 │
│                                                      │
│  app.py          — REST API 엔드포인트               │
│  ocr.py          — GCP Vision API 호출               │
│  fb_read.py      — Firebase RTDB 읽기/쓰기           │
│  _check_medicine — 약품명 매칭 로직                  │
└────────┬──────────────────┬───────────────────────┘
         │                  │
         ▼                  ▼
┌─────────────┐   ┌──────────────────────┐
│ GCP Vision  │   │  Firebase RTDB       │
│ API (유료)  │   │  patients/{pid}/     │
│             │   │    injections/{id}/  │
│ 텍스트 인식  │   │      status          │
└─────────────┘   └──────────────────────┘
```

---

## 3. 기술 선택 이유

### OCR 엔진: GCP Vision API (유료) vs EasyOCR (무료)

| 항목 | EasyOCR (무료) | GCP Vision API (유료) |
|---|---|---|
| 인식 대상 | 일반 텍스트 | **문서/라벨 특화** |
| 소형 텍스트 | 약함 | **강함** |
| 한글 지원 | 보통 | **우수** |
| 서버 부하 | CPU 100% 점유 | 없음 (API 호출) |
| 처리 속도 | 3~10초 | **1초 이내** |
| 비용 | 무료 | 1,000건당 $1.5 |

**선택 이유**: 약품 라벨은 작은 글씨 + 복잡한 배경 → 정확도가 생명. 병원 환경에서 오인식은 투약 사고로 이어질 수 있으므로 정확도 우선 선택.

또한 `DOCUMENT_TEXT_DETECTION` 모드는 일반 `TEXT_DETECTION`보다 문서 구조를 이해해서 줄바꿈, 단어 순서를 더 정확하게 처리함.

```python
# ocr.py
response = client.document_text_detection(image=image)
text = response.full_text_annotation.text.strip()
```

---

### DB: Firebase Realtime DB

**선택 이유:**
- 기존 MediCart 팀 전체가 이미 사용 중인 DB → 새로운 인프라 추가 없음
- 실시간 동기화: 로봇, 웹, 간호사 단말 모두 같은 DB를 바라봄
- NoSQL 구조가 환자별 중첩 데이터(injections) 표현에 적합

```
Firebase RTDB 구조:
patients/
  P-2026-0001/
    injections/
      inj001/
        약품명: "호르몬 주사"
        status: "confirmed"       ← 투약 준비 완료
        verified_at: 1234567890
        ocr_text: "hormone 1mL"
```

---

### 프론트엔드: Next.js + React

**선택 이유:**
- 기존 jaehoon 브랜치 웹 프로젝트와 동일한 스택 → 추가 학습 없이 이식
- React의 상태 관리(`useState`, `useEffect`)로 웹캠 → OCR → 검증 흐름을 명확하게 표현
- 서버사이드 미들웨어로 인증 처리 (쿠키 기반 접근 통제)

---

## 4. 핵심 설계 결정

### 4-1. 인증 분리 구조

단순히 API Key를 환경변수에 넣는 것이 아니라 **두 서버(Flask + Next.js)가 동일한 토큰을 공유**하는 구조.

```
로그인 요청 → Flask가 쿠키 발급 (AUTH_TOKEN)
페이지 접근 → Next.js 미들웨어가 동일 쿠키 검증
API 호출    → Flask가 쿠키 검증
```

Flask와 Next.js가 `INTEL_AUTH_TOKEN`을 공유하므로 로그인 한 번으로 양쪽 모두 통과.

```python
# app.py — 타이밍 공격 방지
def _ct_eq(a, b):
    return hmac.compare_digest(str(a or ""), str(b or ""))
```

일반 `==` 비교 대신 `hmac.compare_digest` 사용 → 문자열 비교 시간이 일정해서 타이밍 공격 불가.

---

### 4-2. GCP 키 인증 방식

```python
# ocr.py
creds = service_account.Credentials.from_service_account_file(
    key_path, scopes=["https://www.googleapis.com/auth/cloud-vision"]
)
_client = vision.ImageAnnotatorClient(credentials=creds)
```

**왜 명시적 credentials를 쓰는가?**

Firebase도 서비스 계정 키를 사용하는데, `GOOGLE_APPLICATION_CREDENTIALS` 환경변수를 쓰면 두 키가 충돌함. GCP Vision은 명시적으로 키를 로드해서 충돌 방지.

**싱글톤 패턴:**
```python
_client = None

def _get_client():
    global _client
    if _client is not None:
        return _client   # 이미 만들어진 클라이언트 재사용
    ...
```
매 요청마다 클라이언트를 새로 만들면 인증 오버헤드 발생 → 최초 1회만 생성 후 재사용.

---

### 4-3. 약품명 매칭 로직

약품 라벨은 영어로 표기되고, DB 처방은 한글로 저장됨 → **별명 매핑 테이블** 설계.

```python
_MEDICINE_ALIASES = {
    "호르몬 주사": ["hormone", "insulin", "estrogen", ...],
    "비타민 주사": ["vitamin", "ascorbic", "b12", ...],
    "스테로이드 주사": ["steroid", "dexamethasone", ...],
}
```

**3단계 매칭:**
1. 직접 포함 (`호르몬 주사` in OCR 텍스트)
2. 공백 제거 후 매칭 (`호르몬주사` 대응)
3. 영문 별명 매칭 (`hormone` in OCR 텍스트)

**OCR 정규화:**
```python
ocr_normalized = " ".join(ocr_text.split())  # 줄바꿈 → 공백
```
OCR이 `호르몬\n주사`로 인식해도 `호르몬 주사`로 처리.

---

### 4-4. IDOR 방지 (보안)

환자 ID를 URL 파라미터로 받을 때 정규식으로 형식 검증:

```python
_PID_RE = re.compile(r"^P-\d{4}-\d{4}$")

@app.get("/api/patients/<pid>/injections")
def patient_injections(pid):
    if not _PID_RE.match(pid):
        return jsonify({"error": "invalid id"}), 400
```

`P-2026-0001` 형식이 아니면 즉시 400 반환 → 임의 키로 DB 탐색(IDOR) 불가.

---

### 4-5. 웹캠 디바이스 선택

브라우저 API만으로 USB 외부 카메라를 자동 선택하는 로직:

```typescript
// 1단계: 임시로 아무 카메라 열어서 브라우저 권한 취득
const tempStream = await navigator.mediaDevices.getUserMedia({ video: true });

// 2단계: 권한 취득 후 라벨 접근 가능 → USB 카메라 찾기
const usbCam = cams.find(
  (d) => !/integrated|facetime|built.?in/i.test(d.label)
);

// 3단계: 이미 USB 캠이면 재사용, 아니면 교체
if (usbCam && tempDeviceId !== usbCam.deviceId) {
  tempStream.getTracks().forEach((t) => t.stop());
  stream = await getUserMedia({ video: { deviceId: { exact: usbCam.deviceId } } });
}
```

**왜 2단계로 나눴는가?**
브라우저는 보안상 권한 없이 `enumerateDevices()`의 라벨을 반환하지 않음. 먼저 권한을 얻은 뒤 라벨로 구분해야 함.

---

## 5. API 설계

### REST Endpoints (추가된 것)

```
GET  /api/patients/{pid}/injections
     → 환자의 주사 처방 목록 반환

POST /api/patients/{pid}/injections/{inj_id}/verify
     Body: { ocr_text: "...", prescription: "호르몬 주사" }
     → 약품 비교 후 DB 업데이트
     Response: { match: bool, status: string, reason: string }
```

### 데이터 흐름

```
① 웹캠 프레임 캡처 (Canvas → Blob)
② POST /api/ocr  →  GCP Vision API  →  텍스트 반환
③ POST /api/patients/{pid}/injections/{inj_id}/verify
       → _check_medicine() 비교
       → Firebase update_injection_status()
④ 결과 렌더링 (투약 준비 완료 / 불일치)
```

---

## 6. 개선 가능한 부분 (리뷰 대비)

| 항목 | 현재 | 개선 방향 |
|---|---|---|
| 매칭 정확도 | 키워드 포함 여부 | 유사도 점수(cosine similarity) 도입 |
| OCR 전처리 | 없음 | CLAHE 대비 강조 후 전송 |
| 인증 | 단일 공유 비밀번호 | 개인별 계정 + JWT |
| 에러 처리 | 단순 문자열 반환 | 에러 코드 체계화 |
| 투약 이력 | 단일 상태만 저장 | 타임스탬프별 이력 누적 |

---

## 7. 한 줄 요약 (발표용)

> "약품 라벨 인식에는 정확도가 최우선이라 GCP Vision API를 선택했고,  
> 기존 팀 인프라(Firebase)를 그대로 활용해 새로운 서버 없이 투약 검증 상태를 실시간으로 공유합니다."
