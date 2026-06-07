# obstacle_detector (지면 평탄도) 구현 플랜

> **For agentic workers:** REQUIRED SUB-SKILL: subagent-driven-development / executing-plans. 체크박스 추적.

**Goal:** OAK-D depth 하단 ROI → 평면적합+거칠기 → 평탄/울퉁불퉁 판단(standalone, 로그+PointCloud2+status).

**Architecture:** 순수 분석(fit_plane·roughness·classify) 단위테스트. cloud3d cloud_projection 재사용(depth→3D ROI). obstacle_node가 ROS 결선. 3DGS 미사용.

**스펙:** `docs/superpowers/specs/2026-06-07-obstacle-detector-ground-design.md`

## 파일 구조
- 생성 `obstacle_detector/obstacle_detector/cloud_projection.py` — cloud3d 복사 + project_depth_roi
- 생성 `obstacle_detector/obstacle_detector/ground_analysis.py` — fit_plane·roughness·classify(순수)
- 수정 `obstacle_detector/obstacle_detector/obstacle_node.py` — ROS 결선
- 삭제 `height_filter.py`(stub)
- 생성 `test/test_ground_analysis.py`

---

### Task 1: ground_analysis.py (순수) + 테스트  [TDD]

- [ ] **Step 1: 실패 테스트** `test/test_ground_analysis.py`
```python
"""ground_analysis 순수 테스트. 실행: cd obstacle_detector && PYTHONPATH=. python3 -m pytest test/test_ground_analysis.py -q"""
import numpy as np
from obstacle_detector.ground_analysis import fit_plane, roughness, classify


def _grid(z_func, n=40):
    xs, ys = np.meshgrid(np.linspace(-0.5, 0.5, n), np.linspace(0.3, 1.0, n))
    zs = z_func(xs, ys)
    return np.stack([xs.ravel(), ys.ravel(), zs.ravel()], axis=1).astype(np.float32)


def test_flat_plane_low_roughness():
    rng = np.random.default_rng(0)
    pts = _grid(lambda x, y: 1.0 + 0.001 * rng.standard_normal(x.shape))  # 평면 + 1mm 노이즈
    plane = fit_plane(pts)
    m = roughness(pts, plane)
    assert m["std"] < 0.01
    assert classify(m, std_thresh=0.02, min_points=200) is True


def test_bumpy_high_roughness():
    rng = np.random.default_rng(1)
    pts = _grid(lambda x, y: 1.0 + 0.05 * rng.standard_normal(x.shape))   # ±5cm 범프
    m = roughness(pts, fit_plane(pts))
    assert m["std"] > 0.02
    assert classify(m, std_thresh=0.02, min_points=200) is False


def test_few_points_unknown():
    pts = np.zeros((10, 3), np.float32)
    assert classify(roughness(pts, fit_plane(pts)) if fit_plane(pts) else {"n": 10},
                    min_points=200) is None


def test_fit_plane_none_when_too_few():
    assert fit_plane(np.zeros((2, 3), np.float32)) is None
```

- [ ] **Step 2: 실패 확인** `cd obstacle_detector && PYTHONPATH=. python3 -m pytest test/test_ground_analysis.py -q` → FAIL

- [ ] **Step 3: 구현** `ground_analysis.py`
```python
"""ground_analysis — 지면 평탄도 순수 로직(ROS 무관). 평면적합 + 거칠기 + 분류."""
import numpy as np


def fit_plane(points):
    """points Nx3 → (normal(3,), centroid(3,)). SVD 최소특이벡터=법선. <3점이면 None."""
    if points is None or len(points) < 3:
        return None
    c = points.mean(axis=0)
    _, _, vt = np.linalg.svd(points - c, full_matrices=False)
    normal = vt[-1]
    return normal, c


def _signed_dist(points, plane):
    normal, c = plane
    return (points - c) @ normal


def roughness(points, plane, inlier_tol=0.02):
    """점-평면 부호거리 통계. plane None 이면 n=0."""
    if plane is None or points is None or len(points) == 0:
        return {"std": 0.0, "max_dev": 0.0, "inlier_ratio": 0.0, "n": 0}
    d = _signed_dist(points, plane)
    ad = np.abs(d)
    return {"std": float(np.std(d)), "max_dev": float(ad.max()),
            "inlier_ratio": float(np.mean(ad <= inlier_tol)), "n": int(len(d))}


def classify(metrics, std_thresh=0.02, min_points=200):
    """평탄 여부. 점 부족(n<min_points)이면 None(미상), 아니면 std≤thresh."""
    if metrics["n"] < min_points:
        return None
    return metrics["std"] <= std_thresh
```

- [ ] **Step 4: 통과** `PYTHONPATH=. python3 -m pytest test/test_ground_analysis.py -q` → 4 passed

---

### Task 2: cloud_projection.py (복사 + project_depth_roi)

- [ ] **Step 1: 복사** `cp /home/rokey/rokey_ws/src/intel1/AMR1/src/cloud3d/cloud3d/cloud_projection.py /home/rokey/MediCart/medicart_ws/src/obstacle_detector/obstacle_detector/cloud_projection.py`
- [ ] **Step 2: project_depth_roi 추가**(파일 끝에)
```python
def project_depth_roi(depth_mm, fx, fy, cx, cy, roi, min_depth=0.3, max_depth=6.0):
    """16UC1 depth(mm)+intrinsics+roi(x1,y1,x2,y2) → 점군 Nx3(광학프레임 m). color 불요."""
    import numpy as np
    h, w = depth_mm.shape[:2]
    x1, y1, x2, y2 = (int(max(0, roi[0])), int(max(0, roi[1])),
                      int(min(w, roi[2])), int(min(h, roi[3])))
    us, vs = np.meshgrid(np.arange(x1, x2), np.arange(y1, y2))
    z = depth_mm[y1:y2, x1:x2].astype(np.float32) / 1000.0
    m = (z >= min_depth) & (z <= max_depth)
    u, v, z = us[m], vs[m], z[m]
    x = (u - cx) * z / fx
    y = (v - cy) * z / fy
    return np.stack([x, y, z], axis=1).astype(np.float32)
```

---

### Task 3: obstacle_node.py + stub 삭제

- [ ] **Step 1: 삭제** `rm -f obstacle_detector/obstacle_detector/height_filter.py`
- [ ] **Step 2: 구현** `obstacle_node.py` (스펙의 파라미터·ROI·발행/로그). PointCloud2 는 `sensor_msgs_py.point_cloud2` 사용, 색=|편차|/inlier_tol 클램프 초록→빨강.
- [ ] **Step 3: 빌드·import** `colcon build --packages-select obstacle_detector --symlink-install && python3 -c "import obstacle_detector.obstacle_node"`

---

### Task 4: 검증
- [ ] 단위: `PYTHONPATH=. python3 -m pytest test/test_ground_analysis.py -q` → 4 passed
- [ ] 빌드 + `ros2 pkg executables obstacle_detector` → obstacle_node
- [ ] (선택) 합성 depth+camera_info 발행 → ground_status 평탄/범프 확인

## Self-Review
- 3DGS 드롭·목적적합(평면적합+거칠기), cloud_projection 재사용, 하단 300×200 ROI, 로그 문구 사용자 사양.
- 순수 분석 단위테스트, standalone.
