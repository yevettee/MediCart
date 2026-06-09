# web — 병동 보조 로봇 대시보드 (MediCart · jeon 브랜치)

Flask(백엔드 `:5000`) + Next.js(프론트 `:3001`). Firebase RTDB를 **서버측(firebase-admin)** 에서 읽어
SSE/REST로 프론트에 제공. 브라우저는 Next.js(`/api/*`)만 호출하고 RTDB를 직접 만지지 않는다.

## jeon 브랜치 주요 기능

| 기능 | 경로 | 설명 |
|---|---|---|
| 처치실 — 약품 OCR 검증 | `/ocr` | GCP Vision API로 약품 라벨 인식 → 처방 대조 → Firebase 상태 업데이트 |
| 처치실 — QR 환자 확인 | `/ocr` → QR 환자 확인 탭 | 환자 QR 스캔 → 3단계 처방 판정 (처방 완료 / 처방 불가) |
| QR 스캔 | `/qr` | 환자 QR 스캔 → Firebase 업데이트 → 아이폰 문진표 자동 호출 |
| 문진표 | `/intake` | QR 경유 또는 직접 접속 → 외래방문 기록 작성·저장 |

```
backend/   Flask  : fb_read·patients·ocr(GCP Vision)·app(REST/auth/OCR/QR확인)
frontend/  Next.js: app/{map,control,patients,intake,ocr,qr,display,debug}, lib/api
```

---

## 0. 키 파일 준비 (최초 1회 — git에 절대 올리지 않음)

### 필요한 키 파일 2개

| 파일 | 용도 |
|---|---|
| Firebase 서비스 계정 키 (`.json`) | RTDB 읽기/쓰기 |
| GCP Vision API 키 (`gcp_vision_key.json`) | 약품 OCR (유료) |

### Firebase 키 — 자동 탐색

백엔드가 아래 순서로 자동 탐색합니다:
1. 환경변수 `FB_CRED`에 지정된 경로
2. `~/rokey_ws/db_test/medi-cart-*firebase*.json` (팀 표준 위치)

`~/rokey_ws/db_test/` 에 Firebase 키가 있으면 **추가 설정 불필요**.
사용자명이 `rokey`가 아닌 경우 `.env`에 직접 지정:
```
FB_CRED=/home/<본인계정>/rokey_ws/db_test/medi-cart-ea39f-firebase-adminsdk-xxx.json
```

### GCP Vision API 키 — 수동 배치

```bash
mkdir -p ~/MediCart/web/backend/credentials
cp ~/다운로드/gcp_vision_key.json ~/MediCart/web/backend/credentials/gcp_vision_key.json
```

> ✅ `credentials/` 는 `.gitignore`에 등록되어 있어 git에 올라가지 않습니다.

---

## 1. 사전 준비 (최초 1회)

```bash
# (1) 백엔드 의존 설치
cd ~/MediCart/web/backend
pip install -r requirements.txt

# (2) 프론트 의존 설치
cd ~/MediCart/web/frontend
npm install
```

### 백엔드 `.env` 작성

```bash
cd ~/MediCart/web/backend
cp .env.example .env
```

`.env` 필수 항목:

```ini
FB_CRED=/home/<계정>/rokey_ws/db_test/medi-cart-ea39f-firebase-adminsdk-xxx.json
FB_DB_URL=https://medi-cart-ea39f-default-rtdb.asia-southeast1.firebasedatabase.app
INTEL_PASSWORD=rokey1234
INTEL_AUTH_TOKEN=<아래 명령어로 생성>
FRONTEND_ORIGIN=http://localhost:3000,http://localhost:3001
COOKIE_SECURE=0
PORT=5000
```

`INTEL_AUTH_TOKEN` 생성:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 프론트 `.env.local` 작성

```bash
cd ~/MediCart/web/frontend
```

아래 내용으로 `.env.local` 파일 생성:

```ini
# NEXT_PUBLIC_API_BASE는 비워둔다 — Next.js가 /api/* 를 Flask로 프록시
NEXT_PUBLIC_API_BASE=
INTEL_AUTH_TOKEN=<백엔드 .env의 INTEL_AUTH_TOKEN과 동일한 값>
```

> ⚠️ `INTEL_AUTH_TOKEN`은 백엔드 `.env`와 프론트 `.env.local` 에 **반드시 같은 값**이어야 합니다.
> 다르면 로그인해도 모든 페이지가 `/login`으로 튕깁니다.

---

## 2. 로컬 실행

터미널 두 개로 각각 실행합니다.

**터미널 1 — 백엔드**
```bash
cd ~/MediCart/web/backend
set -a && source .env && set +a
python3 app.py
# → http://localhost:5000
```

**터미널 2 — 프론트**
```bash
cd ~/MediCart/web/frontend
npm run dev
# → http://localhost:3001  (3000이 점유된 경우 자동으로 3001 사용)
```

브라우저에서 `http://localhost:3001` 접속 → 비밀번호(`rokey1234`) 입력 → 로그인

---

## 3. 아이폰(모바일) 접속

같은 Wi-Fi에서 아이폰으로 접속하려면 PC의 로컬 IP를 사용합니다.

### PC IP 확인

```bash
hostname -I | tr ' ' '\n' | grep -v '^172\.' | grep -v '^127\.'
# 예: 192.168.123.47
```

### `next.config.ts` 에 해당 IP 추가

```typescript
const nextConfig: NextConfig = {
  allowedDevOrigins: ["192.168.123.47"],  // PC IP로 변경
};
```

추가 후 프론트 재시작 필요.

### 아이폰 접속 주소

```
http://<PC_IP>:3001        # 예: http://192.168.123.47:3001
```

로그인 후 `/display` 페이지로 이동하면 PC QR 스캔 시 문진표가 자동으로 열립니다.

### `FRONTEND_ORIGIN` 업데이트 (CORS)

백엔드 `.env`에 아이폰이 사용하는 origin 추가:
```ini
FRONTEND_ORIGIN=http://localhost:3000,http://localhost:3001,http://192.168.123.47:3001
```

---

## 4. 처치실 사용법 (`/ocr`)

### 단일 스캔 탭 — 약품 OCR 검증

1. **환자 선택** → **주사 처방 선택**
2. **웹캠 켜기** → 약품 라벨에 카메라 조준
3. **스캔 & OCR** — GCP Vision API가 텍스트 인식
4. **약품 적합성 검증 & DB 저장** — 처방과 OCR 결과 비교
   - ✅ 일치 → **투약 준비 완료** (Firebase 상태 `confirmed`)
   - ❌ 불일치 → **약품 불일치 — 재확인 필요** (상태 `mismatch`)

### QR 환자 확인 탭 — 최종 처방 판정

모든 약품 OCR 검증 후 환자 QR을 스캔하면 3단계로 판정합니다.

| 조건 | 결과 |
|---|---|
| 선택 환자 QR + 모든 약품 `confirmed` | ✅ **처방 완료** + 코멘트 |
| 선택 환자 QR + 미확인 약품 있음 | ❌ **처방 불가** + 미완료 약품 목록 |
| 다른 환자 QR | ❌ **처방 불가 — 환자 정보 불일치** + 환자 비교 |

결과 표시 후 **다시 스캔** 버튼으로 초기화할 수 있습니다.

---

## 5. QR 스캔 → 아이폰 문진표 흐름 (`/qr` + `/display`)

1. **아이폰**: `http://<PC_IP>:3001/display` 접속 (로그인 후) — 대기 화면
2. **PC**: `/qr` 페이지에서 환자 QR(`P-YYYY-NNNN` 형식) 스캔
3. Firebase 업데이트 → 아이폰 `/display` 페이지가 감지 → 자동으로 `/intake?pid=...` 이동
4. 아이폰에서 문진표 작성 후 저장

---

## 6. DB 초기화 (테스트 후 전체 리셋)

주사 처방 상태를 전부 **투약 대기중(pending)** 으로 초기화:

```bash
cd ~/MediCart/web/backend
set -a && source .env && set +a
python3 - << 'EOF'
import firebase_admin
from firebase_admin import credentials, db
import os

cred = credentials.Certificate(os.environ["FB_CRED"])
firebase_admin.initialize_app(cred, {"databaseURL": os.environ["FB_DB_URL"]})

pids = ["P-2026-0001","P-2026-0002","P-2026-0003",
        "P-2026-0004","P-2026-0005","P-2026-0006","P-2026-0007"]

for pid in pids:
    ref = db.reference(f"patients/{pid}/injections")
    injections = ref.get()
    if not injections:
        continue
    for inj_id in injections:
        ref.child(inj_id).update({"status": "pending", "ocr_text": None, "verified_at": None})
        print(f"  {pid}/{inj_id} → pending")

print("완료")
EOF
```

---

## 7. 흔한 함정

| 증상 | 원인 | 해결 |
|---|---|---|
| 로그인해도 `/login`으로 튕김 | `INTEL_AUTH_TOKEN` 불일치 또는 미설정 | 백엔드 `.env`와 프론트 `.env.local` 토큰값 일치 확인 |
| OCR 스캔 시 401 오류 | `NEXT_PUBLIC_API_BASE`에 IP가 설정되어 cross-origin 쿠키 전송 불가 | `.env.local`의 `NEXT_PUBLIC_API_BASE=` 를 빈 값으로 유지 |
| 아이폰에서 로그인 불가 (화면 전환 없음) | `allowedDevOrigins`에 PC IP 미등록 | `next.config.ts`에 PC IP 추가 후 프론트 재시작 |
| OCR 오류 "키 파일을 찾을 수 없음" | `gcp_vision_key.json` 미배치 | `web/backend/credentials/` 에 파일 배치 |
| OCR 오류 "Bad image data" | 웹캠이 아직 준비되지 않은 상태에서 스캔 | 웹캠 화면이 보인 후 1~2초 뒤 스캔 |
| 백엔드 `INTEL_PASSWORD / INTEL_AUTH_TOKEN 환경변수를 설정하세요` | `.env` 미로드 | `set -a && source .env && set +a && python3 app.py` 로 실행 |
| Firebase DB 주사 목록 없음 | 환자 데이터에 `injections` 노드 없음 | 팀 DB 관리자에게 시딩 요청 |
| 포트 3000 점유로 3001로 뜰 때 아이폰 접속 안 됨 | `allowedDevOrigins`에 등록된 IP가 맞지 않음 | 실제 뜬 포트 확인 후 `FRONTEND_ORIGIN`도 맞게 수정 |

---

## 8. 빠른 점검

```bash
# 백엔드 API 동작 확인
TOKEN=<INTEL_AUTH_TOKEN>

curl -s http://localhost:5000/api/health
# → {"ok":true}

curl -s http://localhost:5000/api/patients \
  -H "Authorization: Bearer $TOKEN"
# → 환자 목록 JSON

curl -s http://localhost:5000/api/patients/P-2026-0001/injections \
  -H "Authorization: Bearer $TOKEN"
# → 주사 처방 목록
```

페이지 목록: `/`(홈) · `/map`(실시간 관제) · `/control`(로봇 제어) · `/patients`(환자 정보) · `/intake`(문진표) · `/ocr`(처치실) · `/qr`(QR 스캔) · `/display`(아이폰 대기화면) · `/debug`
