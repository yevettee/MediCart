# MediCart jeon 브랜치 작업 정리

## 개요

병동 보조 로봇 웹 대시보드(jaehoon 브랜치)에 **처치실(약품 OCR 검증)** 기능을 추가하고 jeon 브랜치로 관리.

---

## 구현한 기능

### 1. 처치실 페이지 (`/ocr`)

| 기능 | 설명 |
|---|---|
| 환자 선택 | Firebase DB에서 환자 목록 로드, 드롭다운 선택 |
| 주사 처방 표시 | 선택한 환자의 주사 처방 목록 및 상태(투약 대기중/준비 완료/불일치) |
| 웹캠 스캔 | USB 외부 카메라 자동 감지 후 라이브 스트림 |
| OCR 인식 | GCP Vision API (유료) — 약품 라벨 텍스트 인식 |
| 약품 검증 | 처방 약품명 vs OCR 텍스트 비교 (한글·영문 별명 매칭) |
| DB 업데이트 | 검증 결과를 Firebase에 저장 (`confirmed` / `mismatch`) |

### 2. 사이드바
- "약품 OCR" → **"처치실"** 로 변경

### 3. OCR 엔진
- EasyOCR (무료, 로컬) → **GCP Vision API (유료)** 로 교체
- `DOCUMENT_TEXT_DETECTION` 모드 (문서/라벨 특화)
- 서비스 계정 키로 직접 인증 (`GOOGLE_APPLICATION_CREDENTIALS` 환경변수 불사용)

### 4. Firebase DB 주사 데이터 시딩

환자 7명에 랜덤 주사 처방 배정:

| 환자 ID | 처방 |
|---|---|
| P-2026-0001 | 호르몬 주사 |
| P-2026-0002 | 호르몬 주사 + 스테로이드 주사 |
| P-2026-0003 | 스테로이드 주사 |
| P-2026-0004 | 스테로이드 주사 |
| P-2026-0005 | 스테로이드 주사 |
| P-2026-0006 | 호르몬 주사 + 스테로이드 주사 |
| P-2026-0007 | 호르몬 주사 |

약품 종류: **호르몬 주사 / 비타민 주사 / 스테로이드 주사**

---

## 파일 구조

```
MediCart/
└── web/
    ├── .gitignore                        ← 키 파일 제외 설정
    ├── README.md                         ← 설치/실행 방법 (키 파일 위치 포함)
    ├── backend/
    │   ├── app.py                        ← 주사 검증 API 추가
    │   │     GET  /api/patients/<pid>/injections
    │   │     POST /api/patients/<pid>/injections/<inj_id>/verify
    │   ├── fb_read.py                    ← get_injections(), update_injection_status() 추가
    │   ├── ocr.py                        ← GCP Vision API 엔진
    │   ├── .env                          ← ❌ git 제외 (직접 생성 필요)
    │   └── credentials/
    │       └── gcp_vision_key.json       ← ❌ git 제외 (슬랙으로 공유)
    └── frontend/
        ├── app/ocr/page.tsx              ← 처치실 페이지 (전면 개편)
        ├── components/Sidebar.tsx        ← "처치실" 메뉴
        ├── lib/api.ts                    ← Injection 타입, getInjections(), verifyInjection()
        └── .env.local                   ← ❌ git 제외 (직접 생성 필요)
```

---

## 키 파일 위치

### GCP Vision API 키 (슬랙으로 공유)
```bash
mkdir -p ~/MediCart/web/backend/credentials
cp ~/다운로드/gcp_vision_key.json ~/MediCart/web/backend/credentials/gcp_vision_key.json
```

### Firebase 키 (자동 탐색)
- `~/rokey_ws/db_test/medi-cart-*firebase*.json` 위치에 있으면 **자동 인식**
- 없으면 `.env`에 `FB_CRED=<경로>` 지정

---

## 실행 방법

### 백엔드 `.env` 생성 (최초 1회)

`web/backend/.env.example`을 복사해서 `.env` 생성:

```
FB_CRED=/home/<본인계정>/rokey_ws/db_test/medi-cart-ea39f-firebase-adminsdk-xxx.json
FB_DB_URL=https://medi-cart-ea39f-default-rtdb.asia-southeast1.firebasedatabase.app
INTEL_PASSWORD=rokey1234
INTEL_AUTH_TOKEN=<랜덤값: python3 -c "import secrets;print(secrets.token_urlsafe(32))">
```

### 프론트 `.env.local` 생성 (최초 1회)

`web/frontend/.env.local` 파일 직접 생성:

```
INTEL_AUTH_TOKEN=<backend .env의 INTEL_AUTH_TOKEN과 동일한 값>
```

### 실행

**터미널 1 — 백엔드**
```bash
cd ~/MediCart/web/backend
set -a && source .env && set +a
python3 app.py
```

**터미널 2 — 프론트**
```bash
cd ~/MediCart/web/frontend
npm run dev -- --port 3000
```

브라우저: `http://localhost:3000` → 비밀번호 `rokey1234` → 사이드바 **처치실**

---

## 약품 매칭 로직

처방 약품명과 OCR 텍스트를 비교할 때 한글·영문 별명 매칭 적용:

| 처방명 | 인식되어도 일치 처리되는 영문 키워드 |
|---|---|
| 호르몬 주사 | hormone, insulin, estrogen, testosterone |
| 비타민 주사 | vitamin, ascorbic, riboflavin, b12 |
| 스테로이드 주사 | steroid, dexamethasone, prednisolone |

OCR 줄바꿈 자동 정규화 (`호르몬\n주사` → `호르몬 주사` 처리)

---

## 투약 상태 흐름

```
투약 대기중 (pending)
    ↓ OCR 스캔 후 검증 버튼
  ┌─────────────────┐
  │ 일치             │→ 투약 준비 완료 (confirmed) ✅
  │ 불일치           │→ 약품 불일치 (mismatch)    ❌
  └─────────────────┘
```

Firebase 경로: `patients/{pid}/injections/{inj_id}/status`

---

## GitHub

- 저장소: `https://github.com/yevettee/MediCart`
- 브랜치: `jeon` (main 절대 건드리지 않음)
- 웹 경로: `https://github.com/yevettee/MediCart/tree/jeon/web`
