# ninety 맵 + Downloads/config 정렬 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`).
>
> **설정-마이그레이션 플랜**: 파일 복제/치환 위주. 각 변경 후 "yaml 문법 + 좌표 범위 + 마커 없음" 검증. 런타임(loc/nav/goto)은 사용자 직접 구동.

**Goal:** MediCart를 main의 ninety 맵 + ninety-frame 좌표 + `~/Downloads/config` 튜닝으로 전면 정렬한다.

**Architecture:** main `medicart_ws/maps/ninety.*` 가져오기 + `~/Downloads/config/{nav2,localization,slam}.yaml` 를 MediCart 설정에 반영(좁은방 튜닝) + 좌표/초기pose/web을 ninety-frame으로 갱신 + bond_timeout 60→10.

**Tech Stack:** Nav2(amcl/costmap), slam_toolbox, Flask(fb_read), ROS2 launch.

스펙: `docs/superpowers/specs/2026-06-09-ninety-map-config-alignment-design.md`

작업 디렉토리 `/home/rokey/MediCart` (브랜치 `integration`). 검증 시 origin/main 은 이미 fetch됨.

---

## Task 1: ninety 맵 가져오기 (main → 레포)

**Files:** Create `common/maps/ninety.{pgm,png,yaml}`, `medicart_ws/maps/ninety.{pgm,png,yaml}`

- [ ] **Step 1: main에서 ninety 맵 추출 → 두 위치**

```bash
cd /home/rokey/MediCart
mkdir -p medicart_ws/maps
for ext in pgm png yaml; do
  git show "origin/main:medicart_ws/maps/ninety.$ext" > "medicart_ws/maps/ninety.$ext"
  cp "medicart_ws/maps/ninety.$ext" "common/maps/ninety.$ext"
done
```

- [ ] **Step 2: 확인 (yaml origin·존재)**

Run: `cd /home/rokey/MediCart && cat common/maps/ninety.yaml && ls -la common/maps/ninety.* medicart_ws/maps/ninety.*`
Expected: `image: ninety.pgm`, `origin: [-5.59, -4.58, 0]`, 6개 파일 존재. ward_map.* 도 그대로 있음.

- [ ] **Step 3: 커밋**

```bash
cd /home/rokey/MediCart
git add common/maps/ninety.pgm common/maps/ninety.png common/maps/ninety.yaml medicart_ws/maps/ninety.pgm medicart_ws/maps/ninety.png medicart_ws/maps/ninety.yaml
git commit -m "feat(maps): main의 ninety 맵 가져오기(common/maps + medicart_ws/maps)"
```

---

## Task 2: Nav2 설정 교체 + bond_timeout 10s

**Files:** Modify `common/nav6.yaml`, `common/navigation_bondpatched.launch.py`, `common/localization_bondpatched.launch.py`

- [ ] **Step 1: Downloads nav2.yaml → common/nav6.yaml 전체 교체**

```bash
cd /home/rokey/MediCart
cp /home/rokey/Downloads/config/nav2.yaml common/nav6.yaml
grep -nE "robot_radius|inflation_radius|cost_scaling_factor|resolution:|max_vel_x|use_sim_time" common/nav6.yaml | head
```
Expected: `robot_radius: 0.175`, `inflation_radius: 0.25`, `cost_scaling_factor: 8.0`, `resolution: 0.06`, `max_vel_x: 0.26`, `use_sim_time: False`. (기존 0.3/4.0 ad-hoc 값 사라짐)

- [ ] **Step 2: bond_timeout 60.0 → 10.0 (두 패치 launch)**

`common/navigation_bondpatched.launch.py` 와 `common/localization_bondpatched.launch.py` 에서
`{'bond_timeout': 60.0},` → `{'bond_timeout': 10.0},` 로 수정(각 파일 1곳).

```bash
cd /home/rokey/MediCart
sed -i "s/{'bond_timeout': 60.0}/{'bond_timeout': 10.0}/" common/navigation_bondpatched.launch.py common/localization_bondpatched.launch.py
grep -rn "bond_timeout" common/navigation_bondpatched.launch.py common/localization_bondpatched.launch.py
```
Expected: 두 파일 모두 `'bond_timeout': 10.0`.

- [ ] **Step 3: 문법 검증**

Run:
```bash
cd /home/rokey/MediCart
python3 -c "import yaml; yaml.safe_load(open('common/nav6.yaml')); print('nav6.yaml OK')"
python3 -m py_compile common/navigation_bondpatched.launch.py common/localization_bondpatched.launch.py && echo "launch OK"
```
Expected: `nav6.yaml OK`, `launch OK`.

- [ ] **Step 4: 커밋**

```bash
cd /home/rokey/MediCart
git add common/nav6.yaml common/navigation_bondpatched.launch.py common/localization_bondpatched.launch.py
git commit -m "feat(nav): Downloads nav2 튜닝 적용(inflation0.25/scaling8.0) + bond_timeout 10s"
```

---

## Task 3: Localization 설정 교체 + ninety dock seed + map 경로

**Files:** Modify `common/loc6_amcl.yaml`, `common/loc6.launch.py`

- [ ] **Step 1: loc6_amcl.yaml 전체 재작성 (Downloads localization + set_initial_pose)**

`common/loc6_amcl.yaml` 를 아래 내용으로 **전체 교체**:

```yaml
amcl:
  ros__parameters:
    use_sim_time: False
    alpha1: 0.2
    alpha2: 0.2
    alpha3: 0.2
    alpha4: 0.2
    alpha5: 0.2
    base_frame_id: "base_link"
    beam_skip_distance: 0.5
    beam_skip_error_threshold: 0.9
    beam_skip_threshold: 0.3
    do_beamskip: false
    global_frame_id: "map"
    lambda_short: 0.1
    laser_likelihood_max_dist: 2.0
    laser_max_range: 100.0
    laser_min_range: -1.0
    laser_model_type: "likelihood_field"
    max_beams: 60
    max_particles: 2000
    min_particles: 500
    odom_frame_id: "odom"
    pf_err: 0.05
    pf_z: 0.99
    recovery_alpha_fast: 0.0
    recovery_alpha_slow: 0.0
    resample_interval: 1
    robot_model_type: "nav2_amcl::DifferentialMotionModel"
    save_pose_rate: 0.5
    sigma_hit: 0.2
    tf_broadcast: true
    transform_tolerance: 1.0
    update_min_a: 0.2
    update_min_d: 0.25
    z_hit: 0.5
    z_max: 0.05
    z_rand: 0.5
    z_short: 0.05
    scan_topic: scan
    set_initial_pose: true
    initial_pose:
      x: -0.354229
      y: -0.118972
      z: 0.0
      yaw: -0.0042011

map_server:
  ros__parameters:
    use_sim_time: False
    yaml_filename: ""

map_saver:
  ros__parameters:
    use_sim_time: False
    save_map_timeout: 5.0
    free_thresh_default: 0.25
    occupied_thresh_default: 0.65
    map_subscribe_transient_local: True
```

- [ ] **Step 2: loc6.launch.py map 기본값 → ninety**

`common/loc6.launch.py` 의 `map` DeclareLaunchArgument default_value 수정:
- old: `default_value='/home/rokey/MediCart/common/maps/ward_map.yaml',`
- new: `default_value='/home/rokey/MediCart/common/maps/ninety.yaml',`

- [ ] **Step 3: 검증**

```bash
cd /home/rokey/MediCart
python3 -c "import yaml; d=yaml.safe_load(open('common/loc6_amcl.yaml')); ip=d['amcl']['ros__parameters']['initial_pose']; print('amcl OK', ip)"
python3 -m py_compile common/loc6.launch.py && echo "loc6.launch OK"
grep -n "ninety.yaml" common/loc6.launch.py
```
Expected: `amcl OK {'x': -0.354229, 'y': -0.118972, 'z': 0.0, 'yaw': -0.0042011}`, `loc6.launch OK`, ninety.yaml 경로 확인.

- [ ] **Step 4: 커밋**

```bash
cd /home/rokey/MediCart
git add common/loc6_amcl.yaml common/loc6.launch.py
git commit -m "feat(loc): Downloads localization 적용 + ninety dock seed(-0.354,-0.119) + map→ninety"
```

---

## Task 4: slam.yaml 추가 (매핑용)

**Files:** Create `common/slam.yaml`

- [ ] **Step 1: Downloads slam.yaml → common/slam.yaml**

```bash
cd /home/rokey/MediCart
cp /home/rokey/Downloads/config/slam.yaml common/slam.yaml
python3 -c "import yaml; yaml.safe_load(open('common/slam.yaml')); print('slam.yaml OK')"
```
Expected: `slam.yaml OK` (slam_toolbox params).

- [ ] **Step 2: 커밋**

```bash
cd /home/rokey/MediCart
git add common/slam.yaml
git commit -m "feat(slam): Downloads slam_toolbox 설정 추가(매핑용)"
```

---

## Task 5: 좌표 ninety-frame + web 맵 경로

**Files:** Modify `web/backend/fb_read.py`, `web/backend/.env`

- [ ] **Step 1: targets_seed 를 ninety 좌표로 교체**

`web/backend/fb_read.py` 의 `targets_seed()` return 딕셔너리를 아래로 교체(키 동일, 좌표만 ninety):

```python
    return {
        "t101_1": {"label": "101호 1번", "x": -4.39228, "y": -0.701007, "yaw": 2.47368},
        "t101_2": {"label": "101호 2번", "x": -4.21788, "y": -1.58667, "yaw": -2.63024},
        "t102":   {"label": "102호 호출", "x": -3.94329, "y": -3.34683, "yaw": -3.1113},
        "pharmacy": {"label": "약품실", "x": -0.302782, "y": -3.3757, "yaw": -0.0545105},
        "dock":   {"label": "Docking Station", "x": -0.354229, "y": -0.118972,
                   "yaw": -0.0042011, "dock_after": True},
    }
```

- [ ] **Step 2: web .env MAP 경로 → ninety**

`web/backend/.env`:
- `MAP_PNG=/home/rokey/MediCart/common/maps/ward_map.png` → `MAP_PNG=/home/rokey/MediCart/common/maps/ninety.png`
- `MAP_YAML=/home/rokey/MediCart/common/maps/ward_map.yaml` → `MAP_YAML=/home/rokey/MediCart/common/maps/ninety.yaml`

```bash
cd /home/rokey/MediCart
sed -i "s#common/maps/ward_map.png#common/maps/ninety.png#; s#common/maps/ward_map.yaml#common/maps/ninety.yaml#" web/backend/.env
grep -nE "MAP_PNG|MAP_YAML" web/backend/.env
```
Expected: 둘 다 ninety 경로.

- [ ] **Step 3: 검증 (문법 + 좌표가 ninety 맵 범위 내)**

```bash
cd /home/rokey/MediCart
python3 -c "import ast; ast.parse(open('web/backend/fb_read.py').read()); print('fb_read OK')"
python3 - <<'PY'
import re
# ninety 맵 범위: x∈[-5.59, 0.56], y∈[-4.58, 0.47]
ninety = {"x":(-5.59,0.56),"y":(-4.58,0.47)}
import importlib.util, sys
spec = importlib.util.spec_from_file_location("fbr","/home/rokey/MediCart/web/backend/fb_read.py")
# fb_read import는 firebase 의존 → targets_seed 만 텍스트로 파싱
import re
txt=open("/home/rokey/MediCart/web/backend/fb_read.py").read()
seg=txt[txt.index("def targets_seed"):txt.index("def get_targets")]
pts=re.findall(r'"x":\s*(-?[\d.]+),\s*"y":\s*(-?[\d.]+)', seg)
ok=all(ninety["x"][0]<=float(x)<=ninety["x"][1] and ninety["y"][0]<=float(y)<=ninety["y"][1] for x,y in pts)
print("targets:", pts)
print("모든 target ninety 범위 내:", ok)
PY
```
Expected: `fb_read OK`, 모든 target `True` (ninety 범위 안).

- [ ] **Step 4: 커밋**

```bash
cd /home/rokey/MediCart
git add web/backend/fb_read.py web/backend/.env
git commit -m "feat(web): targets/MAP를 ninety-frame으로 정렬(dashboard 실측 좌표)"
```

> 참고: `.env` 는 gitignore일 수 있음 — `git add` 가 거부되면 `.env` 는 커밋 생략(로컬 적용만)하고 fb_read.py 만 커밋.

---

## Task 6: 통합 검증 + 런타임 안내

**Files:** (검증)

- [ ] **Step 1: 전체 yaml/launch 문법 일괄 확인**

```bash
cd /home/rokey/MediCart
python3 -c "import yaml; [yaml.safe_load(open(f)) for f in ['common/nav6.yaml','common/loc6_amcl.yaml','common/slam.yaml','common/maps/ninety.yaml']]; print('yaml 전부 OK')"
python3 -m py_compile common/loc6.launch.py common/nav6.launch.py common/localization_bondpatched.launch.py common/navigation_bondpatched.launch.py && echo "launch 전부 OK"
```
Expected: `yaml 전부 OK`, `launch 전부 OK`.

- [ ] **Step 2: 정합 확인 (ninety로 일관됐나)**

```bash
cd /home/rokey/MediCart
echo "loc map:"; grep -o "ninety.yaml" common/loc6.launch.py
echo "amcl seed:"; grep -A1 "initial_pose:" common/loc6_amcl.yaml | grep x:
echo "web MAP:"; grep MAP_YAML web/backend/.env
echo "bond:"; grep -h "bond_timeout" common/*bondpatched.launch.py
echo "nav tune:"; grep -E "inflation_radius|cost_scaling_factor" common/nav6.yaml | head -2
```
Expected: ninety.yaml / seed x:-0.354229 / MAP ninety / bond 10.0 ×2 / inflation 0.25·scaling 8.0.

- [ ] **Step 3: 런타임 검증 (사용자 직접 — 로봇 구동, 어시스턴트는 명령만)**

전제: ninety 맵 실환경, robot6 + discovery 가동. 터미널에서:
```bash
source ~/.bashrc        # loc/nav 함수 ninety 반영
loc                     # ninety map 로드 + dock(-0.354,-0.119) seed → "Managed nodes are active", "Setting pose"
nav                     # "Managed nodes are active" (bond 10s)
medicart-bringup        # db_node + mission_manager
web-restart             # 웹 ninety 맵 표시
```
그다음 web에서 goto(예: 약품실) → ninety target(-0.30,-3.38)으로 실주행 확인.
Expected: amcl 수렴(스캔 드롭 없음), nav active, goto 시 맵 안 좌표로 이동. (실패 시 스캔 timestamp/클럭, bond 로그 확인)

---

## 자기검토 메모
- 스펙 §2.1~2.6 전부 태스크 매핑: 맵(T1)·nav2+bond(T2)·loc+seed+map경로(T3)·slam(T4)·좌표+web(T5)·검증(T6).
- ward_map.* 보존(폴백). 좌표 전부 ninety 범위 내 자동검증(T5 S3).
- bond 10s(사용자 지정), set_initial_pose ninety dock 유지, targets/web ninety — 모두 반영.
