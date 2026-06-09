# 웹 회원 등급(RBAC) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** MediCart 웹을 단일 비밀번호 인증에서 3등급(환자/의료진/관리자) 역할 기반 접근제어로 확장한다.

**Architecture:** 역할은 위변조 불가한 **비밀 토큰 쿠키**로 판정한다. 순수 역할 로직을 백엔드 `auth.py`·프론트 `lib/auth.ts`에 분리(동일 표)하고, Flask `before_request`와 Next `middleware.ts`가 **이중으로** 라우트를 차단한다. 사이드바는 `/api/me` 역할로 메뉴를 필터하고 등급 배지를 표시한다. 비로그인 환자는 본인 직접입력 문진을 `intake_pending`에 적재한다.

**Tech Stack:** Flask(백엔드), Next.js 16(App Router, Edge middleware), pytest, Firebase RTDB.

**스펙:** `docs/superpowers/specs/2026-06-08-web-rbac-roles-design.md`
**브랜치:** `medicart2`

---

## File Structure

**백엔드 (`web/backend/`)**
- `auth.py` (신규) — 순수 역할 로직: 토큰↔역할, 비번↔역할, 경로↔최소등급, 등급 비교.
- `test/test_auth.py` (신규) — `auth.py` 단위테스트.
- `test/test_app_auth.py` (신규) — Flask test client로 login/me/before_request 검증.
- `app.py` (수정) — env(ADMIN), `before_request`·`/api/login`·`/api/me`·`/api/intake` 를 `auth.py`로 재배선.
- `fb_read.py` (수정) — `intake_pending_payload`(순수) + `add_intake_pending`(RTDB push).
- `test/test_fb_read.py` (수정) — `intake_pending_payload` 테스트 추가.
- `.env` / `.env.example` (수정) — `INTEL_ADMIN_PASSWORD`·`INTEL_ADMIN_TOKEN` 추가.

**프론트 (`web/frontend/`)**
- `lib/auth.ts` (신규) — 순수 역할 로직(백엔드 `auth.py`와 동일 표): `Role`·`ROLE_RANK`·`roleAtLeast`·`requiredRoleForRoute`·`landingFor`·`roleForToken`·`NAV_ROLES`.
- `lib/api.ts` (수정) — `getMe()`, `login()`→역할 반환, `submitIntake()`.
- `middleware.ts` (수정) — `lib/auth` 사용한 역할 기반 라우트 게이트.
- `components/Sidebar.tsx` (수정) — 역할 메뉴 필터 + 하단 등급 배지 + 로그인/로그아웃.
- `app/login/page.tsx` (수정) — 역할별 랜딩.
- `app/intake/page.tsx` (수정) — 역할 인지(환자 자기입력 / 의료진·관리자 환자선택).

**기동:** `~/.bashrc` `web()` 또는 수동 프론트 기동 시 `INTEL_ADMIN_TOKEN` 주입.

---

## Task 1: 백엔드 순수 역할 로직 `auth.py`

**Files:**
- Create: `web/backend/auth.py`
- Test: `web/backend/test/test_auth.py`

- [ ] **Step 1: 실패 테스트 작성**

`web/backend/test/test_auth.py`:
```python
import auth


def test_role_for_token():
    assert auth.role_for_token("ADM", "STF", "ADM") == "admin"
    assert auth.role_for_token("STF", "STF", "ADM") == "staff"
    assert auth.role_for_token("nope", "STF", "ADM") == "patient"
    assert auth.role_for_token(None, "STF", "ADM") == "patient"
    assert auth.role_for_token("", "STF", "ADM") == "patient"


def test_role_for_password():
    assert auth.role_for_password("apw", "spw", "apw") == "admin"
    assert auth.role_for_password("spw", "spw", "apw") == "staff"
    assert auth.role_for_password("x", "spw", "apw") is None
    assert auth.role_for_password(None, "spw", "apw") is None


def test_required_role_for_path():
    for p in ["/api/health", "/api/login", "/api/me", "/api/logout", "/api/intake"]:
        assert auth.required_role_for_path(p) == "patient"
    assert auth.required_role_for_path("/api/patients") == "staff"
    assert auth.required_role_for_path("/api/patients/P-2024-0001/visits") == "staff"
    assert auth.required_role_for_path("/api/ocr") == "staff"
    assert auth.required_role_for_path("/api/amrs") == "admin"
    assert auth.required_role_for_path("/api/stream") == "admin"
    assert auth.required_role_for_path("/login") == "patient"  # 非-api 는 게이트 안 함


def test_allowed_and_token_for_role():
    assert auth.allowed("admin", "staff") is True
    assert auth.allowed("staff", "staff") is True
    assert auth.allowed("staff", "admin") is False
    assert auth.allowed("patient", "patient") is True
    assert auth.allowed("patient", "staff") is False
    assert auth.token_for_role("admin", "STF", "ADM") == "ADM"
    assert auth.token_for_role("staff", "STF", "ADM") == "STF"
```

- [ ] **Step 2: 실패 확인**

Run: `cd web/backend && ./venv/bin/python -m pytest test/test_auth.py -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'auth'`)

- [ ] **Step 3: 구현**

`web/backend/auth.py`:
```python
"""auth — 순수 역할(RBAC) 로직. Flask 의존 없음(단위테스트 가능).

역할 서열: patient(0) < staff(1) < admin(2). 상위는 하위 권한 포함.
권한 판정은 위변조 불가한 비밀 토큰/비번 비교(상수시간)로만 한다.
"""
import hmac

ROLE_RANK = {"patient": 0, "staff": 1, "admin": 2}

# 비로그인(patient) 포함 전체 허용 경로
_OPEN = {"/api/health", "/api/login", "/api/me", "/api/logout", "/api/intake"}
# staff+ 접두사 (환자정보·처치실)
_STAFF_PREFIXES = ("/api/patients", "/api/ocr")


def _eq(a, b):
    return bool(b) and hmac.compare_digest(str(a or ""), str(b))


def role_for_token(token, staff_token, admin_token):
    """쿠키 토큰 → 역할. 어떤 토큰과도 안 맞으면 patient."""
    if _eq(token, admin_token):
        return "admin"
    if _eq(token, staff_token):
        return "staff"
    return "patient"


def role_for_password(password, staff_pw, admin_pw):
    """로그인 비번 → 역할. 둘 다 아니면 None(인증 실패)."""
    if _eq(password, admin_pw):
        return "admin"
    if _eq(password, staff_pw):
        return "staff"
    return None


def required_role_for_path(path):
    """요청 경로 → 최소 등급. /api/* 는 명시 외 전부 admin(fail-closed)."""
    if path in _OPEN:
        return "patient"
    if path.startswith(_STAFF_PREFIXES):
        return "staff"
    if path.startswith("/api/"):
        return "admin"
    return "patient"  # 비-API(정적 등)는 여기서 게이트하지 않음


def allowed(role, required):
    return ROLE_RANK.get(role, 0) >= ROLE_RANK.get(required, 99)


def token_for_role(role, staff_token, admin_token):
    return admin_token if role == "admin" else staff_token
```

- [ ] **Step 4: 통과 확인**

Run: `cd web/backend && ./venv/bin/python -m pytest test/test_auth.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: 커밋**

```bash
cd /home/rokey/MediCart
git add web/backend/auth.py web/backend/test/test_auth.py
git commit -m "feat(web): RBAC 순수 역할 로직 auth.py + 단위테스트"
```

---

## Task 2: 백엔드 env에 admin 비번·토큰 추가

**Files:**
- Modify: `web/backend/.env`
- Modify: `web/backend/.env.example` (있으면)

- [ ] **Step 1: admin 토큰 생성**

Run:
```bash
cd /home/rokey/MediCart/web/backend
./venv/bin/python -c "import secrets; print(secrets.token_urlsafe(32))"
```
출력값(예: `Xy3...`)을 다음 단계에 사용.

- [ ] **Step 2: `.env` 에 2줄 추가** (`INTEL_PASSWORD` 줄 아래)

`web/backend/.env` 의 `INTEL_AUTH_TOKEN=...` 줄 다음에:
```
INTEL_ADMIN_PASSWORD=rokey12345
INTEL_ADMIN_TOKEN=<Step1 에서 생성한 토큰>
```

- [ ] **Step 3: `.env.example` 동기화** (존재 시)

`web/backend/.env.example` 에 자리표시 추가:
```
INTEL_ADMIN_PASSWORD=changeme-admin
INTEL_ADMIN_TOKEN=generate-with-secrets-token_urlsafe-32
```
존재하지 않으면 이 단계 건너뜀.

- [ ] **Step 4: 커밋** (`.env` 는 gitignore — `.env.example` 만 커밋 대상)

```bash
cd /home/rokey/MediCart
git add web/backend/.env.example 2>/dev/null || true
git commit -m "chore(web): admin 비번·토큰 env 예시 추가" --allow-empty
```

---

## Task 3: 백엔드 app.py 인증 재배선 + Flask 통합 테스트

**Files:**
- Modify: `web/backend/app.py` (인증부 60~125)
- Test: `web/backend/test/test_app_auth.py`

- [ ] **Step 1: 실패 테스트 작성**

`web/backend/test/test_app_auth.py`:
```python
import os

os.environ.setdefault("INTEL_PASSWORD", "spw")
os.environ.setdefault("INTEL_AUTH_TOKEN", "STAFFTOK")
os.environ.setdefault("INTEL_ADMIN_PASSWORD", "apw")
os.environ.setdefault("INTEL_ADMIN_TOKEN", "ADMINTOK")

import app as flask_app  # noqa: E402

client = flask_app.app.test_client()


def test_login_staff_sets_cookie_and_role():
    r = client.post("/api/login", json={"password": "spw"})
    assert r.status_code == 200 and r.get_json()["role"] == "staff"
    assert "intel_auth=STAFFTOK" in r.headers.get("Set-Cookie", "")


def test_login_admin_role():
    r = client.post("/api/login", json={"password": "apw"})
    assert r.get_json()["role"] == "admin"
    assert "intel_auth=ADMINTOK" in r.headers.get("Set-Cookie", "")


def test_login_bad_password():
    assert client.post("/api/login", json={"password": "x"}).status_code == 401


def test_me_reports_role():
    client.set_cookie("intel_auth", "ADMINTOK")
    assert client.get("/api/me").get_json()["role"] == "admin"
    client.set_cookie("intel_auth", "")
    assert client.get("/api/me").get_json()["role"] == "patient"


def test_before_request_blocks_by_role():
    # patient(no cookie) → /api/patients(staff) 차단
    client.set_cookie("intel_auth", "")
    assert client.get("/api/patients").status_code == 401
    # staff → /api/amrs(admin) 차단
    client.set_cookie("intel_auth", "STAFFTOK")
    assert client.get("/api/amrs").status_code == 401
    # patient → /api/intake(open) 허용(404/200 중 무엇이든 401 아님)
    client.set_cookie("intel_auth", "")
    assert client.post("/api/intake", json={}).status_code != 401
```

- [ ] **Step 2: 실패 확인**

Run: `cd web/backend && ./venv/bin/python -m pytest test/test_app_auth.py -q`
Expected: FAIL (login 응답에 `role` 없음 / amrs 차단 안 됨 등)

- [ ] **Step 3: app.py 수정 — env + import**

`web/backend/app.py` 의 인증 블록을 교체. `_OPEN_PATHS = {...}` 줄과 그 위 토큰 정의를 다음으로:
```python
import auth   # 파일 상단 import 그룹에 추가

INTEL_PASSWORD = os.environ.get("INTEL_PASSWORD")
ADMIN_PASSWORD = os.environ.get("INTEL_ADMIN_PASSWORD")
AUTH_COOKIE    = "intel_auth"
AUTH_TOKEN     = os.environ.get("INTEL_AUTH_TOKEN")
ADMIN_TOKEN    = os.environ.get("INTEL_ADMIN_TOKEN")
COOKIE_SECURE  = os.environ.get("COOKIE_SECURE", "0") == "1"
if not INTEL_PASSWORD or not AUTH_TOKEN:
    sys.exit("INTEL_PASSWORD / INTEL_AUTH_TOKEN 환경변수를 설정하세요 (.env.example 참고)")
```
(기존 `_OPEN_PATHS` 정의 줄과 `_ct_eq` 는 유지. `_ct_eq` 는 다른 곳에서 쓰일 수 있으니 남겨둔다.)

- [ ] **Step 4: app.py 수정 — before_request**

`@app.before_request` 함수 본문을 교체:
```python
@app.before_request
def _require_auth():
    if request.method == "OPTIONS" or not request.path.startswith("/api/"):
        return None
    role = auth.role_for_token(request.cookies.get(AUTH_COOKIE), AUTH_TOKEN, ADMIN_TOKEN)
    if not auth.allowed(role, auth.required_role_for_path(request.path)):
        return jsonify({"error": "auth required"}), 401
    return None
```

- [ ] **Step 5: app.py 수정 — login / me**

`/api/login` 과 `/api/me` 핸들러를 교체:
```python
@app.post("/api/login")
def login():
    body = request.get_json(force=True, silent=True) or {}
    role = auth.role_for_password(body.get("password"), INTEL_PASSWORD, ADMIN_PASSWORD)
    if role is None:
        return jsonify({"ok": False, "error": "비밀번호가 올바르지 않습니다"}), 401
    resp = jsonify({"ok": True, "role": role})
    resp.set_cookie(AUTH_COOKIE, auth.token_for_role(role, AUTH_TOKEN, ADMIN_TOKEN),
                    max_age=60 * 60 * 12, httponly=True, samesite="Lax", secure=COOKIE_SECURE)
    return resp


@app.get("/api/me")
def me():
    role = auth.role_for_token(request.cookies.get(AUTH_COOKIE), AUTH_TOKEN, ADMIN_TOKEN)
    return jsonify({"authed": role != "patient", "role": role})
```
(`/api/logout` 핸들러는 변경 없음.)

- [ ] **Step 6: 통과 확인**

Run: `cd web/backend && ./venv/bin/python -m pytest test/test_app_auth.py test/test_auth.py -q`
Expected: PASS (모든 테스트 통과)

- [ ] **Step 7: 커밋**

```bash
cd /home/rokey/MediCart
git add web/backend/app.py web/backend/test/test_app_auth.py
git commit -m "feat(web): app.py 역할 기반 인증 재배선(login/me/before_request)"
```

---

## Task 4: 백엔드 `/api/intake` + `intake_pending` 적재

**Files:**
- Modify: `web/backend/fb_read.py` (순수 payload + writer)
- Modify: `web/backend/test/test_fb_read.py` (payload 테스트)
- Modify: `web/backend/app.py` (`/api/intake` 핸들러)

- [ ] **Step 1: 실패 테스트 작성** (`test/test_fb_read.py` 끝에 추가)

```python
def test_intake_pending_payload():
    import fb_read
    p = fb_read.intake_pending_payload(
        {"name": " 김환자 ", "room": "101", "sections": {"주호소(CC)": "두통"}}, 1700000000000)
    assert p["name"] == "김환자"          # 트림
    assert p["room"] == "101"
    assert p["sections"] == {"주호소(CC)": "두통"}
    assert p["status"] == "pending"
    assert p["ts"] == 1700000000000


def test_intake_pending_payload_defaults():
    import fb_read
    p = fb_read.intake_pending_payload({}, 1)
    assert p["name"] == "" and p["room"] == "" and p["sections"] == {}
    assert p["status"] == "pending"
```

- [ ] **Step 2: 실패 확인**

Run: `cd web/backend && ./venv/bin/python -m pytest test/test_fb_read.py -q -k intake_pending`
Expected: FAIL (`AttributeError: intake_pending_payload`)

- [ ] **Step 3: fb_read.py 구현** (`add_visit` 함수 위에 추가)

```python
def intake_pending_payload(data, ts):
    """비로그인 환자 자기제출 문진 → intake_pending 레코드(순수)."""
    data = data or {}
    sections = data.get("sections")
    return {
        "name": str(data.get("name") or "").strip(),
        "room": str(data.get("room") or "").strip(),
        "sections": sections if isinstance(sections, dict) else {},
        "status": "pending",
        "ts": ts,
    }


def add_intake_pending(data):
    """intake_pending 큐에 push. 기존 환자 레코드는 건드리지 않음."""
    payload = intake_pending_payload(data, int(time.time() * 1000))
    ref = _init().reference("intake_pending").push(payload)
    return ref.key, payload
```

- [ ] **Step 4: 통과 확인**

Run: `cd web/backend && ./venv/bin/python -m pytest test/test_fb_read.py -q -k intake_pending`
Expected: PASS (2 passed)

- [ ] **Step 5: app.py 에 `/api/intake` 추가** (`/api/me` 핸들러 아래)

```python
@app.post("/api/intake")
def intake_submit():
    body = request.get_json(force=True, silent=True) or {}
    if not str(body.get("name") or "").strip():
        return jsonify({"ok": False, "error": "성명을 입력하세요"}), 400
    key, payload = fb_read.add_intake_pending(body)
    return jsonify({"ok": True, "id": key, "intake": payload})
```

- [ ] **Step 6: import 확인 + 커밋**

Run: `cd web/backend && ./venv/bin/python -c "import app; print('import ok')"`
Expected: `import ok` (단, INTEL_ADMIN_* env 없으면 무관 — 위 import는 INTEL_PASSWORD/AUTH_TOKEN만 필수)
```bash
cd /home/rokey/MediCart
git add web/backend/fb_read.py web/backend/test/test_fb_read.py web/backend/app.py
git commit -m "feat(web): /api/intake — 비로그인 환자 문진 intake_pending 적재"
```

---

## Task 5: 프론트 순수 역할 로직 `lib/auth.ts`

**Files:**
- Create: `web/frontend/lib/auth.ts`

> 프론트 테스트러너가 없으므로 자동 단위테스트 대신, 백엔드 `auth.py`와 **동일한 표**를 유지한다(아래 매핑이 스펙/백엔드와 일치하는지 육안 검증).

- [ ] **Step 1: 구현**

`web/frontend/lib/auth.ts`:
```ts
// RBAC 순수 로직 — 백엔드 auth.py 와 동일 표(미들웨어·사이드바·로그인·문진 공용).
export type Role = "patient" | "staff" | "admin";

export const ROLE_RANK: Record<Role, number> = { patient: 0, staff: 1, admin: 2 };

export function roleAtLeast(role: Role, min: Role): boolean {
  return ROLE_RANK[role] >= ROLE_RANK[min];
}

// 라우트별 최소 등급 (백엔드 required_role_for_path 와 일치)
export function requiredRoleForRoute(path: string): Role {
  if (path === "/intake" || path.startsWith("/intake/")) return "patient";
  if (path.startsWith("/patients") || path.startsWith("/ocr")) return "staff";
  return "admin"; // "/", "/console", 그 외 보호 라우트
}

// 사이드바 메뉴 노출용(각 href 의 최소 등급)
export const NAV_ROLES: Record<string, Role> = {
  "/": "admin",
  "/console": "admin",
  "/patients": "staff",
  "/intake": "patient",
  "/ocr": "staff",
};

export function landingFor(role: Role): string {
  return role === "admin" ? "/" : role === "staff" ? "/patients" : "/intake";
}

// 쿠키 토큰 → 역할 (미들웨어용). 토큰은 호출측이 env에서 주입.
export function roleForToken(token: string | undefined, staffTok?: string, adminTok?: string): Role {
  if (adminTok && token === adminTok) return "admin";
  if (staffTok && token === staffTok) return "staff";
  return "patient";
}

export const ROLE_LABEL: Record<Role, string> = { patient: "환자", staff: "의료진", admin: "관리자" };
```

- [ ] **Step 2: 타입체크 + 커밋**

Run: `cd web/frontend && npx tsc --noEmit`
Expected: 오류 없음
```bash
cd /home/rokey/MediCart
git add web/frontend/lib/auth.ts
git commit -m "feat(web): 프론트 RBAC 순수 로직 lib/auth.ts"
```

---

## Task 6: 프론트 `lib/api.ts` — getMe / login(role) / submitIntake

**Files:**
- Modify: `web/frontend/lib/api.ts`

- [ ] **Step 1: `login` 교체 + `getMe`·`submitIntake` 추가**

`web/frontend/lib/api.ts` 의 기존 `export async function login(...)` 를 교체하고, `import type { Role }` 를 파일 상단에 추가:
```ts
import type { Role } from "@/lib/auth";

export async function login(password: string): Promise<Role | null> {
  const r = await fetch(`${API_BASE}/api/login`, {
    method: "POST", credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });
  if (!r.ok) return null;
  const d = await r.json().catch(() => ({}));
  return (d.role as Role) ?? null;
}

export async function getMe(): Promise<{ authed: boolean; role: Role }> {
  try {
    const r = await fetch(`${API_BASE}/api/me`, { cache: "no-store", credentials: "include" });
    if (!r.ok) return { authed: false, role: "patient" };
    return await r.json();
  } catch {
    return { authed: false, role: "patient" };
  }
}

export async function submitIntake(payload: { name: string; room?: string; sections: Record<string, unknown> }) {
  const r = await fetch(`${API_BASE}/api/intake`, {
    method: "POST", credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new Error(`POST /api/intake → ${r.status}`);
  return r.json();
}
```
(`logout()` 은 그대로 둠.)

- [ ] **Step 2: 타입체크 + 커밋**

Run: `cd web/frontend && npx tsc --noEmit`
Expected: 오류 없음 (login 반환형 변경 → 다음 Task에서 login page 수정 전까지 page에서 boolean 비교가 깨질 수 있으니, page 수정(Task 9)과 함께 빌드 검증한다. tsc는 통과해야 함)
```bash
cd /home/rokey/MediCart
git add web/frontend/lib/api.ts
git commit -m "feat(web): api getMe/login(role)/submitIntake"
```

---

## Task 7: 프론트 `middleware.ts` — 역할 기반 라우트 게이트

**Files:**
- Modify: `web/frontend/middleware.ts`

- [ ] **Step 1: 전체 교체**

`web/frontend/middleware.ts`:
```ts
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { roleForToken, requiredRoleForRoute, roleAtLeast, landingFor } from "@/lib/auth";

// systemd/기동 env 로 양쪽(Flask·Next)이 동일 토큰 공유. 미설정 시 admin 토큰을 모름 → fail-closed.
const STAFF = process.env.INTEL_AUTH_TOKEN;
const ADMIN = process.env.INTEL_ADMIN_TOKEN;

export function middleware(req: NextRequest) {
  const role = roleForToken(req.cookies.get("intel_auth")?.value, STAFF, ADMIN);
  const need = requiredRoleForRoute(req.nextUrl.pathname);
  if (roleAtLeast(role, need)) return NextResponse.next();

  const url = req.nextUrl.clone();
  if (role === "patient") {
    url.pathname = "/login";
    url.searchParams.set("next", req.nextUrl.pathname);
  } else {
    url.pathname = landingFor(role); // 의료진이 관리자 라우트 접근 → 자기 랜딩으로
    url.search = "";
  }
  return NextResponse.redirect(url);
}

// /login·정적파일 제외 전체 보호. /intake 는 미들웨어 내부 판정으로 patient 통과.
export const config = {
  matcher: ["/((?!login|_next/static|_next/image|favicon.ico|.*\\.).*)"],
};
```

- [ ] **Step 2: 타입체크 + 커밋**

Run: `cd web/frontend && npx tsc --noEmit`
Expected: 오류 없음
```bash
cd /home/rokey/MediCart
git add web/frontend/middleware.ts
git commit -m "feat(web): 미들웨어 역할 기반 라우트 차단"
```

---

## Task 8: 프론트 `Sidebar.tsx` — 메뉴 필터 + 등급 배지 + 로그인/로그아웃

**Files:**
- Modify: `web/frontend/components/Sidebar.tsx`

- [ ] **Step 1: import + 역할 상태 + NAV roles**

`Sidebar.tsx` 상단 import 에 추가:
```tsx
import { useEffect, useState } from "react";
import { getMe, logout } from "@/lib/api";
import { NAV_ROLES, roleAtLeast, ROLE_LABEL, landingFor, type Role } from "@/lib/auth";
```
`NAV` 배열의 각 항목에 `roles` 의미는 `NAV_ROLES[href]` 로 대체하므로 NAV 자체는 그대로 둔다.

- [ ] **Step 2: 컴포넌트 본문에 역할 fetch + 필터**

`export default function Sidebar({...}) {` 바로 다음, `const path = usePathname();` 아래에 추가:
```tsx
  const [role, setRole] = useState<Role>("patient");
  useEffect(() => { getMe().then((m) => setRole(m.role)).catch(() => setRole("patient")); }, [path]);
  const visibleNav = NAV.filter(({ href }) => roleAtLeast(role, NAV_ROLES[href] ?? "admin"));
```
그리고 네비 렌더의 `{NAV.map(...)}` 를 `{visibleNav.map(...)}` 로 변경.

- [ ] **Step 3: 하단 등급 배지 + 로그인/로그아웃 교체**

기존 하단 블록:
```tsx
      {!collapsed && (
        <div className="px-5 py-4 border-t border-line">
          <div className="flex items-center gap-2 text-[11.5px] text-ink-3">
            <span className="dot bg-green live-dot" />
            <span>PC3 웹 관제 · Redis 연결</span>
          </div>
        </div>
      )}
```
를 다음으로 교체:
```tsx
      <div className="px-3 py-3 border-t border-line">
        <div className={`flex items-center gap-2 ${collapsed ? "md:justify-center" : ""}`}>
          <span className={`w-2.5 h-2.5 rounded-full shrink-0 ${
            role === "admin" ? "bg-red" : role === "staff" ? "bg-teal" : "bg-ink-3"}`} />
          {!collapsed && (
            <div className="min-w-0 flex-1">
              <div className="text-[12.5px] font-bold text-ink leading-tight">{ROLE_LABEL[role]}</div>
              <div className="text-[10.5px] text-ink-3 truncate">
                {role === "patient" ? "비로그인" : "로그인됨"}
              </div>
            </div>
          )}
          {!collapsed && (
            role === "patient" ? (
              <a href={`/login?next=${encodeURIComponent(path)}`}
                className="text-[11.5px] font-semibold text-teal-600 bg-teal-soft border border-teal/30 rounded-lg px-2.5 py-1 hover:border-teal">로그인</a>
            ) : (
              <button onClick={async () => { await logout(); setRole("patient"); window.location.href = landingFor("patient"); }}
                className="text-[11.5px] font-semibold text-ink-2 bg-surface-2 border border-line rounded-lg px-2.5 py-1 hover:border-ink-3">로그아웃</button>
            )
          )}
        </div>
      </div>
```

- [ ] **Step 4: 타입체크 + 커밋**

Run: `cd web/frontend && npx tsc --noEmit`
Expected: 오류 없음
```bash
cd /home/rokey/MediCart
git add web/frontend/components/Sidebar.tsx
git commit -m "feat(web): 사이드바 역할 메뉴 필터 + 등급 배지 + 로그인/로그아웃"
```

---

## Task 9: 프론트 로그인 페이지 — 역할별 랜딩

**Files:**
- Modify: `web/frontend/app/login/page.tsx`

- [ ] **Step 1: import + submit 핸들러 교체**

상단 import:
```tsx
import { login } from "@/lib/api";
import { requiredRoleForRoute, roleAtLeast, landingFor } from "@/lib/auth";
```
`submit` 함수 본문을 교체:
```tsx
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr(false);
    const role = await login(pw).catch(() => null);
    setBusy(false);
    if (role) {
      const next = params.get("next") || "";
      const safe = next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/\\");
      const dest = safe && roleAtLeast(role, requiredRoleForRoute(next)) ? next : landingFor(role);
      router.replace(dest);
    } else { setErr(true); setPw(""); }
  }
```

- [ ] **Step 2: 타입체크 + 커밋**

Run: `cd web/frontend && npx tsc --noEmit`
Expected: 오류 없음
```bash
cd /home/rokey/MediCart
git add web/frontend/app/login/page.tsx
git commit -m "feat(web): 로그인 성공 시 역할별 랜딩"
```

---

## Task 10: 프론트 문진 페이지 — 역할 인지(환자 자기입력)

**Files:**
- Modify: `web/frontend/app/intake/page.tsx`

> 핵심: 환자(patient)는 `getPatients()`(staff 권한) 호출 금지. 본인 정보 직접입력 + 동일 SECTIONS → `submitIntake`. 의료진/관리자는 기존 동작 유지.

- [ ] **Step 1: import + 역할 상태 추가**

상단 import 에 추가:
```tsx
import { getPatients, Patient, addVisit, getMe, submitIntake } from "@/lib/api";
import type { Role } from "@/lib/auth";
```
`export default function IntakePage() {` 본문 상태 선언부에 추가:
```tsx
  const [role, setRole] = useState<Role>("patient");
  const [selfName, setSelfName] = useState("");
  const [selfRoom, setSelfRoom] = useState("");
```

- [ ] **Step 2: 환자목록 fetch 를 역할 가드**

기존:
```tsx
  useEffect(() => {
    getPatients().then((ps) => { setPatients(ps); if (ps[0]) setPid(ps[0].id); }).catch(() => {});
  }, []);
```
를 교체:
```tsx
  useEffect(() => {
    getMe().then((m) => {
      setRole(m.role);
      if (m.role !== "patient") {
        getPatients().then((ps) => { setPatients(ps); if (ps[0]) setPid(ps[0].id); }).catch(() => {});
      }
    }).catch(() => setRole("patient"));
  }, []);
```

- [ ] **Step 3: 저장 핸들러를 역할 분기**

기존 저장 핸들러(`async function save()` 또는 onClick 저장 로직 — `addVisit(pid, ...)` 호출부)를 찾아, 그 시작에 환자 분기를 추가. 저장 함수 본문 맨 앞:
```tsx
    if (role === "patient") {
      if (!selfName.trim()) { setSaved("err"); return; }
      setBusy(true);
      try {
        await submitIntake({ name: selfName, room: selfRoom, sections: form });
        setSaved("ok");
      } catch { setSaved("err"); }
      finally { setBusy(false); }
      return;
    }
    // ↓ 기존 의료진/관리자 로직(addVisit) 그대로
```

- [ ] **Step 4: 대상 선택 UI 를 역할 분기**

기존 "대상 환자 선택"(환자 드롭다운, `patients.map` / `setPid`) 블록을 다음으로 감싼다:
```tsx
  {role === "patient" ? (
    <div className="card p-4 grid sm:grid-cols-2 gap-3">
      <label className="block">
        <span className="text-[12px] font-semibold text-ink-3">성명 *</span>
        <input value={selfName} onChange={(e) => setSelfName(e.target.value)} className="field" placeholder="본인 성명" />
      </label>
      <label className="block">
        <span className="text-[12px] font-semibold text-ink-3">병실</span>
        <input value={selfRoom} onChange={(e) => setSelfRoom(e.target.value)} className="field" placeholder="예: 101" />
      </label>
    </div>
  ) : (
    /* 기존 환자 선택 드롭다운 블록 그대로 */
  )}
```
(SECTIONS 폼 본문·저장 버튼은 공유 — 변경 없음.)

- [ ] **Step 5: 빌드 검증 + 커밋**

Run: `cd web/frontend && npx tsc --noEmit && npm run build 2>&1 | tail -5`
Expected: 타입 통과, 빌드 성공(Route 목록에 `/intake` 포함)
```bash
cd /home/rokey/MediCart
git add web/frontend/app/intake/page.tsx
git commit -m "feat(web): 문진 페이지 역할 인지(환자 자기입력 → intake_pending)"
```

---

## Task 11: 기동 배선 + 3등급 E2E 검증 (사용자 실행)

**Files:**
- Modify: `~/.bashrc` `web()` 함수 (프론트에 `INTEL_ADMIN_TOKEN` 주입)

> 서버 직접 기동은 사용자가 실행. 아래 명령·순서 제공.

- [ ] **Step 1: 프론트 기동에 `INTEL_ADMIN_TOKEN` 주입**

`~/.bashrc` 의 `web()` 함수에서 프론트 기동 부분에 `INTEL_AUTH_TOKEN` 과 함께 `INTEL_ADMIN_TOKEN` 도 export 하도록 추가. 수동 기동 시:
```bash
cd ~/MediCart/web/frontend
export INTEL_AUTH_TOKEN="$(grep -E '^INTEL_AUTH_TOKEN=' ~/MediCart/web/backend/.env | cut -d= -f2-)"
export INTEL_ADMIN_TOKEN="$(grep -E '^INTEL_ADMIN_TOKEN=' ~/MediCart/web/backend/.env | cut -d= -f2-)"
export PORT=3000
```

- [ ] **Step 2: 빌드 + 백엔드/프론트 재기동 (사용자)**

```bash
# 백엔드
cd ~/MediCart/web/backend && set -a && source ./.env && set +a
pkill -9 -f backend/app.py; sleep 2
setsid nohup ./venv/bin/python app.py > /tmp/web_backend.log 2>&1 < /dev/null &
# 프론트
cd ~/MediCart/web/frontend && npm run build
export INTEL_AUTH_TOKEN="$(grep -E '^INTEL_AUTH_TOKEN=' ~/MediCart/web/backend/.env | cut -d= -f2-)"
export INTEL_ADMIN_TOKEN="$(grep -E '^INTEL_ADMIN_TOKEN=' ~/MediCart/web/backend/.env | cut -d= -f2-)"
export PORT=3000
pkill -9 -f next-server; sleep 2
setsid nohup npm run start > /tmp/web_frontend.log 2>&1 < /dev/null &
```

- [ ] **Step 3: E2E 시나리오 검증 (https://intel.thatshoon.com)**

1. **환자(비로그인)**: 사이드바=문진표만, 하단 "환자" 배지. `/patients` 직접 입력 → `/login` 으로. 문진표에서 성명·병실 입력 후 제출 성공(환자 목록 안 보임). RTDB `intake_pending` 에 적재 확인.
2. **의료진(rokey1234)**: 로그인 → `/patients` 랜딩. 사이드바=문진표·환자정보·처치실. 하단 "의료진"(틸). `/console` 직접 입력 → `/patients` 로 리다이렉트. 처치실 OCR 동작.
3. **관리자(rokey12345)**: 로그인 → `/` 랜딩. 사이드바=전체(홈·콘솔 포함). 하단 "관리자"(빨강). 콘솔 정상.
4. **로그아웃** → "환자"로 복귀, 메뉴=문진표만.

- [ ] **Step 4: 백엔드 단위테스트 전체 통과 확인**

Run: `cd ~/MediCart/web/backend && ./venv/bin/python -m pytest test/ -q`
Expected: 전체 PASS (auth·app_auth·fb_read·ocr·patients)

- [ ] **Step 5: 최종 커밋(있으면)**

```bash
cd /home/rokey/MediCart
git add -A web/ docs/
git commit -m "chore(web): RBAC 기동 배선 + E2E 검증" --allow-empty
```

---

## 비범위(YAGNI)
- `intake_pending` 검토·승인 워크플로우(후속).
- 환자 본인 신원 검증(이름/번호 조회).
- 다중 사용자 계정/DB 인증.
