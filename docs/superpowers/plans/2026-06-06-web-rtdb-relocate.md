# web RTDB 전환 + MediCart 이전 + 정리 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.
> **실행 제약(CLAUDE.md):** Flask·프론트·firebase 연결 등 **서버 구동은 직접 실행 금지 — 사용자에게 명령·순서 제시**. 순수 로직 pytest·git·파일 이동은 직접 가능.

**Goal:** intel1 `hospital_web` 를 `MediCart/web` 으로 이전하고, Flask 백엔드가 firebase-admin(service account)으로 FB RTDB를 서버측에서 읽어(redis_bus→fb_read, patient_data→patients) 기존 SSE/REST로 프론트에 제공하도록 전환한다.

**Architecture:** 순수 로직(snapshot 병합·검증·cmd 페이로드·patient 변환)을 firebase/Flask와 분리해 단위테스트한다. `fb_read.py`가 RTDB 경계(리스너→SSE, get, cmd set)다. 프론트는 Flask만 호출(RTDB 미접촉). RTDB Rules는 전면 잠금(admin 전용). 이전은 git 이동(intel1 제거→MediCart 추가).

**Tech Stack:** Flask, firebase-admin, PyYAML, pytest, Next.js(소비측 변경 최소).

**스펙:** `MediCart/docs/superpowers/specs/2026-06-06-web-rtdb-relocate-design.md`
**경로 표기:** `INTEL=/home/rokey/rokey_ws/src/intel1`, `MC=/home/rokey/MediCart`.

---

## File Structure (이전 후 `MC/web/`)
```
web/backend/  app.py · fb_read.py(신규) · patients.py(신규) · requirements.txt · .env.example(신규) · test/
web/frontend/ app/ components/ lib/ public/ (sync-ns 제거) · CLAUDE.md
web/deploy/   medicart-{backend,frontend,tunnel}.service · setup-tunnel.sh
web/docs/     architecture.md · setup.md · deploy.md
web/legacy/   redis_bus.py · patient_data.py · backend-rooms.yaml · sync-ns.cjs · intel-*.service
web/README.md
```

---

### Task 1: hospital_web → MediCart/web 이전 (git move)

**Files:** 이동(소스만, 빌드산출물 제외).

- [ ] **Step 1: rsync 복사(빌드산출물 제외) + 구조 생성**

> 사전: 옛 위치에서 도는 Flask/프론트가 있으면 사용자가 먼저 중지(이 작업은 파일 이동).

Run:
```bash
mkdir -p /home/rokey/MediCart/web
rsync -a --exclude node_modules --exclude .next --exclude venv --exclude __pycache__ \
  --exclude '*.pyc' /home/rokey/rokey_ws/src/intel1/hospital_web/ /home/rokey/MediCart/web/
mkdir -p /home/rokey/MediCart/web/docs /home/rokey/MediCart/web/legacy
ls /home/rokey/MediCart/web
```
Expected: `backend  deploy  docs  frontend  legacy` (+ 기타 파일).

- [ ] **Step 2: MediCart .gitignore에 빌드산출물 차단**

Append to `/home/rokey/MediCart/.gitignore` (없으면 생성):
```
web/frontend/node_modules/
web/frontend/.next/
web/backend/venv/
__pycache__/
*.pyc
serviceAccountKey.json
**/serviceAccountKey.json
.env
web/**/.env
```

- [ ] **Step 3: MediCart에 web/ 추가 커밋**

Run:
```bash
cd /home/rokey/MediCart
git add web .gitignore docs/superpowers/specs/2026-06-06-web-rtdb-relocate-design.md
git commit -m "feat(web): hospital_web 이전(소스) → MediCart/web + gitignore"
```
Expected: 커밋 성공(node_modules/.next/venv 미포함).

- [ ] **Step 4: intel1에서 hospital_web 제거**

Run:
```bash
cd /home/rokey/rokey_ws/src/intel1
git rm -r --quiet hospital_web
rm -rf hospital_web    # 추적 안 된 node_modules/.next/venv 까지 정리
git commit -m "chore(intel1): hospital_web → MediCart/web 이전(이 repo에서 제거)"
```
Expected: intel1에 hospital_web 없음. (로봇측 ward_bridge·ROS 무관.)

- [ ] **Step 5: 구조 확인**

Run: `find /home/rokey/MediCart/web -maxdepth 2 -not -path '*/node_modules/*' -type d | sort`
Expected: backend, frontend(app/components/lib/public), deploy, docs, legacy.

---

### Task 2: `fb_read.py` 순수 로직 (병합·검증·cmd 페이로드)

**Files:**
- Create: `MC/web/backend/fb_read.py`
- Test: `MC/web/backend/test/test_fb_read.py`

- [ ] **Step 1: Write the failing test**

Create `/home/rokey/MediCart/web/backend/test/test_fb_read.py`:

```python
"""fb_read 순수 로직 단위 테스트 (firebase/Flask 무관).

실행: cd MediCart/web/backend && python3 -m pytest test/test_fb_read.py -v
"""
import pytest

from fb_read import merge_snapshots, cmd_payload, valid_pid


def test_merge_snapshots_injects_source_and_handles_missing():
    raw = {"robot6": {"pose": {"x": 1.0}, "mode": "idle"}}
    out = merge_snapshots(raw, ["robot6", "amr2"])
    assert out["robot6"]["mode"] == "idle"
    assert out["robot6"]["source"] == "robot6"
    assert out["amr2"] is None        # RTDB에 없는 소스


def test_merge_snapshots_none_raw():
    out = merge_snapshots(None, ["robot6"])
    assert out == {"robot6": None}


def test_cmd_payload_valid():
    p = cmd_payload("start", "mapping", {"k": 1}, ts=1000)
    assert p == {"action": "start", "mode": "mapping", "params": {"k": 1}, "ts": 1000}


def test_cmd_payload_clear_allows_no_mode():
    p = cmd_payload("clear", None, None, ts=5)
    assert p["action"] == "clear" and p["params"] == {}


def test_cmd_payload_bad_action():
    with pytest.raises(ValueError):
        cmd_payload("danger", "mapping", None, ts=1)


def test_cmd_payload_bad_mode():
    with pytest.raises(ValueError):
        cmd_payload("start", "evil", None, ts=1)


def test_valid_pid():
    assert valid_pid("P-2026-0001") is True
    assert valid_pid("../x") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/rokey/MediCart/web/backend && python3 -m pytest test/test_fb_read.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fb_read'`

- [ ] **Step 3: Write minimal implementation** — Create `/home/rokey/MediCart/web/backend/fb_read.py` (pure logic + firebase wiring stubs added in Task 3; here only pure parts + module constants):

```python
"""fb_read — Flask 백엔드의 Firebase RTDB 경계 (redis_bus.py 대체).

순수 로직(snapshot 병합·검증·cmd 페이로드)은 firebase/Flask 무관이라 단위테스트한다.
firebase-admin 결선(리스너→SSE·get·cmd set·intake)은 같은 모듈에 Task 3에서 추가한다.
프론트는 이 백엔드의 SSE/REST만 쓰고 RTDB를 직접 만지지 않는다.
"""
import os
import re

PRIMARY_NS = os.environ.get("PRIMARY_NS", "robot6")
SECONDARY_NS = os.environ.get("SECONDARY_NS", "amr2")
SOURCES = [PRIMARY_NS, SECONDARY_NS]

_PID_RE = re.compile(r"^P-\d{4}-\d{4}$")
_MODE_RE = re.compile(r"^(mapping|patrol|errand|guide|intake|round)$")
_ACTION_RE = re.compile(r"^(start|stop|clear)$")


def valid_pid(pid):
    return bool(_PID_RE.match(str(pid)))


def merge_snapshots(robots_raw, sources):
    """RTDB robots/ get() 결과({ns: state}) → {src: state(+source)|None}."""
    raw = robots_raw or {}
    out = {}
    for src in sources:
        st = raw.get(src) if isinstance(raw, dict) else None
        if isinstance(st, dict):
            st = dict(st)
            st["source"] = src
            out[src] = st
        else:
            out[src] = None
    return out


def cmd_payload(action, mode, params, ts):
    """웹→로봇 명령 페이로드 빌드(화이트리스트 검증). robots/{ns}/cmd 에 set 될 dict."""
    if not _ACTION_RE.match(str(action)):
        raise ValueError("invalid action")
    if action != "clear" and not _MODE_RE.match(str(mode or "")):
        raise ValueError("invalid mode")
    return {"action": action, "mode": mode, "params": params or {}, "ts": int(ts)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/rokey/MediCart/web/backend && python3 -m pytest test/test_fb_read.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
cd /home/rokey/MediCart
git add web/backend/fb_read.py web/backend/test/test_fb_read.py
git commit -m "feat(web): fb_read 순수 로직(snapshot 병합·검증·cmd 페이로드)"
```

---

### Task 3: `fb_read.py` firebase-admin 결선 (리스너→SSE·get·set)

**Files:**
- Modify: `MC/web/backend/fb_read.py` (firebase 결선 추가)

- [ ] **Step 1: Append firebase-admin wiring** — `fb_read.py` 끝에 추가:

```python
import json
import queue
import threading
import time

_db = None


def _init():
    global _db
    if _db is not None:
        return _db
    import firebase_admin
    from firebase_admin import credentials, db
    if not firebase_admin._apps:
        firebase_admin.initialize_app(
            credentials.Certificate(os.environ["FB_CRED"]),
            {"databaseURL": os.environ["FB_DB_URL"]})
    _db = db
    return _db


def snapshots():
    """두 AMR 최신 스냅샷 {src: state|None}. (RTDB robots/ 1회 읽기)"""
    db = _init()
    raw = db.reference("robots").get()
    return merge_snapshots(raw, SOURCES)


def _sse_listen(path_of, channels):
    """ns별 RTDB 경로 변경을 큐로 모아 SSE 제너레이터로 push(source 주입)."""
    db = _init()
    q = queue.Queue(maxsize=200)

    def _mk(src):
        def _on(event):
            if event.data is None:
                return
            payload = {"source": src, "data": event.data, "path": event.path}
            try:
                q.put(json.dumps(payload, separators=(",", ":")), block=False)
            except queue.Full:
                pass
        return _on

    for src in channels:
        db.reference(path_of(src)).listen(_mk(src))

    while True:
        try:
            yield f"data: {q.get(timeout=15)}\n\n"
        except queue.Empty:
            yield ": keepalive\n\n"


def telemetry_stream():
    return _sse_listen(lambda s: f"robots/{s}/state", SOURCES)


def alert_stream():
    return _sse_listen(lambda s: f"robots/{s}/alerts", SOURCES)


def publish_mode_cmd(action, mode, params=None):
    db = _init()
    payload = cmd_payload(action, mode, params, ts=int(time.time() * 1000))
    db.reference(f"robots/{PRIMARY_NS}/cmd").set(payload)


def save_intake(pid, data):
    if not valid_pid(pid):
        raise ValueError("invalid patientId")
    db = _init()
    db.reference(f"patients/{pid}/intake").set(
        {"data": data, "ts": int(time.time() * 1000)})


def get_intake(pid):
    if not valid_pid(pid):
        return None
    db = _init()
    node = db.reference(f"patients/{pid}/intake").get()
    return (node or {}).get("data") if isinstance(node, dict) else None
```

- [ ] **Step 2: 문법·순수로직 회귀**

Run: `cd /home/rokey/MediCart/web/backend && python3 -c "import ast; ast.parse(open('fb_read.py').read()); print('OK')" && python3 -m pytest test/test_fb_read.py -q`
Expected: `OK` + 7 passed (firebase_admin은 함수 내부 import라 미설치에도 파싱·순수테스트 통과).

- [ ] **Step 3: Commit**

```bash
cd /home/rokey/MediCart
git add web/backend/fb_read.py
git commit -m "feat(web): fb_read firebase-admin 결선(리스너→SSE·snapshots·cmd·intake)"
```

---

### Task 4: `patients.py` (RTDB 환자 + 순수 변환)

**Files:**
- Create: `MC/web/backend/patients.py`
- Test: `MC/web/backend/test/test_patients.py`

- [ ] **Step 1: Write the failing test**

Create `/home/rokey/MediCart/web/backend/test/test_patients.py`:

```python
"""patients 순수 변환 단위 테스트.

실행: cd MediCart/web/backend && python3 -m pytest test/test_patients.py -v
"""
from patients import patient_node_to_api


def test_patient_node_to_api_flattens():
    node = {"info": {"성명": "홍길동", "혈액형": "A"},
            "vitals": {"통증점수": 3},
            "intake": {"data": {"주호소": "두통"}, "ts": 5}}
    out = patient_node_to_api("P-2026-0001", node)
    assert out["id"] == "P-2026-0001"
    assert out["성명"] == "홍길동" and out["혈액형"] == "A"
    assert out["통증점수"] == 3
    assert out["intake"] == {"주호소": "두통"}
    assert out["visits"] == []          # visits 미임포트 → 빈 배열


def test_patient_node_to_api_with_visits_and_no_intake():
    node = {"info": {"성명": "김"}, "vitals": {}, "visits": [{"방문일": "2026-01-01"}]}
    out = patient_node_to_api("P-2026-0002", node)
    assert out["visits"] == [{"방문일": "2026-01-01"}]
    assert out["intake"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/rokey/MediCart/web/backend && python3 -m pytest test/test_patients.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'patients'`

- [ ] **Step 3: Write minimal implementation** — Create `/home/rokey/MediCart/web/backend/patients.py`:

```python
"""patients — RTDB patients/ → 프론트 형식 (patient_data.py 대체).

RTDB 노드 {info, vitals[, intake][, visits]} 를 프론트가 기대하는 평탄 dict
({id, ...info, ...vitals, visits, intake})로 변환한다. 순수 변환은 단위테스트.
RTDB 읽기는 fb_read._init() 공유.
"""


def patient_node_to_api(pid, node):
    """patients/{pid} 노드 → 프론트 환자 dict."""
    node = node or {}
    out = {"id": pid}
    out.update(node.get("info") or {})
    out.update(node.get("vitals") or {})
    out["visits"] = node.get("visits") or []
    intake = node.get("intake")
    out["intake"] = (intake or {}).get("data") if isinstance(intake, dict) else None
    return out


def load_patients():
    from fb_read import _init
    raw = _init().reference("patients").get() or {}
    return [patient_node_to_api(pid, node) for pid, node in raw.items()]


def get_patient(pid):
    from fb_read import _init, valid_pid
    if not valid_pid(pid):
        return None
    node = _init().reference(f"patients/{pid}").get()
    return patient_node_to_api(pid, node) if node else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/rokey/MediCart/web/backend && python3 -m pytest test/test_patients.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
cd /home/rokey/MediCart
git add web/backend/patients.py web/backend/test/test_patients.py
git commit -m "feat(web): patients RTDB 읽기 + 순수 변환(patient_data.py 대체)"
```

---

### Task 5: `app.py` 재결선 + requirements

**Files:**
- Modify: `MC/web/backend/app.py`, `MC/web/backend/requirements.txt`

- [ ] **Step 1: app.py import 교체** — In `MC/web/backend/app.py`:

`import patient_data` → `import patients`
`import redis_bus` → `import fb_read`

그리고 사용처 치환(엔드포인트 시그니처·인증 불변, 호출 모듈만):
- `patient_data.load_patients()` → `patients.load_patients()`
- `patient_data.get_patient(pid)` → `patients.get_patient(pid)` (2곳: `/api/patients/<pid>`, `/api/intake`)
- `redis_bus.get_intake(pid)` → `fb_read.get_intake(pid)`
- `redis_bus.snapshots()` → `fb_read.snapshots()`
- `redis_bus.telemetry_stream()` → `fb_read.telemetry_stream()`
- `redis_bus.alert_stream()` → `fb_read.alert_stream()`
- `redis_bus.publish_mode_cmd(...)` → `fb_read.publish_mode_cmd(...)`
- `redis_bus.save_intake(pid, body)` → `fb_read.save_intake(pid, body)`

`/api/rooms` 핸들러는 `rooms.yaml` 파일 대신 RTDB rooms 를 읽도록 교체:
```python
@app.get("/api/rooms")
def rooms():
    fb_read._init()
    from fb_read import _db
    return jsonify({"rooms": _db.reference("rooms").get() or {}})
```

- [ ] **Step 2: requirements.txt 교체** — `MC/web/backend/requirements.txt` 전체를:
```
flask
flask-cors
firebase-admin
pyyaml
```

- [ ] **Step 3: 문법 검증 + Redis/xlsx 잔재 확인**

Run:
```bash
cd /home/rokey/MediCart/web/backend
python3 -c "import ast; ast.parse(open('app.py').read()); print('OK')"
grep -n "redis_bus\|patient_data\|import redis\|pandas" app.py || echo "잔재 없음"
```
Expected: `OK` + `잔재 없음`

- [ ] **Step 4: Commit**

```bash
cd /home/rokey/MediCart
git add web/backend/app.py web/backend/requirements.txt
git commit -m "feat(web): app.py를 fb_read/patients(RTDB)로 재결선 + requirements 정리"
```

---

### Task 6: 자기완결 설정 + deploy 리네임 + legacy 정리

**Files:**
- Create: `MC/web/backend/.env.example`
- Modify: frontend NS 설정, deploy 서비스, legacy 이동

- [ ] **Step 1: .env.example**

Create `/home/rokey/MediCart/web/backend/.env.example`:
```
# Firebase
FB_CRED=/path/to/serviceAccountKey.json
FB_DB_URL=https://<project>-default-rtdb.asia-southeast1.firebasedatabase.app
# AMR 네임스페이스
PRIMARY_NS=robot6
SECONDARY_NS=amr2
# 웹 인증/CORS
INTEL_PASSWORD=rokey1234
INTEL_AUTH_TOKEN=intel-demo-token-2026
FRONTEND_ORIGIN=https://intel.thatshoon.com
COOKIE_SECURE=1
PORT=5000
# 맵 파일(있으면 서빙) — web 자기완결 경로 또는 공유 경로
MAP_PNG=/home/rokey/MediCart/web/backend/maps/ward_map.png
MAP_YAML=/home/rokey/MediCart/web/backend/maps/ward_map.yaml
```

- [ ] **Step 2: 프론트 NS 설정 — sync-ns 제거** — `MC/web/frontend/package.json` 의 prebuild에서 sync-ns 호출이 있으면 제거하고, `lib/config.ts` 는 그대로(`NEXT_PUBLIC_PRIMARY_NS` env 직접). `frontend/scripts/sync-ns.cjs` 는 Step 4에서 legacy로 이동.

Run(확인): `grep -n "sync-ns" /home/rokey/MediCart/web/frontend/package.json || echo "prebuild 없음"`
prebuild 스크립트에 `node scripts/sync-ns.cjs` 가 있으면 그 줄을 제거(없으면 생략).

- [ ] **Step 3: deploy 서비스 리네임** — `MC/web/deploy/` 에서 새 서비스 파일 생성(경로를 MediCart/web 으로):

Create `/home/rokey/MediCart/web/deploy/medicart-backend.service`:
```ini
[Unit]
Description=MediCart web Flask backend (:5000)
After=network.target

[Service]
User=rokey
WorkingDirectory=/home/rokey/MediCart/web/backend
EnvironmentFile=/home/rokey/MediCart/web/backend/.env
ExecStart=/home/rokey/MediCart/web/backend/venv/bin/python app.py
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```
(frontend·tunnel 서비스도 동일 패턴으로 경로만 MediCart/web 으로 만든다 — 기존 intel-frontend/intel-tunnel 내용 복사 후 Description/경로 치환.)

- [ ] **Step 4: legacy 이동**

Run:
```bash
cd /home/rokey/MediCart/web
git mv backend/redis_bus.py legacy/redis_bus.py
git mv backend/patient_data.py legacy/patient_data.py
git mv backend/rooms.yaml legacy/backend-rooms.yaml
git mv frontend/scripts/sync-ns.cjs legacy/sync-ns.cjs 2>/dev/null || true
git mv deploy/intel-backend.service legacy/intel-backend.service 2>/dev/null || true
git mv deploy/intel-frontend.service legacy/intel-frontend.service 2>/dev/null || true
git mv deploy/intel-tunnel.service legacy/intel-tunnel.service 2>/dev/null || true
```

- [ ] **Step 5: 회귀 + 커밋**

Run: `cd /home/rokey/MediCart/web/backend && python3 -m pytest test/ -q`
Expected: 9 passed (fb_read 7 + patients 2).

```bash
cd /home/rokey/MediCart
git add web
git commit -m "feat(web): 자기완결 .env + deploy medicart-* 리네임 + legacy 정리"
```

---

### Task 7: 개발문서 통합 (web/docs)

**Files:**
- Create: `MC/web/docs/architecture.md`, `setup.md`, `deploy.md`, `MC/web/README.md`

- [ ] **Step 1: 문서 작성** — 아래 4개 파일 생성(기존 DEPLOY.md·frontend README 내용 흡수, RTDB 아키텍처 반영).

`MC/web/README.md`:
```markdown
# web — 병동 보조 로봇 대시보드 (MediCart)

Flask(백엔드) + Next.js(프론트). Firebase RTDB를 서버측에서 읽어 SSE/REST로 제공.
로봇(intel1 ward_bridge)이 RTDB `robots/{ns}` 에 기록 → 이 백엔드가 읽어 표시.

- `backend/` Flask: fb_read(RTDB 경계)·patients·app(SSE/REST/auth)
- `frontend/` Next.js: lib/api로 백엔드 호출(RTDB 미접촉)
- `docs/` architecture·setup·deploy
- `legacy/` 더 이상 안 쓰는 Redis/xlsx 구현(참고 보존)

빠른 시작은 `docs/setup.md`.
```

`MC/web/docs/architecture.md`:
```markdown
# 아키텍처

```
로봇 PC(intel1) ward_bridge ──firebase-admin──▶ Firebase RTDB ◀──firebase-admin── web/backend Flask
                                  robots/{ns}/{state,cmd,alerts}        │ SSE/REST(쿠키 인증)
                                  patients/{pid}, rooms/                ▼
                                                                   web/frontend Next.js
```
- 프론트는 Firebase 직접 접근 안 함 → RTDB Rules 전면 잠금(admin SDK만). 인증은 Flask 쿠키.
- backend: `fb_read.py`(snapshots·리스너→SSE·cmd set·intake), `patients.py`(RTDB→프론트 형식), `app.py`(엔드포인트).
- 데이터: `robots/{ns}/state`(2Hz, scan 제외)·`cmd`·`alerts`, `patients/{pid}/{info,vitals,intake}`, `rooms/`.
```

`MC/web/docs/setup.md`:
```markdown
# 설치 / 실행

## 1. Firebase
- RTDB(asia-southeast1) + serviceAccountKey.json 발급. Rules는 `intel1/database.rules.json`(전면 잠금) 게시.

## 2. backend
```bash
cd MediCart/web/backend
python3 -m venv venv && venv/bin/pip install -r requirements.txt
cp .env.example .env   # FB_CRED/FB_DB_URL 등 채움
venv/bin/python app.py   # :5000
```

## 3. frontend
```bash
cd MediCart/web/frontend
npm install
NEXT_PUBLIC_PRIMARY_NS=robot6 npm run dev   # :3000 (또는 build/start)
```

## 4. 테스트(로봇/firebase 무관)
```bash
cd MediCart/web/backend && python3 -m pytest test/ -q
```
```

`MC/web/docs/deploy.md`:
```markdown
# 배포 (systemd + Cloudflare 터널)

- `deploy/medicart-backend.service` / `medicart-frontend.service` / `medicart-tunnel.service` 를
  `/etc/systemd/system/` 에 링크 후 `systemctl enable --now`.
- backend는 `.env`(EnvironmentFile)로 FB_CRED/FB_DB_URL 주입. 프론트는 빌드 env로 NS 설정.
- 공개 호스팅은 Cloudflare 터널(setup-tunnel.sh). 비밀번호 게이트(INTEL_PASSWORD)로 접근 통제(데모).
- 구 intel-*.service 는 legacy/ 참고.
```

- [ ] **Step 2: Commit**

```bash
cd /home/rokey/MediCart
git add web/README.md web/docs
git commit -m "docs(web): architecture·setup·deploy 통합 문서 + README"
```

---

### Task 8: 통합 검증 (사용자 실행)

**Files:** 없음(검증).

> ⚠️ Flask·프론트 구동은 **사용자 직접 실행**. 아래 명령·순서 따라 실행하고 결과 확인.

- [ ] **Step 1: backend venv + 의존성(사용자)**
```bash
cd /home/rokey/MediCart/web/backend
python3 -m venv venv && venv/bin/pip install -r requirements.txt
cp .env.example .env   # FB_CRED, FB_DB_URL 채움
```

- [ ] **Step 2: 단위테스트(컨트롤러/사용자)**
```bash
cd /home/rokey/MediCart/web/backend && python3 -m pytest test/ -q
```
Expected: 9 passed.

- [ ] **Step 3: Flask 기동 + RTDB 읽기 확인(사용자)**
```bash
cd /home/rokey/MediCart/web/backend && venv/bin/python app.py
# 다른 터미널:
curl -s -c /tmp/c.txt -X POST localhost:5000/api/login -H 'Content-Type: application/json' -d '{"password":"rokey1234"}'
curl -s -b /tmp/c.txt localhost:5000/api/amrs        # RTDB robots 스냅샷
curl -s -b /tmp/c.txt localhost:5000/api/patients    # RTDB patients
```
Expected: `/api/amrs`가 robots/{ns} 스냅샷(로봇 기동 중이면 pose/mode), `/api/patients`가 임포트된 환자 목록.

- [ ] **Step 4: 프론트 + SSE 실시간(사용자)**
```bash
cd /home/rokey/MediCart/web/frontend && npm install && NEXT_PUBLIC_PRIMARY_NS=robot6 npm run dev
```
브라우저 → 로그인 → /map 에 마커·모드 실시간(SSE), /patients·/intake 동작, /api/mode 명령→RTDB cmd→로봇 반영 확인.

> visits(외래기록)는 RTDB 미임포트라 빈 배열로 표시됨 — 필요 시 마이그레이션 툴에 visits 임포트 추가(별도).

---

## Self-Review

**1. Spec coverage:**
- Flask 유지·firebase-admin 리스너→SSE → Task 2·3 ✓
- redis_bus→fb_read, patient_data→patients → Task 2·3·4 ✓
- app.py 재결선(엔드포인트 불변) → Task 5 ✓
- RTDB Rules 잠금(이미 intel1에 커밋) → 문서 참조(Task 7) ✓
- hospital_web→MediCart/web git 이전 → Task 1 ✓
- 자기완결 .env + sync-ns 제거 → Task 6 ✓
- deploy medicart-* 리네임 → Task 6 ✓
- legacy 정리 → Task 6 ✓
- docs 통합 → Task 7 ✓
- 통합 검증(사용자) → Task 8 ✓
- 알려진 갭: visits RTDB 미임포트 → Task 4·8에 명시.

**2. Placeholder scan:** 코드·명령 완전. (frontend/tunnel service는 "동일 패턴 경로 치환"으로 기술 — 구체 경로 제시, 플레이스홀더 아님.)

**3. Type consistency:**
- `merge_snapshots(raw, sources)`·`cmd_payload(action,mode,params,ts)`·`valid_pid`(Task 2) = fb_read 결선(Task 3)·app(Task 5) 일치.
- `snapshots/telemetry_stream/alert_stream/publish_mode_cmd/save_intake/get_intake`(Task 3) = app.py 호출(Task 5) = 기존 redis_bus 시그니처 일치(드롭인).
- `patient_node_to_api/load_patients/get_patient`(Task 4) = app.py(Task 5) 일치.
- `_init()`/`_db`(Task 3) = patients.py·app rooms(Task 4·5) 공유.
- RTDB 경로 robots/{ns}/{state,cmd,alerts}·patients/{pid}·rooms = 스펙·플랜1 일치.
