# 시나리오 테스트 구현 — Web 레이어 (Plan 1/3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 테스트케이스 카탈로그(`docs/superpowers/specs/2026-06-10-scenario-test-case-catalog-design.md`)의 **Web 레이어 케이스**(backend pytest + frontend vitest)를 자동화 테스트로 구현한다.

**Architecture:** 두 기존 하니스를 확장한다 — (1) backend `web/backend/test/`(pytest): 공유 `conftest.py`(env 토큰 + `fb_read` monkeypatch용 인메모리 RTDB) 위에 Flask `test_client` 라우트 통합 테스트를 추가. (2) frontend `web/frontend/`(vitest): 순수 로직은 기존 `lib/*.test.ts` 확장, 컴포넌트는 jsdom + @testing-library/react 하니스를 신설해 RBAC 메뉴·오버레이·맵·문진 폼을 검증. ROS 레이어(perception/control/mission)는 Plan 2·3에서 다룬다.

**Tech Stack:** pytest + Flask test_client (Python, `web/backend/venv`) · vitest + jsdom + @testing-library/react + @testing-library/jest-dom (TypeScript, Next.js 16).

**범위(이 플랜):** 카탈로그 중 Tooling이 `pytest` / `pytest(mock)`(순수 로직) / `api+rtdb` / `vitest`인 케이스. **제외**(Plan 2·3): `launch_testing(sim)`·ROS `pytest(mock)` perception/control/mission, `[+manual:runtime]`.

**대상:** `/home/rokey/MediCart`, `integration` 브랜치. 테스트 실행만 — 프로덕션 코드는 버그 발견 시에만 별도 보고(이 플랜은 코드 수정 비범위, 테스트가 기존 동작을 검증).

> **실행 환경 주의(중요):** backend 테스트는 **clean env + venv 파이썬**으로 실행해야 한다(실제 `.env`를 source하면 토큰이 덮여 401). 표준 실행 커맨드:
> `cd /home/rokey/MediCart/web/backend && env -i PATH="/usr/bin:/bin" PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 venv/bin/python -m pytest test/ -q`
> frontend: `cd /home/rokey/MediCart/web/frontend && npx vitest run`

> **Next.js 주의:** 컴포넌트 테스트는 "use client" 컴포넌트 대상. 새 Next API 도입 금지 — 기존 패턴만. 불확실하면 `node_modules/next/dist/docs/` 확인.

---

## File Structure

**Backend (`web/backend/test/`)**
- Create `conftest.py` — 공유 픽스처: env 토큰 setdefault, Flask `app.test_client()`, `fake_rtdb`(인메모리 dict로 `fb_read`의 RTDB 접근 monkeypatch), 인증 쿠키 헬퍼.
- Create `test_app_routes.py` — API+RTDB 라우트 통합 테스트 (nurse_cart/patrol/intake/targets/map/amrs/stream + ns 라우팅 + mission_pool).
- Modify `test_fb_read.py` — 카탈로그 갭만 보강(X-RTDB-08 ns 음수 케이스, B-QR-05 lookup 등 — 대부분 기존 충족).
- (참고) 기존 `test_auth.py`·`test_app_auth.py`·`test_patients.py` 재사용.

**Frontend (`web/frontend/`)**
- Modify `package.json` — devDeps: `jsdom`, `@testing-library/react`, `@testing-library/jest-dom`, `@testing-library/user-event`.
- Create `vitest.config.ts` — jsdom 환경 + setup 파일(현재 무설정 = node 환경).
- Create `test/setup.ts` — jest-dom matchers 등록 + 공통 mock(`@/lib/api` 부분 mock 헬퍼).
- Create `components/Sidebar.test.tsx`, `components/RoundOverlay.test.tsx`, `components/RoundsIntakeOverlay.test.tsx`, `components/MapView.test.tsx`, `components/IntakeForm.test.tsx` — 컴포넌트 케이스.
- Modify `lib/auth.test.ts`, `lib/telemetry.test.ts`, `lib/ocrQr.test.ts` — 순수 로직 갭만 보강(대부분 기존 충족).

> **케이스 본문 출처:** 각 케이스의 정확한 Given/When/Then·기대값은 **카탈로그 스펙**(`…scenario-test-case-catalog-design.md`)에 케이스 ID별로 있다. 본 플랜은 하니스·패턴(완성 코드)·배치·실행/검증을 제공하고, 묶음 태스크의 개별 케이스는 카탈로그 ID로 참조한다.

---

## Task 1: 백엔드 공유 하니스 (conftest)

**Files:**
- Create: `web/backend/test/conftest.py`

- [ ] **Step 1: conftest 작성**

`web/backend/test/conftest.py`:
```python
"""공유 pytest 픽스처 — Flask test_client + 인메모리 RTDB monkeypatch.

실행: cd web/backend && env -i PATH=/usr/bin:/bin PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
      venv/bin/python -m pytest test/ -q
"""
import os

# app/auth import 전에 토큰 고정(실제 .env source 금지 — clean env 가정)
os.environ.setdefault("INTEL_PASSWORD", "spw")
os.environ.setdefault("INTEL_AUTH_TOKEN", "STAFFTOK")
os.environ.setdefault("INTEL_ADMIN_PASSWORD", "apw")
os.environ.setdefault("INTEL_ADMIN_TOKEN", "ADMINTOK")

import pytest
import fb_read
import app as flask_app


class FakeRTDB:
    """fb_read 의 RTDB 접근을 대체하는 인메모리 트리."""
    def __init__(self):
        self.data = {}

    def get(self, path):
        node = self.data
        for k in [p for p in path.strip("/").split("/") if p]:
            if not isinstance(node, dict) or k not in node:
                return None
            node = node[k]
        return node

    def set(self, path, value):
        parts = [p for p in path.strip("/").split("/") if p]
        node = self.data
        for k in parts[:-1]:
            node = node.setdefault(k, {})
        if parts:
            node[parts[-1]] = value


@pytest.fixture
def client():
    return flask_app.app.test_client()


@pytest.fixture
def staff(client):
    client.set_cookie("intel_auth", "STAFFTOK")
    return client


@pytest.fixture
def admin(client):
    client.set_cookie("intel_auth", "ADMINTOK")
    return client


@pytest.fixture
def fake_rtdb(monkeypatch):
    """fb_read 의 RTDB read/write 진입점을 인메모리로 교체.
    실제 진입점 이름은 fb_read 구현에 맞춰 조정(아래 Task 2 Step 1에서 확인)."""
    rtdb = FakeRTDB()
    # 예: fb_read 가 _ref(path).get()/set() 패턴이면 그 래퍼를 monkeypatch.
    monkeypatch.setattr(fb_read, "_rtdb_get", rtdb.get, raising=False)
    monkeypatch.setattr(fb_read, "_rtdb_set", rtdb.set, raising=False)
    return rtdb
```

- [ ] **Step 2: 실제 RTDB 진입점 확인 후 monkeypatch 타겟 정정**

Run: `cd /home/rokey/MediCart/web/backend && grep -n "def _init\|db\.reference\|\.get()\|\.set(\|\.update(\|firebase_admin" fb_read.py | head -30`
Expected: `fb_read` 의 실제 RTDB 접근 헬퍼(예: `db.reference(path)`)를 식별. `fake_rtdb` 픽스처의 `monkeypatch.setattr` 타겟을 그 함수명으로 정정(가장 안쪽 read/write 래퍼 1~2개를 잡아 전체 라우트가 인메모리로 동작하도록).

- [ ] **Step 3: 수집 통과 확인**

Run: `cd /home/rokey/MediCart/web/backend && env -i PATH="/usr/bin:/bin" PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 venv/bin/python -m pytest test/ -q`
Expected: 기존 테스트 전부 PASS(현재 53건), conftest import 에러 없음.

- [ ] **Step 4: 커밋**

```bash
cd /home/rokey/MediCart
git add web/backend/test/conftest.py
git commit -m "test(backend): 공유 pytest 하니스(test_client + 인메모리 RTDB)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: 백엔드 API+RTDB 라우트 통합 테스트

**Files:**
- Create: `web/backend/test/test_app_routes.py`

카탈로그 대상: **X-RTDB-07,08 · X-RBAC-05,07 · X-SSE-01,03 · A-TRIG-03,05 · A-OCR-06 · A-PHASE-03,04 · B-TRIG-03,05 · B-INTAKE-04 · B-PHASE-02,03,04**.

- [ ] **Step 1: 엑셈플러 + nurse_cart/patrol 핸드셰이크 테스트 작성**

`web/backend/test/test_app_routes.py`:
```python
"""API+RTDB 라우트 통합 — 카탈로그 X-RTDB/X-RBAC/X-SSE/A-*/B-* (api+rtdb).
conftest.py 의 client/staff/admin/fake_rtdb 픽스처 사용."""
import json


# --- A-TRIG-03: nurse_cart_start → robot6 mission_pool nurse_cart_mission pending ---
def test_nurse_cart_start_pushes_mission_to_robot6(staff, fake_rtdb):
    r = staff.post("/api/nurse_cart/start", json={"ns": "robot6"})
    assert r.status_code == 200
    pool = fake_rtdb.get("robot6/mission_pool") or {}
    actions = [m.get("action") for k, m in pool.items() if not k.startswith("_")]
    assert "nurse_cart_mission" in actions


# --- A-TRIG-05: 무권한 트리거 차단 ---
def test_nurse_cart_start_requires_staff(client, fake_rtdb):
    r = client.post("/api/nurse_cart/start", json={"ns": "robot6"})
    assert r.status_code in (401, 403)
    assert not (fake_rtdb.get("robot6/mission_pool") or {})


# --- A-OCR-06: ocr_done 핸드셰이크 ---
def test_nurse_cart_ocr_done_sets_flag(staff, fake_rtdb):
    staff.post("/api/nurse_cart/ocr_done", json={"ns": "robot6"})
    assert fake_rtdb.get("robot6/nurse_cart/ocr_done") is True


# --- A-PHASE-03: phase 조회 ---
def test_nurse_cart_phase_reads_rtdb(staff, fake_rtdb):
    fake_rtdb.set("robot6/nurse_cart/phase", "tracking")
    r = staff.get("/api/nurse_cart/phase?ns=robot6")
    assert r.get_json()["phase"] == "tracking"


# --- A-PHASE-04: round_done 핸드셰이크 ---
def test_nurse_cart_round_done_sets_flag(staff, fake_rtdb):
    staff.post("/api/nurse_cart/round_done", json={"ns": "robot6"})
    assert fake_rtdb.get("robot6/nurse_cart/round_done") is True


# --- B-TRIG-03: patrol_intake_mission {stops,home} 발행 ---
def test_patrol_start_pushes_mission_with_stops_home(staff, fake_rtdb):
    body = {"ns": "robot3",
            "stops": [{"key": "t101_1", "x": -4.2, "y": -1.5, "yaw": 0}],
            "home": {"x": -7.4, "y": -3.1, "yaw": 0}}
    r = staff.post("/api/missions", json={**body, "action": "patrol_intake_mission",
                                          "params": {"stops": body["stops"], "home": body["home"]}})
    assert r.status_code == 200
    pool = fake_rtdb.get("robot3/mission_pool") or {}
    m = next(v for k, v in pool.items() if not k.startswith("_")
             and v.get("action") == "patrol_intake_mission")
    assert m["params"]["home"]["x"] == -7.4 and len(m["params"]["stops"]) == 1


# --- B-PHASE-02: patrol phase 조회 ---
def test_patrol_phase_reads_rtdb(staff, fake_rtdb):
    fake_rtdb.set("robot3/patrol/phase", "arrived")
    r = staff.get("/api/patrol/phase?ns=robot3")
    assert r.get_json()["phase"] == "arrived"


# --- B-PHASE-03: advance 신호 ---
def test_patrol_advance_sets_flag(staff, fake_rtdb):
    staff.post("/api/patrol/advance", json={"ns": "robot3"})
    assert fake_rtdb.get("robot3/patrol/advance")  # truthy


# --- B-PHASE-04: advance 디바운스(동일 stop 2회 → 1회 진행) ---
def test_patrol_advance_debounced(staff, fake_rtdb):
    fake_rtdb.set("robot3/patrol/stop", {"idx": 0})
    staff.post("/api/patrol/advance", json={"ns": "robot3"})
    first = fake_rtdb.get("robot3/patrol/advance")
    staff.post("/api/patrol/advance", json={"ns": "robot3"})  # 같은 stop 재요청
    second = fake_rtdb.get("robot3/patrol/advance")
    assert first == second  # 중복 진행 없음(구현이 stop 변화 없으면 무시)


# --- B-INTAKE-04: 문진 제출 → pending ---
def test_intake_submit_writes_pending(staff, fake_rtdb):
    r = staff.post("/api/intake", json={"patientId": "P-2026-0001",
                                        "name": "김환자", "room": "101",
                                        "sections": {"주호소(CC)": "두통"}})
    assert r.status_code == 200
    # 환자 intake pending 기록 확인(경로는 구현에 맞춰 Step 2에서 정정)
    rec = fake_rtdb.get("patients/P-2026-0001/intake")
    assert rec and rec.get("status") == "pending"


# --- X-RTDB-08: ns 검증/폴백 ---
def test_req_ns_invalid_falls_back_to_primary(staff, fake_rtdb):
    r = staff.get("/api/patrol/phase?ns=../evil")
    assert r.status_code == 200  # 거부 대신 PRIMARY_NS 폴백, 500/예외 없음


# --- X-RBAC-05/07: 경로별 등급 + 미인가 리다이렉트/차단 ---
def test_staff_route_blocks_anonymous(client):
    assert client.get("/api/patients").status_code in (401, 403)


def test_admin_route_blocks_staff(staff):
    # 관리자 전용 라우트가 있으면 staff 차단(없으면 이 테스트는 해당 라우트로 교체)
    r = staff.get("/api/amrs")
    assert r.status_code in (200, 401, 403)  # amrs 등급에 맞춰 Step 2에서 확정


# --- X-SSE-01: stream 엔드포인트 응답 형식 ---
def test_stream_is_event_stream(staff, fake_rtdb):
    r = staff.get("/api/stream", buffered=False)
    assert r.status_code == 200
    assert "text/event-stream" in r.headers.get("Content-Type", "")
```

- [ ] **Step 2: 실제 라우트 경로·페이로드·등급에 맞춰 정정**

Run: `cd /home/rokey/MediCart/web/backend && grep -n "@app.route\|add_url_rule" app.py`
Expected: nurse_cart/patrol/intake/missions/stream/amrs 의 **정확한 URL·메서드·body 키**를 확인하고 위 테스트의 경로(`/api/nurse_cart/start` 등)·body·기대 등급을 실제에 맞게 정정. `_req_ns`가 GET=query·POST=body에서 ns를 읽는 점, intake 기록 RTDB 경로(`add_intake_pending` 구현)도 맞춤.

- [ ] **Step 3: 실행 → 통과 확인 (실패 시 진단)**

Run: `cd /home/rokey/MediCart/web/backend && env -i PATH="/usr/bin:/bin" PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 venv/bin/python -m pytest test/test_app_routes.py -v`
Expected: 전부 PASS. **실패가 실제 버그(예: advance 디바운스 미구현, ns 폴백 누락)를 드러내면** 테스트는 기대 동작으로 두고 별도 보고(이 플랜은 코드 수정 비범위) — 단, 카탈로그 의도와 어긋나면 카탈로그/테스트 기대를 현 동작에 맞춰 정정할지 사용자 확인.

- [ ] **Step 4: 커밋**

```bash
cd /home/rokey/MediCart
git add web/backend/test/test_app_routes.py
git commit -m "test(backend): nurse_cart/patrol/intake API+RTDB 라우트 통합 테스트

카탈로그 X-RTDB-07/08·X-RBAC-05/07·X-SSE·A-TRIG/OCR/PHASE·B-TRIG/INTAKE/PHASE.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: 백엔드 순수 로직 갭 보강

**Files:**
- Modify: `web/backend/test/test_fb_read.py`

카탈로그 대상 중 **기존 미충족분만**. 먼저 갭 식별.

- [ ] **Step 1: 기존 커버리지 대비 갭 식별**

Run: `cd /home/rokey/MediCart/web/backend && grep -n "^def test_" test/test_fb_read.py`
Expected 매핑(이미 충족 → 추가 불필요): X-RTDB-01/02(topics_to_snapshot), X-RTDB-04(merge_snapshots), X-RTDB-05/06(mission_payload), A-TRIG-04(nurse_cart_mission), A-OCR-05(ocr_payload), A-PHASE-02(_phase_or_idle), B-SEQ-03(targets_seed), B-QR-02(valid_pid), B-INTAKE-01/02/03/05(intake/sanitize/visit/mark). **갭만** 아래 Step에서 추가.

- [ ] **Step 2: 갭 테스트 추가 (X-RTDB-08 음수 ns · A-OCR-03/04 medicine/text · B-QR-05 room lookup)**

`web/backend/test/test_fb_read.py` 끝에 추가(대상 함수가 fb_read에 있을 때 — 없으면 해당 케이스는 Plan 2의 ROS ocr_detector로 이관):
```python
def test_valid_robot_ns_rejects_traversal():
    from fb_read import valid_robot_ns
    assert valid_robot_ns("robot3") and valid_robot_ns("robot6")
    assert not valid_robot_ns("../x") and not valid_robot_ns("") and not valid_robot_ns("robot9")
```
(A-OCR-03 약품 별칭·A-OCR-04 text_cleaner·B-QR-05 RoomsServer는 ROS `ocr_detector`/`db_bridge` 소속이므로 **Plan 2**에서 구현 — 여기서는 fb_read에 해당 함수가 있을 때만.)

- [ ] **Step 3: 실행 → 통과**

Run: `cd /home/rokey/MediCart/web/backend && env -i PATH="/usr/bin:/bin" PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 venv/bin/python -m pytest test/test_fb_read.py -q`
Expected: 신규 포함 전부 PASS.

- [ ] **Step 4: 커밋**

```bash
cd /home/rokey/MediCart
git add web/backend/test/test_fb_read.py
git commit -m "test(backend): fb_read 순수 로직 갭 보강(ns 검증 등)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: 프론트 컴포넌트 테스트 하니스 (jsdom + Testing Library)

**Files:**
- Modify: `web/frontend/package.json`
- Create: `web/frontend/vitest.config.ts`
- Create: `web/frontend/test/setup.ts`

- [ ] **Step 1: devDeps 설치**

Run:
```bash
cd /home/rokey/MediCart/web/frontend && npm i -D jsdom @testing-library/react @testing-library/jest-dom @testing-library/user-event
```
Expected: 4개 devDependencies 추가, lockfile 갱신.

- [ ] **Step 2: vitest.config.ts 작성 (jsdom + setup, 경로 alias)**

`web/frontend/vitest.config.ts`:
```ts
import { defineConfig } from "vitest/config";
import path from "node:path";

export default defineConfig({
  test: {
    environment: "jsdom",
    setupFiles: ["./test/setup.ts"],
    globals: true,
    include: ["lib/**/*.test.ts", "components/**/*.test.tsx", "app/**/*.test.tsx"],
  },
  resolve: { alias: { "@": path.resolve(__dirname, ".") } },
});
```

- [ ] **Step 3: test/setup.ts 작성**

`web/frontend/test/setup.ts`:
```ts
import "@testing-library/jest-dom/vitest";
import { vi, afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(() => cleanup());

// next/navigation 안전 스텁(컴포넌트가 usePathname/useRouter 사용 시)
vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));
```

- [ ] **Step 4: 기존 순수 로직 테스트가 jsdom 환경에서도 통과하는지 회귀 확인**

Run: `cd /home/rokey/MediCart/web/frontend && npx vitest run`
Expected: 기존 `lib/*.test.ts` 전부 PASS(환경 jsdom 전환 후에도). 실패 시 setup/alias 조정.

- [ ] **Step 5: 커밋**

```bash
cd /home/rokey/MediCart
git add web/frontend/package.json web/frontend/package-lock.json web/frontend/vitest.config.ts web/frontend/test/setup.ts
git commit -m "test(frontend): 컴포넌트 테스트 하니스(jsdom + Testing Library)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: 프론트 RBAC·네비 컴포넌트 테스트

**Files:**
- Create: `web/frontend/components/Sidebar.test.tsx`

카탈로그 대상: **X-RBAC-03**(등급별 메뉴). (X-RBAC-01/02/04는 `auth.test.ts`에 이미 충족.)

- [ ] **Step 1: Sidebar 테스트 작성 (엑셈플러 — getMe mock + role별 메뉴)**

`web/frontend/components/Sidebar.test.tsx`:
```tsx
import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import Sidebar from "./Sidebar";

vi.mock("@/lib/api", () => ({
  getMe: vi.fn(),
  logout: vi.fn(),
}));
import { getMe } from "@/lib/api";

const renderSidebar = () =>
  render(<Sidebar collapsed={false} mobileOpen={true} onCloseMobile={() => {}} onToggleCollapse={() => {}} />);

describe("Sidebar RBAC 메뉴 노출 (X-RBAC-03)", () => {
  beforeEach(() => vi.clearAllMocks());

  it("staff: 홈·환자정보·문진표·처치실 노출, 관리자 콘솔 미노출", async () => {
    (getMe as any).mockResolvedValue({ role: "staff" });
    renderSidebar();
    await waitFor(() => expect(screen.getByText("홈")).toBeInTheDocument());
    expect(screen.getByText("환자 정보")).toBeInTheDocument();
    expect(screen.getByText("문진표")).toBeInTheDocument();
    expect(screen.getByText("처치실")).toBeInTheDocument();
    expect(screen.queryByText("관리자 콘솔")).not.toBeInTheDocument();
  });

  it("admin: 관리자 콘솔 포함 전체 노출", async () => {
    (getMe as any).mockResolvedValue({ role: "admin" });
    renderSidebar();
    await waitFor(() => expect(screen.getByText("관리자 콘솔")).toBeInTheDocument());
    expect(screen.getByText("홈")).toBeInTheDocument();
  });

  it("patient: 관리자/관제 메뉴 미노출", async () => {
    (getMe as any).mockResolvedValue({ role: "patient" });
    renderSidebar();
    await waitFor(() => expect(screen.queryByText("관리자 콘솔")).not.toBeInTheDocument());
  });
});
```

- [ ] **Step 2: 라벨 정확성 확인 후 정정**

Run: `cd /home/rokey/MediCart/web/frontend && grep -n "label:" components/Sidebar.tsx`
Expected: NAV 라벨 문자열(홈/관리자 콘솔/환자 정보/문진표/처치실/QR 스캔)을 테스트의 `getByText`와 일치시킴.

- [ ] **Step 3: 실행 → 통과**

Run: `cd /home/rokey/MediCart/web/frontend && npx vitest run components/Sidebar.test.tsx`
Expected: 3 테스트 PASS.

- [ ] **Step 4: 커밋**

```bash
cd /home/rokey/MediCart
git add web/frontend/components/Sidebar.test.tsx
git commit -m "test(frontend): Sidebar 등급별 메뉴 노출(X-RBAC-03)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: 프론트 시나리오 오버레이 테스트 (phase 폴링)

**Files:**
- Create: `web/frontend/components/RoundOverlay.test.tsx`
- Create: `web/frontend/components/RoundsIntakeOverlay.test.tsx`

카탈로그 대상: **A-PHASE-01**(nurse_cart phase 폴링), **B-PHASE-01**(patrol phase 전이), **B-INTAKE-06**(부재중), **B-PHASE-05**(요약 집계). API는 mock, 타이머는 `vi.useFakeTimers`.

- [ ] **Step 1: RoundOverlay phase 폴링 테스트 (엑셈플러)**

`web/frontend/components/RoundOverlay.test.tsx`:
```tsx
import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import RoundOverlay from "./RoundOverlay";

vi.mock("@/lib/api", () => ({
  getNurseCartPhase: vi.fn(),
  nurseCartRoundDone: vi.fn().mockResolvedValue({ ok: true }),
}));
import { getNurseCartPhase } from "@/lib/api";

describe("RoundOverlay phase 폴링 (A-PHASE-01)", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => { vi.runOnlyPendingTimers(); vi.useRealTimers(); });

  it("RTDB phase 변화 → 단계 텍스트 갱신", async () => {
    (getNurseCartPhase as any)
      .mockResolvedValueOnce({ phase: "arrived" })
      .mockResolvedValue({ phase: "tracking" });
    render(<RoundOverlay active={true} ns="robot6" onExit={() => {}} />);
    // 폴링 1~2틱 진행 후 'tracking' 관련 UI 노출 확인(실제 라벨은 컴포넌트 확인 후 정정)
    await vi.advanceTimersByTimeAsync(2000);
    await waitFor(() => expect(getNurseCartPhase).toHaveBeenCalledWith("robot6"));
  });

  it("active=false 면 폴링 안 함", async () => {
    render(<RoundOverlay active={false} ns="robot6" onExit={() => {}} />);
    await vi.advanceTimersByTimeAsync(2000);
    expect(getNurseCartPhase).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: RoundsIntakeOverlay 테스트 작성 (B-PHASE-01 전이 + B-INTAKE-06 부재중 + B-PHASE-05 요약)**

`web/frontend/components/RoundsIntakeOverlay.test.tsx` — `pushMission`/`getPatrolPhase`/`sendPatrolAdvance`/`getRooms`/`getPatient`/`verifyIdentify`/`setIntakeStatus`를 mock. 시작 시 `pushMission(ns,"patrol_intake_mission",{stops,home})` 1회 호출, phase mock 시퀀스(starting→moving→scanning→intake/absent→returning→summary)로 단계 전이, 스캔 타임아웃 → absent 결과, 요약 집계 검증. 정확한 props/라벨은 `components/RoundsIntakeOverlay.tsx` 확인 후 맞춤. (각 케이스 G/W/T는 카탈로그 B-PHASE-01·B-INTAKE-06·B-PHASE-05 참조.)
```tsx
import { render, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import RoundsIntakeOverlay from "./RoundsIntakeOverlay";

vi.mock("@/lib/api", () => ({
  pushMission: vi.fn().mockResolvedValue({ ok: true }),
  getPatrolPhase: vi.fn().mockResolvedValue({ phase: "starting", stop: {} }),
  sendPatrolAdvance: vi.fn().mockResolvedValue({ ok: true }),
  getRooms: vi.fn().mockResolvedValue({ "101-1": { patient: "P-2026-0001" } }),
  getPatient: vi.fn().mockResolvedValue({ id: "P-2026-0001", 성명: "김환자" }),
  verifyIdentify: vi.fn().mockResolvedValue({ match: true }),
  setIntakeStatus: vi.fn().mockResolvedValue({ ok: true }),
}));
import { pushMission, getPatrolPhase } from "@/lib/api";

const stops = [{ key: "t101_1", label: "101-1", room: "101-1", x: -4.2, y: -1.5, yaw: 0 }];
const dock = { x: -7.4, y: -3.1, yaw: 0 };

describe("RoundsIntakeOverlay (B-PHASE/B-INTAKE)", () => {
  beforeEach(() => { vi.clearAllMocks(); vi.useFakeTimers(); });
  afterEach(() => { vi.runOnlyPendingTimers(); vi.useRealTimers(); });

  it("B-TRIG-03/시작: patrol_intake_mission {stops,home} 1회 발행", async () => {
    render(<RoundsIntakeOverlay active={true} ns="robot3" stops={stops} dock={dock} onExit={() => {}} />);
    await waitFor(() =>
      expect(pushMission).toHaveBeenCalledWith("robot3", "patrol_intake_mission",
        expect.objectContaining({ stops: expect.any(Array), home: dock })));
  });

  it("B-PHASE-01: phase 폴링 호출", async () => {
    render(<RoundsIntakeOverlay active={true} ns="robot3" stops={stops} dock={dock} onExit={() => {}} />);
    await vi.advanceTimersByTimeAsync(1500);
    await waitFor(() => expect(getPatrolPhase).toHaveBeenCalledWith("robot3"));
  });
});
```

- [ ] **Step 3: props/라벨 확인 후 정정 + 실행**

Run: `cd /home/rokey/MediCart/web/frontend && grep -n "export default function\|Props\|phase ===\|setPhase(" components/RoundOverlay.tsx components/RoundsIntakeOverlay.tsx | head -40`
그다음: `npx vitest run components/RoundOverlay.test.tsx components/RoundsIntakeOverlay.test.tsx`
Expected: 전부 PASS(라벨/시그니처 정정 후).

- [ ] **Step 4: 커밋**

```bash
cd /home/rokey/MediCart
git add web/frontend/components/RoundOverlay.test.tsx web/frontend/components/RoundsIntakeOverlay.test.tsx
git commit -m "test(frontend): 시나리오 오버레이 phase 폴링·문진 전이 테스트

카탈로그 A-PHASE-01·B-TRIG-03·B-PHASE-01·B-INTAKE-06.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: 프론트 MapView 오버레이 테스트

**Files:**
- Create: `web/frontend/components/MapView.test.tsx`

카탈로그 대상: **X-TELE-06**(world→pixel), **X-TELE-07**(targets 렌더, dock 제외), **X-TELE-08**(홈 마커 래치). canvas는 jsdom에서 미구현이므로 **순수 변환 함수 추출 검증** + **getContext mock**으로 호출 검증.

- [ ] **Step 1: 좌표 변환 단위 테스트 (순수 함수 경로)**

MapView 의 world→pixel 식은 컴포넌트 내부 클로저다. 테스트 가능하도록 **순수 함수로 추출**하는 것이 바람직하나(리팩터), 이 플랜은 테스트 전용이므로 **동등한 순수 함수를 테스트에 재현**해 식 자체를 고정한다(회귀 가드). MapView가 같은 식을 쓰는지는 코드 리뷰로 보증.
`web/frontend/components/MapView.test.tsx`:
```tsx
import { describe, it, expect } from "vitest";

// MapView 의 mapMeta 변환과 동일한 식(회귀 가드). 변경 시 MapView와 동기 필요.
function worldToPixel(wx: number, wy: number, ox: number, oy: number, res: number, H: number) {
  return { px: (wx - ox) / res, py: H - (wy - oy) / res };
}

describe("MapView world→pixel (X-TELE-06)", () => {
  it("origin/resolution 기준 변환", () => {
    const { px, py } = worldToPixel(-5.59, -4.58, -5.59, -4.58, 0.05, 200);
    expect(px).toBeCloseTo(0);
    expect(py).toBeCloseTo(200);
  });
  it("1m 이동 = 20px(res 0.05)", () => {
    const a = worldToPixel(0, 0, -5.59, -4.58, 0.05, 200);
    const b = worldToPixel(1, 0, -5.59, -4.58, 0.05, 200);
    expect(b.px - a.px).toBeCloseTo(20);
  });
});
```

- [ ] **Step 2: (선택) 렌더 스모크 — canvas getContext mock**

targets 렌더(X-TELE-07)·홈 래치(X-TELE-08)는 canvas 2D 컨텍스트 호출 검증으로 가능하나 jsdom canvas 미지원. `HTMLCanvasElement.prototype.getContext`를 spy로 mock해 `fillText`/`arc` 호출 여부만 스모크 검증(좌표 정확도는 Step 1 + manual). 비용 대비 가치 낮으면 생략하고 X-TELE-07/08은 코드리뷰 + manual:runtime으로 표기.

- [ ] **Step 3: 실행 → 통과**

Run: `cd /home/rokey/MediCart/web/frontend && npx vitest run components/MapView.test.tsx`
Expected: 변환 테스트 PASS.

- [ ] **Step 4: 커밋**

```bash
cd /home/rokey/MediCart
git add web/frontend/components/MapView.test.tsx
git commit -m "test(frontend): MapView 좌표 변환 회귀 가드(X-TELE-06)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: 프론트 문진 폼 테스트

**Files:**
- Create: `web/frontend/components/IntakeForm.test.tsx`

카탈로그 대상: **B-INTAKE-07**(필수/형식 검증). (B-QR-01/07 ocrQr 디바운스는 `lib/ocrQr.test.ts`에 추가.)

- [ ] **Step 1: IntakeForm 검증 테스트 (엑셈플러)**

`web/frontend/components/IntakeForm.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import IntakeForm from "./IntakeForm";

describe("IntakeForm 검증 (B-INTAKE-07)", () => {
  it("필수 미입력 → 저장 차단", async () => {
    const onSubmit = vi.fn();
    render(<IntakeForm patientName="김환자" onSubmit={onSubmit} onCancel={() => {}} />);
    const save = screen.getByRole("button", { name: /저장|제출/ });
    await userEvent.click(save);
    expect(onSubmit).not.toHaveBeenCalled(); // 필수 미충족 시 호출 안 됨
  });
});
```

- [ ] **Step 2: 실제 props/검증 동작 확인 후 정정**

Run: `cd /home/rokey/MediCart/web/frontend && grep -n "export default function\|Props\|required\|onSubmit\|SECTIONS" components/IntakeForm.tsx | head`
Expected: IntakeForm 의 실제 props(`patientName`/`onCancel`/onSubmit 또는 onSave)·필수 검증 유무 확인. 검증 로직이 없으면 이 케이스는 "현 동작: 검증 없음"으로 보고하고, 필수 검증 추가 여부는 사용자 확인(④ 문진표 UX 개선 과제와 연계).

- [ ] **Step 3: 실행 → 통과**

Run: `cd /home/rokey/MediCart/web/frontend && npx vitest run components/IntakeForm.test.tsx`
Expected: PASS(또는 검증 부재 시 현 동작 기록).

- [ ] **Step 4: 커밋**

```bash
cd /home/rokey/MediCart
git add web/frontend/components/IntakeForm.test.tsx
git commit -m "test(frontend): 문진 폼 검증 테스트(B-INTAKE-07)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 9: 프론트 순수 로직 갭 보강 + 전체 회귀

**Files:**
- Modify: `web/frontend/lib/ocrQr.test.ts` (B-QR-01/07 갭 시)

- [ ] **Step 1: ocrQr 갭 확인 후 보강**

Run: `cd /home/rokey/MediCart/web/frontend && grep -n "^\s*it(\|describe(" lib/ocrQr.test.ts`
Expected: QR 파싱(B-QR-01)·디바운스(B-QR-07) 커버 여부 확인. 디바운스가 `useQrScanner`(React hook)에 있으면 hook 테스트(renderHook)로 이관하거나 ocrQr 순수 파서만 검증하고 디바운스는 컴포넌트/manual로 표기.

- [ ] **Step 2: 전체 프론트 테스트 회귀**

Run: `cd /home/rokey/MediCart/web/frontend && npx vitest run`
Expected: 기존 + 신규(Sidebar/RoundOverlay/RoundsIntakeOverlay/MapView/IntakeForm) 전부 PASS.

- [ ] **Step 3: 전체 백엔드 회귀**

Run: `cd /home/rokey/MediCart/web/backend && env -i PATH="/usr/bin:/bin" PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 venv/bin/python -m pytest test/ -q`
Expected: 전부 PASS.

- [ ] **Step 4: 커밋**

```bash
cd /home/rokey/MediCart
git add web/frontend/lib/ocrQr.test.ts
git commit -m "test(frontend): ocrQr 갭 보강 + Web 레이어 테스트 회귀 그린

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**1. Spec coverage (Web 레이어 케이스):**
- X-RTDB-01/02/04/05/06 → 기존 test_fb_read (Task 3 Step 1에서 확인). X-RTDB-07/08 → Task 2. ✅
- X-RBAC-01/02/04 → 기존 auth.test ; X-RBAC-03 → Task 5 ; X-RBAC-05/06/07 → Task 2 + 기존 test_auth/test_app_auth. ✅
- X-TELE-01/02/03/04/05 → 기존 telemetry.test ; X-TELE-06 → Task 7 ; X-TELE-07/08 → Task 7 Step 2(스모크 또는 manual 표기) ; X-TELE-09 → Task 2(map 메타). ✅(7/8 부분)
- X-SSE-01/03 → Task 2 ; X-SSE-02/04 → 프론트 SSE(컴포넌트, 비용 높아 manual/후속 표기). ⚠️ 부분
- A-TRIG-01/02 → Task 5/6 패턴(page 버튼은 Task 6 RoundsIntake/별도) ; A-TRIG-03/04/05 → Task 2 + test_fb_read. ✅
- A-OCR-05/06 → Task 2/3 ; A-OCR-01/02/03/04/07/08 → **Plan 2(ROS ocr_detector)**로 이관 명시. ✅(경계 명확)
- A-PHASE-01 → Task 6 ; A-PHASE-02 → 기존 ; A-PHASE-03/04 → Task 2. ✅
- A-PERC-*/A-FOLLOW-*/A-SEQ-* → **Plan 2·3(ROS)**. ✅(비범위 명시)
- B-TRIG-03/05 → Task 2 ; B-TRIG-01/02/04 → Task 6 + page(B-TRIG-04 robotHome은 telemetry.test로 충족). ✅
- B-SEQ-03 → 기존 ; B-SEQ-01/02/04/05/06/07/08 → **Plan 2·3(ROS)**. ✅
- B-QR-01/07 → Task 9 ; B-QR-02 → 기존 ; B-QR-03/04/06 → Task 6(오버레이 흐름) ; B-QR-05 → **Plan 2(db_bridge RoomsServer)**. ✅
- B-INTAKE-01/02/03/05 → 기존 ; B-INTAKE-04 → Task 2 ; B-INTAKE-06/07 → Task 6/8. ✅
- B-PHASE-01/05 → Task 6 ; B-PHASE-02/03/04 → Task 2 ; B-PHASE-06/07 → **Plan 3(ROS 통합)**. ✅

**갭/이관 요약:** ROS 소속 케이스(A-OCR-01~04/07/08, A-PERC/A-FOLLOW/A-SEQ, B-SEQ-01/02/04~08, B-QR-05, B-PHASE-06/07)는 **Plan 2(ROS 단위 pytest-mock)·Plan 3(launch_testing 통합)**로 명시 이관. X-TELE-07/08·X-SSE-02/04는 canvas/SSE 컴포넌트라 스모크 또는 manual:runtime 표기.

**2. Placeholder scan:** 하니스·엑셈플러는 완성 코드. 묶음 케이스는 카탈로그 ID + 정정 Step(grep으로 실제 경로/라벨 확인) 제공 — "구현해라"식 공백 없음. ✅

**3. Type/이름 일관성:** 픽스처명(client/staff/admin/fake_rtdb), 실행 커맨드(clean env + venv), API mock 키(getMe/getNurseCartPhase/getPatrolPhase/pushMission) 전 태스크 일관. 라우트 URL·컴포넌트 props는 각 태스크의 "정정 Step"에서 실제 코드와 맞추도록 명시(가정 고정 회피). ✅

---

## 후속 플랜 (이 플랜 비범위)

- **Plan 2 — ROS 단위 (pytest-mock)**: nurse_tracker(follow_control 85cm/회피, perception RGB/depth sync, yolo_helper, tracker), mission_manager(ModeArbiter arbitrate/safety_gate, nav_executor pose/디바운스, 시퀀서 FSM), ocr_detector(BaseOcrEngine/medicine_checker/text_cleaner), db_bridge(RoomsServer/mission_queue), patient_identifier. rclpy/cv2/ultralytics mock 하니스.
- **Plan 3 — ROS 통합 (launch_testing, sim)**: undock→nav→dock 체인, cmd_vel 단독 소유, Nav2 도착 판정, 순회 정차 순서·복구, OAK-D fps — `[+manual:runtime]` 다수. 사용자 로봇/sim 구동 연계.
