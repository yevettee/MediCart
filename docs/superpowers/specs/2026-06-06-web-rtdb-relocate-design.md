# web(구 hospital_web) RTDB 전환 + MediCart 이전 + 정리 — 설계

**작성일:** 2026-06-06
**상태:** 승인됨 (구현 계획 대기)
**대상:** intel1 `hospital_web` 를 RTDB 백엔드로 전환하고 `MediCart/web` 으로 이전·정리.
**관련:** intel1 `docs/superpowers/specs/2026-06-06-redis-to-rtdb-migration-design.md`(로봇측=플랜1 완료), 이 문서는 그 웹측(방향 수정판).

## 배경 / 결정

앞선 RTDB 마이그레이션에서 웹측은 "프론트가 RTDB 직접구독 + Flask 제거"로 정했으나, **번복**한다:
**Flask 백엔드를 유지**(향후 기능확장 위해)하고, Flask가 **firebase-admin(service account)로 RTDB를 서버측에서 읽어** 웹에 출력한다.
동시에 `hospital_web` 을 `MediCart/web` 으로 **이전**하고, 더 이상 안 쓰는 것은 `legacy/` 로 정리하며, 폴더구조·개발문서를 깔끔히 한다.

**확정 결정(브레인스토밍):**
1. Flask 유지 — `firebase-admin 리스너 → SSE`. `db.reference('robots').listen()` 변경을 기존 SSE로 푸시. snapshot/patients/rooms 는 `db.reference().get()`.
2. **프론트는 Firebase 직접 미접근** → Flask만 호출(rokey1234 쿠키 인증 유지). Firebase 클라 Auth/Rules 불필요 → **RTDB Rules 전면 잠금**(`.read/.write=false`; admin SDK만 접근, Rules 우회). PHI 노출/IDOR/권한상승 보안지적 일괄 해소.
3. `hospital_web` → `MediCart/web` 으로 **git 이전**(intel1에서 제거, MediCart에 신규 추적). intel1엔 로봇측(ward_bridge·ROS)만 남음.
4. legacy(redis_bus·patient_data·backend rooms.yaml·sync-ns·intel-* service)는 `web/legacy/` 보존.
5. **자기완결 설정** — `web/.env`(FB_DB_URL·FB_CRED·NS·비번). intel1/common/robot.env 의존 끊음(크로스 repo).

## 아키텍처 / 데이터 흐름

```
[Firebase RTDB] ← ward_bridge(admin, 플랜1 완료)가 robots/{ns} 기록 + 마이그레이션 툴이 patients/rooms 임포트
      │ firebase-admin (service account, Rules 우회)
[MediCart/web/backend] Flask
   - fb_read.py(신규, redis_bus.py 대체):
       · 백그라운드 리스너: db.reference("robots").listen() → 내부 큐 → SSE 제너레이터로 push(source 주입)
       · snapshots(): db.reference("robots").get() → {ns: state} 병합
       · alerts: robots/{ns}/alerts 리스너 → SSE
       · publish_mode_cmd(action,mode,params): db.reference(f"robots/{ns}/cmd").set({...,ts})  (화이트리스트 검증 유지)
       · save_intake/get_intake: db.reference(f"patients/{pid}/intake")
   - patients.py(신규, patient_data.py 대체): db.reference("patients").get() → 프론트 형식 변환
   - app.py: SSE/REST/auth(쿠키) 유지 — 소스만 Redis→RTDB. 엔드포인트 시그니처 불변.
      │ 기존 SSE/REST
[MediCart/web/frontend] Next.js — lib/api.ts로 Flask 호출 그대로(변경 최소). RTDB 미접촉.
```

## 새 폴더 구조 (`MediCart/web/`)

```
web/
  backend/
    app.py            # Flask: SSE/REST/auth (RTDB 백엔드)
    fb_read.py        # firebase-admin RTDB 읽기 + 리스너→SSE (redis_bus.py 대체)
    patients.py       # RTDB patients 읽기 (patient_data.py 대체)
    requirements.txt  # flask, firebase-admin, pyyaml (redis/pandas/openpyxl 제거)
    .env.example      # FB_CRED, FB_DB_URL, PRIMARY_NS, SECONDARY_NS, INTEL_PASSWORD, INTEL_AUTH_TOKEN
  frontend/
    app/ components/ lib/ public/ middleware.ts  (configs)   # sync-ns.cjs 제거
    CLAUDE.md         # Next.js 주의(유지)
  deploy/
    medicart-backend.service  medicart-frontend.service  medicart-tunnel.service  setup-tunnel.sh
  docs/
    architecture.md   setup.md   deploy.md      # 흩어진 md 통합·RTDB 반영
  legacy/             # 더 이상 안 쓰는 참고 보존
    redis_bus.py  patient_data.py  backend-rooms.yaml  sync-ns.cjs  intel-backend.service  intel-frontend.service  intel-tunnel.service
  README.md
```

## 구성요소

### 1. `web/backend/fb_read.py` (신규 — redis_bus.py 대체)
- **firebase-admin init**(`FB_CRED`,`FB_DB_URL`) 1회.
- **SOURCES**: `[PRIMARY_NS, SECONDARY_NS]`(env, 기본 robot6/amr2).
- `snapshots()`: `db.reference("robots").get()` → `{src: state|None}`(state에 source 주입). RTDB 미존재 src는 None.
- `telemetry_stream()` / `alert_stream()`: 백그라운드 `db.reference("robots").listen()`(또는 ns별 state/alerts 리스너)로 변경 이벤트를 `queue`에 적재 → 기존 `_sse_merge` 형태의 SSE 제너레이터로 push(source 필드 주입, keepalive 유지).
- `publish_mode_cmd(action, mode, params)`: 기존 `_ACTION_RE`/`_MODE_RE` 화이트리스트 검증 후 `db.reference(f"robots/{PRIMARY_NS}/cmd").set({"action","mode","params","ts": now_ms})`.
- `save_intake(pid, data)` / `get_intake(pid)`: `_PID_RE` 검증 후 `db.reference(f"patients/{pid}/intake")` set/get(`{data, ts}`).
- **순수 로직 분리(단위테스트)**: snapshot 병합(`merge_snapshot(raw, src)`), SSE 직렬화, pid/mode/action 검증 정규식.

### 2. `web/backend/patients.py` (신규 — patient_data.py 대체)
- `db.reference("patients").get()` → 프론트 기대 형식(api.ts `Patient`)으로 변환. id 키 주입, info/vitals/intake 병합, visits(있으면). 순수 변환(`patient_node_to_api(pid, node)`)은 단위테스트.

### 3. `web/backend/app.py` (수정)
- import `redis_bus`→`fb_read`, `patient_data`→`patients`. 엔드포인트(`/api/amrs`,`/api/stream`,`/api/alerts`,`/api/patients`,`/api/mode`,`/api/intake`,`/api/login` 등) 시그니처·인증 불변 — 데이터 소스만 교체.
- `/api/map`·`/api/map.png` 는 그대로(common/maps 파일 — 이전 후 경로 갱신 또는 web 내 복사; **설정으로 경로 지정**).

### 4. `web/backend/requirements.txt` (수정)
- `flask`, `firebase-admin`, `pyyaml`. (`redis`, `pandas`, `openpyxl` 제거.)

### 5. `web/.env.example` (신규) + frontend 설정
- `.env.example`: `FB_CRED`,`FB_DB_URL`,`PRIMARY_NS=robot6`,`SECONDARY_NS=amr2`,`INTEL_PASSWORD`,`INTEL_AUTH_TOKEN`,`MAP_PNG`,`MAP_YAML`.
- frontend: `sync-ns.cjs`(robot.env 읽던 prebuild) 제거 → `NEXT_PUBLIC_PRIMARY_NS` 를 web/.env/빌드 env로 직접. `lib/config.ts` 기본값만 유지.

### 6. `web/deploy/` (수정)
- `intel-*.service` → `medicart-*.service`(WorkingDirectory/ExecStart 경로를 MediCart/web 으로, EnvironmentFile=web/.env). 구본은 legacy/.

### 7. `web/docs/` (신규 — 통합)
- `architecture.md`(RTDB 흐름·컴포넌트), `setup.md`(Firebase·env·실행 명령), `deploy.md`(systemd·tunnel). 기존 `DEPLOY.md`+frontend README/AGENTS 내용 흡수.

### 8. `web/legacy/` (이동)
- `redis_bus.py`, `patient_data.py`, `backend/rooms.yaml`(→`backend-rooms.yaml`), `frontend/scripts/sync-ns.cjs`, `deploy/intel-*.service`. 삭제 아닌 보존(참고).

## 검증
- **단위(RTDB 무관, pytest):** `fb_read.merge_snapshot`·pid/mode/action 검증·cmd 페이로드 빌드, `patients.patient_node_to_api` 변환.
- **통합(사용자 실행 — 노드/서버 직접 실행 금지, 명령·순서 제시):** Flask 기동(`FB_CRED`/`FB_DB_URL` 설정) → `/api/amrs`가 RTDB 스냅샷 반환, `/api/stream`이 RTDB 변경을 SSE로 푸시, 프론트가 실시간 마커·모드·환자·문진 표시, `/api/mode`→RTDB cmd→로봇 반영.

## 재사용 / 영향
| 필요 | 위치 |
|---|---|
| SSE 병합·검증 정규식 | 기존 `redis_bus.py`(로직 이식, 소스만 RTDB) |
| 엔드포인트·인증·프론트 | 기존 `app.py`/Next.js(시그니처 불변) |
| RTDB 스키마 | 플랜1 트리(robots/patients/rooms) |
| firebase-admin | 로봇측 `fb_bus`와 동일 SDK |

**변경 영향 점검:** intel1에선 `hospital_web` 제거(로봇측 무관). MediCart에 `web/` 신규. 프론트 api.ts 호출 시그니처 불변이라 페이지 변경 최소(NS 설정 경로만). RTDB Rules 잠금은 admin 전용 접근과 정합(ward_bridge·Flask·마이그레이션 무영향). map 파일 경로는 env로 web 자기완결화.

## 범위 밖
- 프론트 UI 재디자인, 신규 페이지.
- MediCart 자체 ROS 패키지(dashboard 등)와의 통합 — 본 건은 intel1 fleet을 RTDB로 표시하는 web 이전.
- per-user 역할 인증(단일 쿠키 유지). RTDB 직접-클라 접근(없음).
- 실시간 LiDAR scan 웹 표시(플랜1에서 RTDB 제외 — 별도).
