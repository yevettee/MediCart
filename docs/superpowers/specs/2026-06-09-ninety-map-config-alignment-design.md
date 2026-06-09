# ninety 맵 + Downloads/config 정렬 — 설계 (Design)

**작성일**: 2026-06-09
**대상**: MediCart 전체를 **main의 ninety 맵 + ninety-frame 좌표 + `~/Downloads/config` 튜닝**으로 정렬

## 1. 목표

현재 MediCart는 `common/maps/ward_map`(origin [-14.3,-10.4]) + ward-frame 좌표(targets -12,-9, 초기pose -8.356,-6.478)로 설정돼 있다. main의 실운영 기준인 **ninety 맵**(origin [-5.59,-4.58], 123×101, x∈[-5.6,0.6]·y∈[-4.6,0.5])과 **ninety-frame 좌표**(dashboard DEFAULT_TARGETS), 그리고 `~/Downloads/config`의 튜닝 설정으로 전체를 맞춘다.

## 2. 변경 항목

### 2.1 맵 적용 (main → 레포)
- `git show origin/main:medicart_ws/maps/ninety.{pgm,png,yaml}` 을 가져와:
  - `common/maps/ninety.{pgm,png,yaml}` (loc/web 참조 위치)
  - `medicart_ws/maps/ninety.{pgm,png,yaml}` (main 정본 위치 — 정합)
- `ward_map.*` 는 보존(삭제 안 함, 폴백).

### 2.2 설정 적용 (~/Downloads/config → MediCart)
| Downloads | → 적용 | 비고 |
| --- | --- | --- |
| `nav2.yaml` | `common/nav6.yaml` **전체 교체** | 좁은방 튜닝: `robot_radius 0.175`, `inflation_radius 0.25`, `cost_scaling_factor 8.0`, `resolution 0.06`, `max_vel_x 0.26`, `use_sim_time False`. (내 기존 0.3/4.0 ad-hoc 값 폐기) |
| `localization.yaml` | `common/loc6_amcl.yaml` **베이스 교체** + `set_initial_pose` 추가 | Downloads amcl(use_sim_time False) 그대로 + 아래 초기pose 블록 append |
| `slam.yaml` | `common/slam.yaml` **신규 추가** | 매핑용(slam_toolbox). 정상 운영(amcl)엔 미사용, 보관/매핑 시 사용 |

### 2.3 초기 pose (set_initial_pose, ninety dock)
`common/loc6_amcl.yaml` 의 amcl 섹션에 추가:
```yaml
    set_initial_pose: true
    initial_pose:
      x: -0.354229
      y: -0.118972
      z: 0.0
      yaw: -0.0042011
```
(= main dashboard "Docking Station" 좌표. loc 기동 시 ninety 도크 위치로 자동 seed)

### 2.4 좌표 — ninety-frame (main dashboard DEFAULT_TARGETS)
`web/backend/fb_read.py` `targets_seed()` 값을 ninety로 교체:
```python
"t101_1":  {"label": "101호 1번", "x": -4.39228,  "y": -0.701007, "yaw": 2.47368},
"t101_2":  {"label": "101호 2번", "x": -4.21788,  "y": -1.58667,  "yaw": -2.63024},
"t102":    {"label": "102호 호출", "x": -3.94329,  "y": -3.34683,  "yaw": -3.1113},
"pharmacy":{"label": "약품실",    "x": -0.302782, "y": -3.3757,   "yaw": -0.0545105},
"dock":    {"label": "Docking Station", "x": -0.354229, "y": -0.118972, "yaw": -0.0042011, "dock_after": True},
```

### 2.5 loc/web 맵 경로
- `common/loc6.launch.py` `map` 기본값 → `/home/rokey/MediCart/common/maps/ninety.yaml`
- `web/backend/.env` `MAP_YAML` → `.../common/maps/ninety.yaml`, `MAP_PNG` → `.../common/maps/ninety.png`

### 2.6 bond_timeout (유지, 10s로 조정)
- `common/localization_bondpatched.launch.py` · `common/navigation_bondpatched.launch.py` 의 `bond_timeout: 60.0` → **`10.0`** (사용자 지정). 디스커버리 혼잡 대응은 유지하되 4s→10s 여유.

## 3. 유지/비변경
- `ward_map.*`(폴백), `nav6.launch.py`·`loc6.launch.py` 구조, `medicart-bringup`·`loc`·`nav` 함수(경로만 ninety 반영).
- mode_arbiter safety_gate(lidar 0.3/depth 0.2)·mission_manager 로직은 무관.

## 4. 검증
- yaml 문법(`python3 -c yaml.safe_load`), launch py_compile.
- ninety 좌표가 맵 범위 내인지 확인(모든 target x∈[-5.6,0.6], y∈[-4.6,0.5]).
- (런타임, 사용자) `loc` → ninety map 로드 + dock(-0.354,-0.119) seed + amcl 수렴 → `nav` → web goto(ninety target)로 실주행. 서버/로봇 직접구동 금지(명령 안내).

## 5. 영향도
- loc/nav/web/goto 좌표계가 ward→ninety로 **전면 전환**. ninety 맵을 쓰는 실환경에서만 정상. ward 환경이면 되돌려야 함(ward_map 보존).
- 내 기존 nav6.yaml ad-hoc 튜닝(0.3/4.0)은 Downloads 값(0.25/8.0)으로 대체됨.

## 6. 파일 변경 요약
- 신규: `common/maps/ninety.{pgm,png,yaml}`, `medicart_ws/maps/ninety.{pgm,png,yaml}`, `common/slam.yaml`
- 교체: `common/nav6.yaml`(←Downloads nav2), `common/loc6_amcl.yaml`(←Downloads localization+seed)
- 수정: `common/loc6.launch.py`(map 경로), `web/backend/.env`(MAP_*), `web/backend/fb_read.py`(targets_seed), `common/localization_bondpatched.launch.py`·`common/navigation_bondpatched.launch.py`(bond_timeout 10)
