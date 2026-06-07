"""cloud_projection — depth+RGB+intrinsics → 컬러 3D점, 좌표변환. 순수 numpy(ROS 무관)."""

import numpy as np


def project_roi(depth_mm, rgb_bgr, fx, fy, cx, cy, roi=None,
                min_depth=0.3, max_depth=6.0):
    """16UC1 depth(mm)+BGR → (points Nx3 float32 [광학프레임 m], colors Nx3 uint8 RGB).

    roi=(x1,y1,x2,y2)면 그 영역만(계층2). None이면 전체(계층1).
    광학프레임 규약(REP-103): x→오른쪽, y→아래, z→전방.
    """
    h, w = depth_mm.shape[:2]
    if roi is None:
        x1, y1, x2, y2 = 0, 0, w, h
    else:
        x1, y1, x2, y2 = (int(max(0, roi[0])), int(max(0, roi[1])),
                          int(min(w, roi[2])), int(min(h, roi[3])))
    us, vs = np.meshgrid(np.arange(x1, x2), np.arange(y1, y2))
    z = depth_mm[y1:y2, x1:x2].astype(np.float32) / 1000.0
    m = (z >= min_depth) & (z <= max_depth)
    u, v, z = us[m], vs[m], z[m]
    x = (u - cx) * z / fx
    y = (v - cy) * z / fy
    pts = np.stack([x, y, z], axis=1).astype(np.float32)
    bgr = rgb_bgr[y1:y2, x1:x2][m]
    cols = bgr[:, ::-1].astype(np.uint8)
    return pts, cols


def _quat_to_rot(q_xyzw):
    x, y, z, w = q_xyzw
    return np.array([
        [1 - 2*(y*y + z*z), 2*(x*y - z*w),     2*(x*z + y*w)],
        [2*(x*y + z*w),     1 - 2*(x*x + z*z), 2*(y*z - x*w)],
        [2*(x*z - y*w),     2*(y*z + x*w),     1 - 2*(x*x + y*y)],
    ], np.float32)


def transform_points(points, t_xyz, q_xyzw):
    """points(Nx3)를 (translation, quaternion xyzw)로 회전·평행이동."""
    if points.size == 0:
        return points
    R = _quat_to_rot(q_xyzw)
    return (points @ R.T + np.asarray(t_xyz, np.float32)).astype(np.float32)


def project_depth_roi(depth_mm, fx, fy, cx, cy, roi, min_depth=0.3, max_depth=6.0):
    """16UC1 depth(mm)+intrinsics+roi(x1,y1,x2,y2) → 점군 Nx3(광학프레임 m). color 불요."""
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
