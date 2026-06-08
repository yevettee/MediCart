# MediCart 자기완결화(intel1 분리) 설계

**날짜:** 2026-06-07
**대상:** `/home/rokey/MediCart` 가 `/home/rokey/rokey_ws/src/intel1` 없이 web + medicart_ws 노드를 실행할 수 있도록 런타임 의존 자산을 MediCart로 이관(복사).

## 배경 / 의존 감사 결과

MediCart 코드는 `web/`·`medicart_ws/` 안에 모두 있으나, 런타임 자산이 intel1을 가리킨다:

- **web 실의존**
  - 맵: `web/backend/.env` `MAP_PNG`/`MAP_YAML` → `intel1/common/maps/ward_map.png|yaml` (`/api/map`, `/api/map.png` → `/map` 페이지)
  - NS: `deploy/medicart-backend.service` `EnvironmentFile` → `intel1/common/robot.env`, 프론트 빌드 `NEXT_PUBLIC_PRIMARY_NS`
  - 배포: `deploy/setup-tunnel.sh`(REPO=intel1, 옛 hospital_web 경로·옛 intel-*.service — 스테일)
- **medicart_ws 실의존**: 코드 import는 0. 실행 env로 `intel1/common/robot.env`(NS·DISCOVERY_IP)·`discovery.sh`(ROS 디스커버리)만 source.
- **의존 아님**: `web/legacy/*`(미import), 환자 xlsx(마이그레이션 1회용, 이미 RTDB), docs 언급.
- **범위 밖(잔류)**: `intel1/AMR1/src/ward_bridge`(RTDB `robots/{ns}` 텔레메트리 **생산자**). web은 읽기만 하므로 대시보드 실데이터는 여전히 intel1 ward_bridge 가동 필요. 생산자 포팅은 추후.

## 결정

- **복사(이동 아님)** — intel1 ward_bridge가 `intel1/common/*`를 계속 쓰므로 MediCart로 복사한다.
- **robot.env = 독립 복사본 + 동기화 메모** — 두 파일(`intel1/common/robot.env`, `MediCart/common/robot.env`)이 존재. MediCart 쪽 헤더에 "값(ROBOT_NAMESPACE/DISCOVERY_IP/도메인) 일치 필요 — 로봇 바꾸면 양쪽 수정" 경고.

## 구조 (신규)

```
MediCart/common/
  robot.env       ← intel1/common/robot.env 복사 + 동기화 경고 헤더
  discovery.sh    ← intel1/common/discovery.sh 복사 (BASH_SOURCE 상대로 옆 robot.env source → 무수정 동작)
  maps/
    ward_map.png  ward_map.yaml  ward_map.pgm
```
(initial_poses.yaml·tour_waypoints.yaml 은 nav/tour 전용 → 제외.)

## 변경

1. **MediCart/common/ 생성** + 위 파일 복사. robot.env 헤더 주석 추가.
2. **web/backend/.env**: MAP_PNG/MAP_YAML → `/home/rokey/MediCart/common/maps/ward_map.png|yaml`.
3. **web/backend/app.py**: MAP_PNG/MAP_YAML 기본값 → MediCart/common/maps.
4. **web/deploy/medicart-backend.service**: EnvironmentFile robot.env → `/home/rokey/MediCart/common/robot.env`.
5. **web/deploy/setup-tunnel.sh**: REPO→`/home/rokey/MediCart`, 빌드 경로→`web/frontend`(+robot.env source), 설치 서비스→`deploy/medicart-*.service`로 재작성.
6. **web/docs/*·README**: intel1 경로 표기 갱신, ward_bridge는 intel1 생산자임을 명시.
7. **medicart_ws 실행 절차/문서**: `source MediCart/common/discovery.sh`로 변경(코드 변경 0).

## 검증

- `grep -rn "rokey_ws\|intel1" MediCart` → 런타임 경로 0건(문서/legacy/"ward_bridge=intel1" 주석만 잔존).
- 백엔드 기동 후 `/api/map`(resolution/origin) + `/api/map.png`(200) 이 MediCart/common/maps에서 서빙.
- `source MediCart/common/discovery.sh` → `ROBOT_NAMESPACE`/`DISCOVERY_IP`/`ROS_DISCOVERY_SERVER` 세팅 확인.
- intel1 무영향: `intel1/common/*` 그대로(복사이므로 ward_bridge·nav 계속 동작).

## 범위 밖

- ward_bridge(텔레메트리 생산자) medicart_ws 포팅 — 추후(완전 standalone 시).
- legacy/ 정리, 환자 xlsx 이동.
