# obstacle_detector (지면 평탄도) 설계

**날짜:** 2026-06-07
**대상:** `medicart_ws/src/obstacle_detector` — OAK-D depth 하단 ROI로 지면 점군을 만들어 평면적합+거칠기로 **평탄/울퉁불퉁** 판단. standalone(주행 연동 없음, 울퉁불퉁 시 로그).

## 결정 (brainstorming)

- **3DGS 드롭.** cloud3d의 gs_pipeline·nerf·COLMAP·voxel은 포토리얼 렌더/맵핑용이라 평탄도 목적에 과함. 목적엔 **depth→평면적합→거칠기**가 정답.
- **재사용**: cloud3d `cloud_projection.project_roi`(순수 numpy depth→3D, ROI 지원) 를 복사·확장(`project_depth_roi`, color 불요).
- **ROI**: 연산절감 위해 프레임 **하단 중앙 300(w)×200(h)** 만 분석(사용자 사양).
- **색칠**: RGB 카메라 대신 **평면편차로 색칠**(평탄 초록·범프 빨강) → RGB 동기화 불요, depth만.
- **출력**: PointCloud2(시각화) + ground_status(JSON). 울퉁불퉁 시 `get_logger().warn("표면이 울퉁불퉁 합니다 값 : {std:.3f}m")`(throttle). 주행 연동(정지/감속)은 후속.

## 파이프라인

```
/{ns}/oakd/stereo/image_raw/compressedDepth (16UC1 mm, 12B 헤더)
/{ns}/oakd/stereo/camera_info (fx,fy,cx,cy)
   → 하단중앙 300×200 ROI → project_depth_roi → 점군(광학프레임 Nx3)
   → fit_plane(SVD 최소제곱) → 점-평면 부호거리
   → roughness {std, max_dev, inlier_ratio, n}
   → classify(std ≤ flat_std_thresh(0.02) → 평탄, 점<min_points 면 None=미상)
발행: /obstacle_detector/ground_cloud (PointCloud2 xyzrgb, |편차|로 초록→빨강)
      /obstacle_detector/ground_status (String JSON {flat, std, max_dev, inlier_ratio, n, ts})
울퉁불퉁(flat=False): logger.warn("표면이 울퉁불퉁 합니다 값 : {std:.3f}m", throttle 2s)
```

## 모듈 (평탄·재사용)

| 파일 | 내용 |
|---|---|
| `cloud_projection.py` | cloud3d 복사 + `project_depth_roi(depth_mm,fx,fy,cx,cy,roi,min,max)→Nx3`(color 불요). 순수 |
| `ground_analysis.py` (신규·순수) | `fit_plane`(SVD)·`roughness`·`classify`. **단위테스트**(합성 평면→평탄 / 범프→울퉁불퉁 / 점부족→None) |
| `obstacle_node.py` | depth+camera_info 구독 → ROI → project → analyze → PointCloud2+status+log |

- **삭제**: 기존 stub `height_filter.py`(대체).
- **의존**: numpy·opencv-python(depth 디코딩)·sensor_msgs_py(PointCloud2). (cv_bridge 불요 — 직접 imdecode.)

## ground_analysis (순수 핵심)

- `fit_plane(points)` → (normal(3,), centroid(3,)) | None(<3점). centroid 중심화 후 SVD 최소특이벡터=법선.
- `roughness(points, plane, inlier_tol=0.02)` → {std(부호거리 표준편차), max_dev(|거리| 최대), inlier_ratio(|거리|≤tol 비율), n}.
- `classify(metrics, std_thresh=0.02, min_points=200)` → bool|None. n<min_points 면 None(미상), 아니면 std≤thresh.

## obstacle_node

- 파라미터: namespace, depth_topic, caminfo_topic, roi_w=300, roi_h=200, min_depth=0.3, max_depth=6.0, flat_std_thresh=0.02, inlier_tol=0.02, min_points=200, frame_id(광학프레임), warn_period=2.0.
- camera_info에서 K→fx,fy,cx,cy(1회 캐시). depth 콜백마다: 디코딩→ROI(하단중앙)→project→fit_plane→roughness→classify→발행/로그.
- ROI: `x1=w//2-roi_w//2, y1=h-roi_h, x2=x1+roi_w, y2=h` (하단 중앙, 경계 클램프).
- PointCloud2: `sensor_msgs_py.point_cloud2`로 xyzrgb, |편차|/max 비례 초록(0)→빨강(≥tol) 색.

## 검증

- 단위: `ground_analysis` — 합성 평면(노이즈 1mm)→flat True·std작음 / 범프(±5cm)→flat False·std큼 / 10점→None. `project_depth_roi` ROI·필터.
- 빌드: `colcon build --packages-select obstacle_detector` + import.
- 통합(카메라 없이): 합성 16UC1 depth + camera_info 발행 → ground_status/PointCloud2 나오는지(평탄/범프 합성). 실 OAK-D는 사용자 실행.

## 범위 밖 (후속)
- RANSAC 강건화(ROI에 장애물/사람 섞일 때), 주행 연동(울퉁불퉁→정지/감속, mission_manager), 시간적 평활(연속 프레임), 웹 시각화.
