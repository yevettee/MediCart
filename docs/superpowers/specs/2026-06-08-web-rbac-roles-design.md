# MediCart Web — 회원 등급(RBAC) 설계

**작성일:** 2026-06-08
**대상:** `web/` (Next.js 프론트 + Flask 백엔드)
**목표:** 단일 비밀번호 인증을 **3등급(환자/의료진/관리자) 역할 기반 접근제어**로 확장하고,
사이드바에 등급 표시 + 등급별 메뉴 노출 + 서버측 라우트 차단을 구현한다.

---

## 1. 역할 모델

| 역할 | 한글 | 조건 | 배지색 |
| --- | --- | --- | --- |
| `patient` | 환자 | 비로그인(쿠키 없음/무효) | 회색 |
| `staff` | 의료진 | `rokey1234` 로그인 | 틸(teal) |
| `admin` | 관리자 | `rokey12345` 로그인 | 빨강(강조) |

등급 서열(rank): `patient=0 < staff=1 < admin=2`. 상위 등급은 하위 등급 권한을 포함한다.

### 등급별 메뉴 / 라우트

| 메뉴 | 라우트 | patient | staff | admin |
| --- | --- | :-: | :-: | :-: |
| 문진표 | `/intake` | ✅ | ✅ | ✅ |
| 환자 정보 | `/patients`, `/patients/[id]` | ✕ | ✅ | ✅ |
| 처치실 | `/ocr` | ✕ | ✅ | ✅ |
| 홈 | `/` | ✕ | ✕ | ✅ |
| 관리자 콘솔 | `/console` | ✕ | ✕ | ✅ |

### 로그인 후 랜딩(기본 진입)
- patient → `/intake` · staff → `/patients` · admin → `/`

---

## 2. 인증 메커니즘 (위변조 불가)

평문 `role` 쿠키는 위조 가능하므로 권한 판정에 쓰지 않는다. **역할별 비밀 토큰**을 쓴다.

### 환경변수 (`web/backend/.env`, 커밋 금지)
```
INTEL_PASSWORD=rokey1234            # staff 비번 (기존)
INTEL_ADMIN_PASSWORD=rokey12345     # admin 비번 (신규)
INTEL_AUTH_TOKEN=<기존 staff 토큰>   # staff 쿠키값 (기존)
INTEL_ADMIN_TOKEN=<신규 admin 토큰>  # admin 쿠키값 (신규, 랜덤 생성)
```
신규 토큰 생성: `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`.
프론트 미들웨어도 두 토큰이 필요하므로 **프론트 프로세스에 `INTEL_AUTH_TOKEN`·`INTEL_ADMIN_TOKEN` 둘 다 주입**(기동 스크립트/`web()` 함수 수정).

### 쿠키
- 쿠키명 `intel_auth` (기존 유지). 값 = staff 토큰 **또는** admin 토큰.
- 역할 판정(상수시간 비교):
  ```
  role_for_token(tok):
    if ct_eq(tok, INTEL_ADMIN_TOKEN): return "admin"
    if ct_eq(tok, INTEL_AUTH_TOKEN):  return "staff"
    return "patient"
  ```

### 백엔드 엔드포인트 변경 (`app.py`)
- `POST /api/login` — body `{password}`. admin 비번 먼저 검사 → admin 토큰 쿠키, 아니면 staff 비번 → staff 토큰 쿠키, 둘 다 아니면 401. 응답 `{ok:true, role}`.
- `GET /api/me` — `{authed: bool, role}` (사이드바·페이지 역할 판정용, **open**).
- `POST /api/logout` — 쿠키 삭제. 응답 `{ok:true}`. (open)
- `POST /api/intake` — **신규, open**. 비로그인 환자 자기제출(§4).

---

## 3. 서버측 강제 (이중 차단)

### 3-1. 백엔드 `before_request` (app.py)
경로별 **최소 등급**을 판정한다. fail-closed: 명시되지 않은 `/api/*` 는 admin 요구.

```
OPEN     = {/api/health, /api/login, /api/me, /api/logout, /api/intake}   # patient 포함 전체
STAFF_PREFIXES = (/api/patients, /api/ocr)                                # staff+ (환자정보·처치실)
# 그 외 /api/* (amrs, stream, alerts, missions, targets, map.png, rooms, mode, goto 등) = admin
```
판정: `role = role_for_token(cookie)`; 경로의 required 등급 산출 → `rank(role) < rank(required)` 이면 **401**.
- OPTIONS·정적은 통과(기존 로직 유지).

### 3-2. 프론트 `middleware.ts`
쿠키 토큰 → 역할 매핑 후 라우트 allowlist. 미들웨어 env: `INTEL_AUTH_TOKEN`, `INTEL_ADMIN_TOKEN`.

```
ROUTE_MIN(path):
  /login                         → (모두, 미들웨어 제외)
  /intake                        → patient
  /patients, /ocr                → staff
  /, /console                    → admin
  그 외(보호대상)                 → admin   (fail-closed)
판정:
  role = roleOf(cookie)
  required = ROUTE_MIN(path)
  rank(role) >= rank(required) → next()
  else if role == patient       → /login?next=<path>
  else (staff가 admin route)     → role 랜딩(staff→/patients)로 redirect
```
- matcher: 기존과 동일(로그인·정적 제외 전체). 단 **patient(쿠키 없음)도 `/intake` 는 통과**하도록 위 판정으로 변경(기존엔 무조건 /login 이었음).

---

## 4. 비로그인 환자 문진 플로우 (목록 비노출)

`/intake` 페이지를 **역할 인지**로 분기한다(`getMe()` 로 역할 취득).

- **patient**: 환자 목록 선택 UI **숨김**. 대신 **본인 정보 직접 입력**(이름, 병실, 연락처 등 최소 필드) + 문진 11섹션 작성 → `POST /api/intake`.
  - 백엔드 `POST /api/intake` → `fb_read.add_intake_pending(payload)` 가 RTDB `intake_pending/<pushId>` 에 적재(`{name, room, sections, ts, status:"pending"}`). 기존 환자 레코드를 건드리지 않음(프라이버시).
- **staff / admin**: 기존 동작 유지 — `getPatients()` 목록에서 선택 → `addVisit()` 로 외래기록 추가.

> staff/admin 의 `intake_pending` 검토·환자 매칭 UI는 **이번 범위 밖**(적재까지만). 후속 작업.

---

## 5. 프론트 컴포넌트 변경

- **`lib/api.ts`**: `getMe(): {authed, role}`, `logout()`, `submitIntake(payload)`; `Role` 타입.
- **`lib/auth.ts`** (신규, 순수): `ROLE_RANK`, `roleAtLeast(role, min)`, 메뉴 `roles` 매핑 — 미들웨어·사이드바·intake 공용(단위테스트 대상).
- **`components/Sidebar.tsx`**: 마운트 시 `getMe()` → 역할. NAV 를 `item.roles.includes(role)` 로 필터. **하단 등급 배지**(환자/의료진/관리자 + 색) + **로그인/로그아웃 버튼**.
- **`app/intake/page.tsx`**: 역할 분기(patient 자기입력 폼 / staff·admin 환자선택 폼).
- **`app/login/page.tsx`**: 성공 응답의 `role` 로 랜딩(next 우선, 없으면 역할 기본 랜딩).
- **`middleware.ts`**: §3-2.

---

## 6. 테스트

### 순수 단위테스트 (구현 대상)
- 백엔드 `test_auth.py`: `role_for_token` (admin/staff/unknown→patient), `required_role_for_path` (각 경로→등급), login 비번→역할.
- 프론트 `lib/auth.ts`: `roleAtLeast`, 메뉴 필터 (가능하면; 프론트 테스트러너 없으면 로직을 순수함수로 분리해 백엔드와 동일 표를 문서로 보증).

### 통합(사용자 실행, 서버 직접기동 금지 → 명령 제공)
- patient(비로그인): 사이드바=문진표만 / `/patients` 직접URL → /login / 문진 제출 성공(목록 안 보임).
- staff(rokey1234): 문진표·환자정보·처치실 노출 / `/console` 직접URL → /patients 리다이렉트 / OCR 동작.
- admin(rokey12345): 전체 노출 / 콘솔 정상.
- 등급 배지 3종 표시·로그아웃 시 patient 복귀.

---

## 7. 영향도 / 호환성

- 기존 staff 토큰·쿠키·비번 그대로 동작(추가만). admin 비번·토큰만 신규.
- `/api/intake` 신규 open 엔드포인트 — 기존 인증 라우트 영향 없음.
- 프론트 기동 시 `INTEL_ADMIN_TOKEN` 주입 누락 시: 미들웨어가 admin 토큰을 모름 → admin이 staff로 강등(콘솔 차단). 기동 스크립트에 반드시 추가.
- 미들웨어 fail-closed 유지: 토큰 미설정 시 보호 라우트 전면 차단(현 동작과 동일 안전성).

---

## 8. 비범위(YAGNI)
- 환자 본인 신원 검증(이름/번호 조회) — 안 함(자기제출만).
- `intake_pending` 검토·승인 워크플로우 — 후속.
- 다중 사용자 계정/DB 인증 — 안 함(비번 2개 고정).
