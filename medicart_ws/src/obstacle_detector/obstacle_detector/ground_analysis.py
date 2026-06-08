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
