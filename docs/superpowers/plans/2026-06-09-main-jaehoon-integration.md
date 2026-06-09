# main ↔ jaehoon 통합 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **머지 플랜 특성**: 충돌 해결은 실제 hunk 기반이라 verbatim 코드 대신 **파일별 해결 전략 + 검증 게이트**로 기술한다. 각 충돌 해결 후 반드시 "충돌 마커 0개 + 빌드/문법 통과"를 확인한다.

**Goal:** `origin/main`에 로컬 `jaehoon`(+40)을 머지해 두 작업 라인을 하나로 통합하고, 충돌 12파일을 의도 보존 원칙(ocr 기계적 / nurse_tracker=main / 나머지=union)으로 해결한 뒤 빌드·테스트 검증하고 PR한다.

**Architecture:** `git checkout -b integration origin/main` → `git merge jaehoon` → 자동병합 61 + 충돌 12 수동 해결. 해결 방침: nurse_tracker=`--ours`(main), ocr.py=`--theirs`(jaehoon, 코드 동일·경로만), 나머지 8=양측 기능 union.

**Tech Stack:** git merge, Next.js(npm build+vitest), Flask(python), ROS2(ament — 최소 문법 검증).

스펙: `docs/superpowers/specs/2026-06-09-main-jaehoon-integration-design.md`

> **머지 방향 주의**: 브랜치 `integration`(=main)에서 `git merge jaehoon` 이므로 **`--ours`=main, `--theirs`=jaehoon**.

---

## Task 1: 사전 정리 (jaehoon 클린 트리)

**Files:** `common/nav6.launch.py`, `common/nav6.yaml`, `docs/superpowers/plans/2026-06-08-console-follow-mode.md`, `.gitignore`, `medicart_ws/src/nurse_tracker/**`(working swap 폐기)

- [ ] **Step 1: 현재 상태 확인**

Run: `cd /home/rokey/MediCart && git branch --show-current && git status --short`
Expected: 브랜치 `jaehoon`, 미커밋 약 13건(nav6, nurse_tracker M, follow plan ??, temp/dataset ??, best.pt ??).

- [ ] **Step 2: nurse_tracker 워킹 스왑 폐기 (main 채택 예정이라 불필요)**

```bash
cd /home/rokey/MediCart
git restore medicart_ws/src/nurse_tracker
git clean -fd medicart_ws/src/nurse_tracker/models   # 워킹트리 best.pt(미추적) 제거
git status --short medicart_ws/src/nurse_tracker
```
Expected: nurse_tracker 관련 변경 0 (jaehoon 커밋본 ward_model 상태로 복원).

- [ ] **Step 3: temp/dataset gitignore (대용량 75MB 제외)**

`/home/rokey/MediCart/.gitignore` 끝에 다음 한 줄 추가(이미 있으면 생략):
```
medicart_ws/src/temp/
```

- [ ] **Step 4: 유효 작업 커밋 (nav6 costmap + follow plan + gitignore)**

```bash
cd /home/rokey/MediCart
git add .gitignore common/nav6.launch.py common/nav6.yaml docs/superpowers/plans/2026-06-08-console-follow-mode.md
git commit -m "chore(jaehoon): nav6 costmap params + follow 계획 + temp gitignore"
```

- [ ] **Step 5: 클린 트리 검증**

Run: `cd /home/rokey/MediCart && git status --short`
Expected: 출력 없음(빈 줄) 또는 gitignore된 `medicart_ws/src/temp/`만 미표시. 커밋 안 된 추적 변경 0.

---

## Task 2: integration 브랜치 생성 + 머지 (충돌 12 확인)

**Files:** (git 상태만 — 파일 편집 없음)

- [ ] **Step 1: 최신 origin/main 확인**

```bash
cd /home/rokey/MediCart
git fetch origin main
git log --oneline -1 origin/main
```
Expected: `d995330` (또는 더 최신) — 머지 직전 최신.

- [ ] **Step 2: integration 브랜치 생성(origin/main 기준)**

```bash
cd /home/rokey/MediCart
git checkout -b integration origin/main
git branch --show-current
```
Expected: `integration`.

- [ ] **Step 3: jaehoon 머지 (충돌 발생 예상)**

```bash
cd /home/rokey/MediCart
git merge --no-ff jaehoon
```
Expected: `Automatic merge failed; fix conflicts and then commit the result.` (rc=1).

- [ ] **Step 4: 충돌 목록 확인 (12개)**

Run: `cd /home/rokey/MediCart && git diff --name-only --diff-filter=U`
Expected (정확히 이 12개):
```
medicart_ws/src/mission_manager/mission_manager/mission_manager_node.py
medicart_ws/src/nurse_tracker/nurse_tracker/perception.py
medicart_ws/src/nurse_tracker/nurse_tracker/tracker_node.py
medicart_ws/src/nurse_tracker/setup.py
web/backend/app.py
web/backend/fb_read.py
web/backend/ocr.py
web/frontend/app/intake/page.tsx
web/frontend/app/ocr/page.tsx
web/frontend/components/Sidebar.tsx
web/frontend/lib/api.ts
web/frontend/next.config.ts
```
목록이 다르면 멈추고 보고(스펙 기준과 불일치).

---

## Task 3: 기계적·단일채택 해결 (ocr.py + nurse_tracker ×3)

**Files:** `web/backend/ocr.py`, `medicart_ws/src/nurse_tracker/nurse_tracker/perception.py`, `.../tracker_node.py`, `medicart_ws/src/nurse_tracker/setup.py`, `.../models/`

- [ ] **Step 1: nurse_tracker = main 채택(`--ours`)**

```bash
cd /home/rokey/MediCart
git checkout --ours medicart_ws/src/nurse_tracker/nurse_tracker/perception.py \
                     medicart_ws/src/nurse_tracker/nurse_tracker/tracker_node.py \
                     medicart_ws/src/nurse_tracker/setup.py
git add medicart_ws/src/nurse_tracker/nurse_tracker/perception.py \
        medicart_ws/src/nurse_tracker/nurse_tracker/tracker_node.py \
        medicart_ws/src/nurse_tracker/setup.py
```

- [ ] **Step 2: jaehoon ward_model.pt 제거(main은 best.pt 사용)**

```bash
cd /home/rokey/MediCart
git rm -f --ignore-unmatch medicart_ws/src/nurse_tracker/models/ward_model.pt
ls medicart_ws/src/nurse_tracker/models/
```
Expected: `best.pt`, `.gitkeep` 존재, `ward_model.pt` 없음.

- [ ] **Step 3: ocr.py = jaehoon 채택(`--theirs`, 코드 동일·레포 경로)**

```bash
cd /home/rokey/MediCart
git checkout --theirs web/backend/ocr.py
git add web/backend/ocr.py
grep -n "_DEFAULT_KEY" web/backend/ocr.py
```
Expected: 경로가 `/home/rokey/MediCart/medicart_ws/src/ocr_detector/credentials/gcp_vision_key.json` (jeon 개인경로 아님).

- [ ] **Step 4: 4파일 충돌 해소 확인**

Run: `cd /home/rokey/MediCart && git diff --name-only --diff-filter=U`
Expected: nurse_tracker 3파일·ocr.py가 목록에서 사라짐(남은 충돌 8개: app.py, fb_read.py, api.ts, intake/page, ocr/page, Sidebar, next.config, mission_manager_node).

---

## Task 4: union 해결 — 웹 백엔드 (app.py, fb_read.py)

**Files:** `web/backend/app.py`, `web/backend/fb_read.py`

- [ ] **Step 1: app.py union 해결**

`web/backend/app.py`의 각 `<<<<<<< / ======= / >>>>>>>` 블록을 **양측 기능 보존**으로 편집:
- **베이스 = jaehoon(theirs)**: RBAC 인증(`before_request` 역할 게이트, `login`이 role 반환, `/api/me`), `/api/intake`(비로그인 환자 intake_pending) 유지.
- **main(ours)에서 graft**: `/api/display/current` (GET·POST) 라우트 추가, GetPrescription/OCR데모 관련 결선이 있으면 포함.
- `/api/ocr` 는 양측 모두 존재 → **1개로 통합**(ocr.py가 GCP Vision이므로 GCP 호출 바디 유지).
- 라우트 데코레이터 중복 금지(같은 `@app.<method>("/path")` 2개면 1개로).

검증:
```bash
cd /home/rokey/MediCart
grep -c "<<<<<<<\|=======\|>>>>>>>" web/backend/app.py   # 0 이어야 함
python3 -c "import ast; ast.parse(open('web/backend/app.py').read()); print('app.py OK')"
grep -E "@app\.(get|post|put)\(" web/backend/app.py | sort | uniq -d   # 중복 라우트(출력 없어야 함)
```
Expected: 마커 0, `app.py OK`, 중복 라우트 출력 없음. `/api/intake`(jaehoon)와 `/api/display/current`(main) 둘 다 존재.
```bash
grep -cE "/api/intake|/api/display/current" web/backend/app.py   # 둘 다 있어야 함(>=2 매치)
git add web/backend/app.py
```

- [ ] **Step 2: fb_read.py union 해결**

`web/backend/fb_read.py` 충돌 블록 편집 — 양측 함수 모두 보존:
- **jaehoon**: `targets_seed`/`get_targets`/`seed_targets`, telemetry/SSE 관련.
- **main**: `get_prescription`/환자·병실 조회(GetPrescription 백엔드), display 관련 read/write.
- 동일 함수가 양측에 다르게 있으면 동작 상위(더 완성된) 쪽 채택 후 다른 쪽 고유 함수 추가.

검증:
```bash
cd /home/rokey/MediCart
grep -c "<<<<<<<\|=======\|>>>>>>>" web/backend/fb_read.py   # 0
python3 -c "import ast; ast.parse(open('web/backend/fb_read.py').read()); print('fb_read.py OK')"
grep -E "^def (targets_seed|get_targets|seed_targets|publish_mode_cmd)" web/backend/fb_read.py   # jaehoon 함수 존재
git add web/backend/fb_read.py
```
Expected: 마커 0, OK, jaehoon 타겟 함수 존재.

- [ ] **Step 3: staged 유지 (중간 커밋 안 함)**

머지 진행 중이므로 별도 커밋하지 않는다. 해결한 파일은 `git add`로 staged 상태만 유지하고,
모든 충돌 해결 완료 후 **Task 7에서 단일 머지 커밋**으로 마무리한다.
Run: `cd /home/rokey/MediCart && git diff --cached --name-only | grep -E "app.py|fb_read.py"`
Expected: 두 파일이 staged 목록에 있음.

---

## Task 5: union 해결 — 웹 프론트 (api.ts, intake, ocr page, Sidebar, next.config)

**Files:** `web/frontend/lib/api.ts`, `web/frontend/app/intake/page.tsx`, `web/frontend/app/ocr/page.tsx`, `web/frontend/components/Sidebar.tsx`, `web/frontend/next.config.ts`

- [ ] **Step 1: api.ts union 해결**

충돌 블록을 양측 export 모두 보존으로 편집:
- **jaehoon**: `login(role)`/`getMe`/`submitIntake`/`Role` import, `getTargets`/`GotoTarget`/`pushMission`/`saveMode`/`AmrSnapshot`(pose/dock), 회진 관련 타입.
- **main**: OCR 데모 헬퍼/`/api/display` 호출/GetPrescription 호출 등 고유 export.
- 동일 이름 export 충돌 시 시그니처가 더 풍부한 쪽(대개 jaehoon RBAC 버전) 채택.

검증:
```bash
cd /home/rokey/MediCart
grep -c "<<<<<<<\|=======\|>>>>>>>" web/frontend/lib/api.ts   # 0
grep -E "export (async )?(function|const) " web/frontend/lib/api.ts | grep -oE "(function|const) [a-zA-Z]+" | sort | uniq -d   # 중복 export(없어야)
git add web/frontend/lib/api.ts
```
Expected: 마커 0, 중복 export 없음.

- [ ] **Step 2: intake/page.tsx 해결 (union/판단)**

`web/frontend/app/intake/page.tsx` — 양측 문진 UI. jaehoon 역할인지(비로그인 환자 → intake_pending) 흐름을 베이스로, main의 문진표 필드/섹션·QR 연동을 graft. 둘 중 더 완성된 폼을 베이스로 삼고 나머지 기능 이식.
검증:
```bash
grep -c "<<<<<<<\|=======\|>>>>>>>" web/frontend/app/intake/page.tsx   # 0
git add web/frontend/app/intake/page.tsx
```

- [ ] **Step 3: ocr/page.tsx 해결 (union/판단)**

`web/frontend/app/ocr/page.tsx` — main OCR 데모 UI(카메라/업로드 실시간)를 베이스로, jaehoon 라우팅/역할/`api.ts` 결선 적용.
검증:
```bash
grep -c "<<<<<<<\|=======\|>>>>>>>" web/frontend/app/ocr/page.tsx   # 0
git add web/frontend/app/ocr/page.tsx
```

- [ ] **Step 4: Sidebar.tsx union 해결**

jaehoon 역할 메뉴 필터·등급 배지·로그인/로그아웃 + main 추가 메뉴 항목(예: 디스플레이/순찰 관련)을 합침. 메뉴 목록 union.
검증:
```bash
grep -c "<<<<<<<\|=======\|>>>>>>>" web/frontend/components/Sidebar.tsx   # 0
git add web/frontend/components/Sidebar.tsx
```

- [ ] **Step 5: next.config.ts union 해결**

양측 config(리다이렉트·이미지·env 등) 키 합치기. jaehoon 콘솔 리다이렉트 + main 설정 모두 보존.
검증:
```bash
grep -c "<<<<<<<\|=======\|>>>>>>>" web/frontend/next.config.ts   # 0
git add web/frontend/next.config.ts
```

---

## Task 6: union 해결 — ROS 허브 (mission_manager_node.py)

**Files:** `medicart_ws/src/mission_manager/mission_manager/mission_manager_node.py`

가장 신중히 — mission 라우팅 허브. 양측 모드/액션 등록·라우팅을 모두 보존.

- [ ] **Step 1: 충돌 블록 union 편집**

- **jaehoon**: goto 라우팅 레인(`_handle_goto`), NavExecutor 결선, 디스커버리/timeout 관련, MODE_REGISTRY에 추가한 모드.
- **main**: QR scan 순찰대기 라우팅, nurse tracking/start_tracking 연동, GetPrescription 호출 등.
- `MODE_REGISTRY`/`SYSTEM_ACTIONS`/`MODE_ACTIONS` 등 딕셔너리·라우팅 분기는 **양측 항목 합집합**. `_on_mission_request` 의 action 분기에 양측 케이스 모두 포함.

- [ ] **Step 2: 검증**

```bash
cd /home/rokey/MediCart
grep -c "<<<<<<<\|=======\|>>>>>>>" medicart_ws/src/mission_manager/mission_manager/mission_manager_node.py   # 0
python3 -c "import ast; ast.parse(open('medicart_ws/src/mission_manager/mission_manager/mission_manager_node.py').read()); print('mm_node OK')"
git add medicart_ws/src/mission_manager/mission_manager/mission_manager_node.py
```
Expected: 마커 0, `mm_node OK`.

- [ ] **Step 3: 전체 충돌 해소 확인**

Run: `cd /home/rokey/MediCart && git diff --name-only --diff-filter=U`
Expected: **출력 없음**(충돌 0).

---

## Task 7: 머지 커밋 + 검증 + PR

**Files:** (검증·커밋)

- [ ] **Step 1: 머지 커밋**

```bash
cd /home/rokey/MediCart
git commit --no-edit
git log --oneline -1
```
Expected: 머지 커밋 생성(`Merge ... jaehoon ...`).

- [ ] **Step 2: 잔여 충돌 마커 전역 점검**

```bash
cd /home/rokey/MediCart
grep -rn "<<<<<<<\|>>>>>>>" --include="*.py" --include="*.ts" --include="*.tsx" web medicart_ws | grep -v node_modules
```
Expected: 출력 없음.

- [ ] **Step 3: 웹 프론트 빌드 + 단위테스트**

```bash
cd /home/rokey/MediCart/web/frontend
npm install
NEXT_PUBLIC_API_BASE="" NEXT_PUBLIC_PRIMARY_NS=robot6 NEXT_PUBLIC_SECONDARY_NS=robot3 npm run build
npm test
```
Expected: 빌드 성공(에러 0), vitest 통과(`follow.test.ts` 등). 실패 시 해당 충돌 파일 재검토.

- [ ] **Step 4: 백엔드 py 문법 점검**

```bash
cd /home/rokey/MediCart
python3 -c "import ast,glob; [ast.parse(open(f).read()) for f in glob.glob('web/backend/*.py')]; print('backend py OK')"
```
Expected: `backend py OK`.

- [ ] **Step 5: ROS 변경 패키지 py 문법 점검 (colcon 미실행)**

```bash
cd /home/rokey/MediCart
python3 -c "import ast,glob; [ast.parse(open(f).read()) for f in glob.glob('medicart_ws/src/mission_manager/mission_manager/*.py')+glob.glob('medicart_ws/src/nurse_tracker/nurse_tracker/*.py')+glob.glob('medicart_ws/src/db_bridge/db_bridge/*.py')]; print('ros py OK')"
```
Expected: `ros py OK`. (전체 `colcon build`는 로봇 환경에서 사용자 실행 — 명령만 안내: `cd ~/MediCart/medicart_ws && colcon build`.)

- [ ] **Step 6: 통합 결과 존재 확인 (양측 핵심 기능)**

```bash
cd /home/rokey/MediCart
ls medicart_ws/src/medi_interfaces medicart_ws/src/scanner medicart_ws/src/simulation   # main 신규 패키지 존재
test -f web/frontend/components/FollowOverlay.tsx && echo "follow OK"                      # jaehoon 회진 존재
grep -q "round 모드 시작\|회진" web/frontend/app/page.tsx && echo "banner OK" || echo "banner 확인필요"
grep -q "get_prescription\|GetPrescription" medicart_ws/src/db_bridge/db_bridge/*.py && echo "prescription OK"
```
Expected: main 패키지 3개 존재, `follow OK`, banner 확인, `prescription OK`.

- [ ] **Step 7: push + PR**

```bash
cd /home/rokey/MediCart
git push origin integration
```
그다음 PR 생성(웹 또는 gh): `gh pr create --base main --head integration --title "통합: jaehoon(RBAC·goto·회진) ↔ main(OCR·scanner·simulation·GetPrescription)" --body "충돌 12 해결: nurse_tracker=main, ocr 경로정리, 나머지 union. 검증: web build+vitest, py 문법."`
Expected: PR 생성. (gh 인증 없으면 push까지만 하고 PR은 사용자에게 안내.)

---

## 자기검토 메모

- 충돌 12개 전부 태스크에 매핑: Task3(ocr+nurse_tracker×3), Task4(app·fb_read), Task5(api·intake·ocr page·Sidebar·next.config), Task6(mm_node).
- 머지 방향 일관: `--ours`=main(nurse_tracker), `--theirs`=jaehoon(ocr.py).
- 회진 풀스크린은 자동병합 → Task7 Step6에서 존재 확인.
- 검증: 마커 전역점검 + web build/vitest + py 문법 + 양측 기능 존재. colcon 전체빌드는 사용자.
