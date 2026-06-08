"""ground_analysis 순수 테스트. 실행: cd obstacle_detector && PYTHONPATH=. python3 -m pytest test/test_ground_analysis.py -q"""
import numpy as np
from obstacle_detector.ground_analysis import fit_plane, roughness, classify


def _grid(z_func, n=40):
    xs, ys = np.meshgrid(np.linspace(-0.5, 0.5, n), np.linspace(0.3, 1.0, n))
    zs = z_func(xs, ys)
    return np.stack([xs.ravel(), ys.ravel(), zs.ravel()], axis=1).astype(np.float32)


def test_flat_plane_low_roughness():
    rng = np.random.default_rng(0)
    pts = _grid(lambda x, y: 1.0 + 0.001 * rng.standard_normal(x.shape))   # 평면 + 1mm 노이즈
    m = roughness(pts, fit_plane(pts))
    assert m["std"] < 0.01
    assert classify(m, std_thresh=0.02, min_points=200) is True


def test_bumpy_high_roughness():
    rng = np.random.default_rng(1)
    pts = _grid(lambda x, y: 1.0 + 0.05 * rng.standard_normal(x.shape))    # ±5cm 범프
    m = roughness(pts, fit_plane(pts))
    assert m["std"] > 0.02
    assert classify(m, std_thresh=0.02, min_points=200) is False


def test_few_points_unknown():
    pts = np.zeros((10, 3), np.float32)
    assert classify(roughness(pts, fit_plane(pts)), min_points=200) is None


def test_fit_plane_none_when_too_few():
    assert fit_plane(np.zeros((2, 3), np.float32)) is None
