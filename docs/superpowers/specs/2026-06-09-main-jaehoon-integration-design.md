# main ↔ jaehoon 통합 — 설계 (Design)

**작성일**: 2026-06-09
**대상**: `yevettee/MediCart` — `main`(원격, +34) 과 로컬 `jaehoon`(+40) 통합
**공통 조상**: `f05b679`

## 1. 목표

분기된 두 작업 라인을 충돌 없이 하나로 합친다. `main` 기반 `integration` 브랜치에 `jaehoon`을 머지하고
12개 충돌 파일을 의도 보존 원칙으로 해결한 뒤, 빌드/테스트 검증 후 `main`에 PR한다.

## 2. 분기 요약

테스트 머지(클론에서 dry-run) 결과: **자동병합 61파일 + 실제 충돌 12파일**.

| 분기 | 가져오는 주요 작업 |
| --- | --- |
| **main (+34)** | ROS 신규 패키지 `medi_interfaces`(msg/srv)·`scanner`·`simulation`(Gazebo)·dashboard robot3/6, `db_bridge` GetPrescription 서비스, **nurse tracking 구현(best.pt)**, QR scan 순찰대기, web OCR 데모(GCP+EasyOCR)·jeon 문진표/QR/display, 아키텍처 문서 |
| **jaehoon (+40)** | web **RBAC 전체**(역할/auth/미들웨어/콘솔통합/역할테마)·targets/goto·MapView·**회진 풀스크린 모드**, mission_manager **NavExecutor/goto 레인**·디스커버리 fix·robot6_bringup, db_bridge goto 워치독, 아키텍처 다이어그램 |

main-only 신규 패키지(`medi_interfaces`/`scanner`/`simulation` 등)는 **additive — 자동병합**(충돌 없음).

## 3. 충돌 12파일 해결 방침

해결 원칙: **경쟁 구현은 한쪽 채택, 그 외 중첩은 양쪽 기능 union(둘 다 보존)**.

| 파일 | 유형 | 해결 |
| --- | --- | --- |
| `web/backend/ocr.py` | 사실상 동일 | **기계적** — 코드 동일, 키 경로만 충돌. main의 `/home/jeon/...`(개인경로) 버리고 레포 경로 채택. 가능하면 `OCR_KEY` env(.env)로 일반화 |
| `medicart_ws/src/nurse_tracker/nurse_tracker/perception.py` | 경쟁구현 | **main 채택**(theirs) |
| `medicart_ws/src/nurse_tracker/nurse_tracker/tracker_node.py` | 경쟁구현 | **main 채택**(best.pt + `_on_start_tracking` 서비스) |
| `medicart_ws/src/nurse_tracker/setup.py` | 경쟁구현 | **main 채택**(best.pt 데이터 포함) |
| `web/backend/app.py` | union | jaehoon RBAC(login/me/before_request·intake_pending·역할게이트)·targets/goto 라우트 **+** main OCR데모·QR·문진표·GetPrescription 결선. 중복 라우트(예: `/api/ocr`)는 1개로 정리 |
| `web/backend/fb_read.py` | union | jaehoon targets/seed·telemetry **+** main GetPrescription/환자·병실 조회 |
| `web/frontend/lib/api.ts` | union | jaehoon getMe/login(role)/submitIntake/targets/pushMission/saveMode/follow 타입 **+** main OCR데모 헬퍼. export 중복 정리 |
| `web/frontend/app/intake/page.tsx` | union/판단 | 양쪽 문진 UI — jaehoon 역할인지(intake_pending) 기반 위에 main 문진표 필드/QR 통합. 더 완성된 쪽을 베이스로 나머지 graft |
| `web/frontend/app/ocr/page.tsx` | union/판단 | main OCR 데모 UI 베이스 + jaehoon 라우팅/역할 결선 |
| `web/frontend/components/Sidebar.tsx` | union | jaehoon 역할 메뉴 필터·등급 배지 + main 메뉴 항목 |
| `web/frontend/next.config.ts` | union | 양측 설정/리다이렉트 합치기 |
| `medicart_ws/src/mission_manager/mission_manager/mission_manager_node.py` | union(주의) | jaehoon goto 레인·NavExecutor·모드 라우팅 **+** main QR scan 순찰대기 라우팅. **허브라 가장 신중히** — 양쪽 액션/모드 등록 모두 보존 |

> 회진 풀스크린(jaehoon `lib/follow.ts`·`followActions.ts`·`FollowOverlay.tsx`·`app/page.tsx` 배너)은
> main에 없어 **자동병합**된다(충돌 아님). 단 `app/page.tsx`가 자동병합되므로 배너 마운트가 유지되는지
> 머지 후 확인.

## 4. 사전 정리 (jaehoon 미커밋 13건)

머지는 클린 트리 필요. 머지 전 처리:

| 항목 | 처리 |
| --- | --- |
| `common/nav6.launch.py`(M)·`common/nav6.yaml`(??) | jaehoon에 **커밋**(costmap robot_radius/inflation 변경 — 유효 작업) |
| `docs/superpowers/plans/2026-06-08-console-follow-mode.md`(??) | jaehoon에 **커밋**(회진 구현 계획) |
| `medicart_ws/src/nurse_tracker/**`(M, 워킹스왑)·`models/best.pt`(??) | **discard**(`git restore` / 정리) — nurse_tracker는 main 채택이라 불필요 |
| `medicart_ws/src/temp/dataset.zip`·`dataset/`(??, 75MB) | `.gitignore`에 `medicart_ws/src/temp/` 추가, **커밋 안 함** |

## 5. 통합 절차 (로컬 `/home/rokey/MediCart`)

1. 사전 정리(§4) 후 jaehoon 클린 확인.
2. `git checkout -b integration origin/main`
3. `git merge jaehoon` → 12충돌 발생.
4. §3 방침대로 해결:
   - nurse_tracker 3파일: `git checkout --theirs` (main) 후 `git add`.
   - 나머지: 수동 union 편집.
5. `git commit`(머지 커밋).
6. 검증(§6).
7. `git push origin integration` → main에 PR(리뷰).

## 6. 검증

- **web 프론트**: `cd web/frontend && npm install && npm run build && npm test`(vitest) — 빌드·단위테스트 통과.
- **web 백엔드**: `python -c "import ast,sys; [ast.parse(open(f).read()) for f in ['web/backend/app.py','web/backend/fb_read.py','web/backend/ocr.py']]"` 문법 확인 + import 점검.
- **ROS**: `colcon build`는 무거움 → 최소 변경 패키지 py 문법/임포트 확인. 전체 빌드는 사용자에게 명령 안내(서버/로봇 직접 실행 금지).
- 머지 후 핵심 기능 존재 확인: RBAC 라우트·targets·follow 배너(jaehoon) + GetPrescription·scanner·simulation·OCR데모(main) 모두 트리에 존재.

## 7. 범위 밖 / 리스크

- 런타임 통합 테스트(실로봇 E2E)는 별도 — 본 작업은 소스 통합·빌드 검증까지.
- `app.py`/`api.ts`/`mission_manager_node.py` union 시 **중복 라우트·중복 export·모드 키 충돌** 누락 주의 — 머지 후 grep로 중복 점검.
- nurse_tracker main 채택으로 jaehoon ward_model 학습 결과는 폐기(필요 시 별도 보존).
- 대용량 모델(best.pt 19MB)·dataset은 git 부담 — LFS/제외 정책은 추후.
