# web — 병동 보조 로봇 대시보드 (MediCart · jeon 브랜치)

Flask(백엔드 :5000) + Next.js(프론트 :3000). Firebase RTDB를 **서버측(firebase-admin)** 에서 읽어
SSE/REST로 프론트에 제공. 프론트(브라우저)는 Flask만 호출하고 RTDB를 직접 만지지 않는다.

**jeon 브랜치 추가 기능 — 처치실 (약품 OCR 검증)**
- GCP Vision API로 약품 라벨 텍스트 인식 (호르몬·비타민·스테로이드 주사)
- 환자별 처방 주사 확인 → OCR 스캔 → 약품 적합성 검증 → Firebase DB 상태 업데이트
- 사이드바 "처치실" 메뉴 (`/ocr`)

```
backend/   Flask : fb_read(RTDB 경계)·patients·ocr(GCP Vision)·app(SSE/REST/auth/OCR검증)
frontend/  Next  : app/{map,control,patients,intake,ocr(처치실),debug}, lib/api
deploy/    systemd 서비스 + setup-tunnel.sh(호스팅)
docs/      architecture·setup·deploy(DEPLOY.md)
legacy/    구 Redis/xlsx 구현(미사용·참고)
```

---

## 0. 키 파일 준비 (최초 1회, git에 절대 올리지 않음)

### 필요한 키 파일 2개

| 파일 | 용도 | 받는 방법 |
|---|---|---|
| Firebase 서비스 계정 키 | RTDB 읽기/쓰기 | 각자 Firebase 콘솔에서 발급 또는 기존 파일 사용 |
| GCP Vision API 키 | 약품 OCR (유료) | 슬랙으로 공유받은 `gcp_vision_key.json` 사용 |

### Firebase 키 — 자동 탐색 (별도 설정 불필요)

백엔드가 아래 순서로 자동 탐색합니다:
1. 환경변수 `FB_CRED`에 지정된 경로
2. `~/rokey_ws/db_test/medi-cart-*firebase*.json` (팀 표준 위치)

👉 **`~/rokey_ws/db_test/` 에 Firebase 키가 있으면 추가 설정 불필요**

사용자 이름이 `rokey`가 아닌 경우 `.env`에 경로를 직접 지정하세요:
```
FB_CRED=/home/<본인계정>/rokey_ws/db_test/medi-cart-ea39f-firebase-adminsdk-xxx.json
```

### GCP Vision API 키 — 수동 배치

슬랙에서 `gcp_vision_key.json` 파일을 받은 뒤 아래 순서대로 진행하세요.

**① 폴더 만들기**
```bash
mkdir -p ~/MediCart/web/backend/credentials
```

**② 파일 복사 (다운로드 폴더 기준)**
```bash
cp ~/다운로드/gcp_vision_key.json ~/MediCart/web/backend/credentials/gcp_vision_key.json
```

완료 후 확인:
```bash
ls ~/MediCart/web/backend/credentials/
# gcp_vision_key.json 이 보이면 정상
```

> ✅ 이 파일은 `.gitignore`에 등록되어 있어 **git에 올라가지 않습니다. 절대 커밋하지 마세요.**

> ⚠️ 사용자 이름이 `rokey`인 경우 경로가 `/home/rokey/MediCart/...` 입니다. `~` 는 본인 홈 폴더로 자동 변환됩니다.

---

## 1. 사전 준비 (최초 1회)

```bash
# (1) 백엔드 의존 설치
cd MediCart/web/backend
pip install -r requirements.txt      # flask·firebase-admin·google-cloud-vision 등

# (2) 프론트 의존 설치
cd MediCart/web/frontend
npm install

# (3) 백엔드 .env 작성 (git 제외됨)
cd MediCart/web/backend
cp .env.example .env
# 아래 항목 수정:
#   FB_CRED=           ← Firebase 키 경로 (자동탐색이면 생략 가능)
#   FB_DB_URL=https://medi-cart-ea39f-default-rtdb.asia-southeast1.firebasedatabase.app
#   INTEL_PASSWORD=rokey1234
#   INTEL_AUTH_TOKEN=  ← python3 -c "import secrets;print(secrets.token_urlsafe(32))"
#   GCP_VISION_KEY_PATH=  ← gcp_vision_key.json 경로 (기본값 사용 시 생략 가능)

# (4) 프론트 .env.local 작성 (git 제외됨)
cd MediCart/web/frontend
# 아래 내용으로 .env.local 파일 직접 생성:
#   INTEL_AUTH_TOKEN=<backend .env의 INTEL_AUTH_TOKEN과 동일한 값>
```

> ⚠️ `INTEL_AUTH_TOKEN`은 백엔드 `.env`와 프론트 `.env.local` 에 **동일한 값**이어야 합니다.
> 다르면 로그인해도 모든 페이지가 `/login`으로 튕깁니다.

---

## 2. 로컬 개발 실행

### 백엔드 (터미널 1)
```bash
cd MediCart/web/backend
set -a && source .env && set +a
python3 app.py
# → http://localhost:5000
```

### 프론트 (터미널 2)
```bash
cd MediCart/web/frontend
npm run dev -- --port 3000
# → http://localhost:3000
```

> ⚠️ `npm run dev` 만 쓰면 백엔드 `.env`의 `PORT=5000`을 상속해 포트 충돌이 납니다.
> 반드시 `-- --port 3000` 을 붙이세요.

브라우저에서 `http://localhost:3000` 접속 → 비밀번호 입력 → 로그인

---

## 3. 처치실 (약품 OCR 검증) 사용법

1. 사이드바 **처치실** 클릭
2. **환자 선택** — 드롭다운에서 투약 대상 환자 선택
3. **주사 처방 선택** — 해당 환자의 처방 목록 확인 (투약 대기중 상태)
4. **웹캠 켜기** → 약품 라벨에 카메라 조준
5. **스캔 & OCR** — GCP Vision API가 텍스트 인식
6. **약품 적합성 검증 & DB 저장** — 처방과 OCR 결과 비교
   - ✅ 일치 → "투약 준비 완료" (Firebase DB 상태 `confirmed` 업데이트)
   - ❌ 불일치 → "약품 불일치 — 재확인 필요" (상태 `mismatch`)

---

## 4. 흔한 함정

| 증상 | 원인 | 해결 |
|---|---|---|
| 로그인해도 `/login`으로 튕김 | 프론트 `.env.local`에 `INTEL_AUTH_TOKEN` 없거나 백엔드와 값 불일치 | 두 파일의 토큰값 일치 확인 |
| 프론트가 `:5000`으로 `EADDRINUSE` | 백엔드 `.env`의 `PORT=5000` 상속 | `npm run dev -- --port 3000` 으로 실행 |
| OCR 오류 "키 파일을 찾을 수 없음" | `gcp_vision_key.json` 미배치 | `web/backend/credentials/` 에 파일 배치 |
| OCR 오류 "UNAUTHENTICATED" | Firebase 키가 `GOOGLE_APPLICATION_CREDENTIALS`에 등록된 상태 | `unset GOOGLE_APPLICATION_CREDENTIALS` 후 재시작 |
| 약품 인식 후 불일치 처리 | OCR이 줄바꿈으로 단어 분리 (예: `호르몬\n주사`) | 자동 정규화됨 — Flask 재시작 후 재시도 |
| Firebase DB 주사 목록 없음 | 환자 데이터에 injections 노드 없음 | 팀 DB 관리자에게 시딩 요청 |

---

## 5. 빠른 점검
```bash
# 로그인 + API 동작 확인
curl -s -c /tmp/c -X POST localhost:5000/api/login \
  -H 'Content-Type: application/json' -d '{"password":"rokey1234"}'
curl -s -b /tmp/c localhost:5000/api/health            # {"ok":true}
curl -s -b /tmp/c localhost:5000/api/patients          # 환자 목록
curl -s -b /tmp/c localhost:5000/api/patients/P-2026-0001/injections  # 주사 처방
```

페이지: `/`(홈) · `/map`(실시간 관제) · `/control`(로봇 제어) · `/patients`(환자) · `/intake`(문진) · `/ocr`(처치실) · `/debug`
