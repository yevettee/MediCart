# nurse_tracker 탐지 모델 학습 — 설계 (nurse / obstacle)

**작성일:** 2026-06-08
**목표:** `nurse_tracker` 가 사용할 2클래스(nurse·obstacle) YOLO11s **탐지** 모델을 학습해
`nurse_tracker/models/ward_model.pt` 로 배치한다.

---

## 1. 배경 / 소비처

`nurse_tracker/nurse_tracker/perception.py` 의 `PersonTracker` 는 YOLO `model.track`(ByteTrack)
결과를 `[x1,y1,x2,y2,conf,cls,track_id]` **바운딩박스**로만 소비한다(마스크 미사용).
따라서 **탐지(detection) 모델**이면 충분하며, 세그멘테이션은 불필요.

- 클래스: `0=nurse`, `1=obstacle` (3개 part data.yaml 모두 `names:['nurse','obstacle']` 일치)
- 추종 대상은 `nurse`. `obstacle` 는 회피/상황인지용 부가 클래스.
- 학습 후 `perception.py` 의 `target_classes` 는 `("nurse",)` 로 결선(본 스펙 범위 밖, 후속).

## 2. 데이터셋 실측 (`/home/rokey/Downloads/traking_dataset`)

| 항목 | 값 |
|---|---|
| 이미지 | 704장 (512×512, Roboflow export), part1/2/3 각 train split |
| 인스턴스 | 844개 — nurse 628 · obstacle 216 |
| 클래스 불균형 | nurse:obstacle ≈ **2.9 : 1** (nurse 74%) |
| obstacle 등장 이미지 | 216 / 704 |
| 라벨 형식 | **폴리곤(세그멘테이션)** — `class x1 y1 …`. bbox 0개 |
| 빈 라벨(배경) | 1장 |

**불균형 판정:** 경증~중등도. 치명적이지 않으나 obstacle 절대량이 적어 obstacle recall 약화 가능.
→ 재가중 대신 **증강(mosaic/mixup) + 클래스별 mAP 모니터링** 으로 대응.

**폴리곤 처리:** 탐지 task 로 학습 시 ultralytics 가 폴리곤을 외접 bbox 로 자동 변환(`segments2boxes`).

## 3. 데이터 준비 (병합 + split)

3개 part 의 train-only 데이터를 병합 후 **85/15** 로 분할(`val` 부재 해소).

- 출력: `/home/rokey/Downloads/traking_dataset/merged/`
  - `images/{train,val}/`, `labels/{train,val}/`, `data.yaml`
- **클래스 인지 분할(seed=42):** obstacle 포함 이미지(216장)와 nurse-only 이미지를 각각 85/15 로 나눠
  두 split 모두 obstacle 대표성 확보(val obstacle ≈ 30여 장).
- 파일명 충돌 방지: `part{n}__` 프리픽스로 복사. 라벨 원본(폴리곤) 그대로 복사 — 변환은 학습기가 수행.
- `data.yaml`: `train`/`val` 절대경로, `nc: 2`, `names: ['nurse','obstacle']`.

## 4. 학습 구성 (`yolo11s.pt`, RTX 4070 Laptop 8GB)

| 파라미터 | 값 | 근거 |
|---|---|---|
| model | `yolo11s.pt` (COCO pretrained) | 704장 소규모 → 전이학습 |
| imgsz | 640 | 512 letterbox, 원거리 obstacle recall, 추론 기본값 일치 |
| epochs | 150, patience 30 | 사전학습 빠른 수렴 + early-stop 과적합 차단 |
| batch | 16 (OOM 시 8) | yolo11s@640 / 8GB |
| optimizer | auto (AdamW) | lr/모멘텀 자동 |
| cos_lr | True | 후반 안정 수렴 |
| mosaic / close_mosaic | 1.0 / 10 | 막판 10ep off → 실분포 미세조정 |
| mixup | 0.1 | 소규모 보강 |
| fliplr / flipud | 0.5 / 0.0 | 정립 시점, 상하반전 X |
| degrees / scale | 5.0 / 0.5 | 약한 회전·스케일 |
| hsv_h/s/v | 기본 | 조명 변화 |
| seed | 42 | 재현성 |
| device | 0 | GPU |

프로젝트/이름: `runs/detect/ward_nurse_obstacle` (cwd = `/home/rokey/Downloads/traking_dataset`).

## 5. 산출물 / 검증

- 학습 산출물: `runs/detect/ward_nurse_obstacle/` (results.png, confusion_matrix, PR curve, weights/best.pt)
- **`best.pt` → `/home/rokey/MediCart/medicart_ws/src/nurse_tracker/models/ward_model.pt`** 복사
- 검증: 최종 `val` 의 **클래스별** mAP50 / mAP50-95 보고. obstacle mAP50 이 nurse 대비 현저히 낮으면 후속(오버샘플/추가수집) 권고.
- 영향도: `nurse_tracker` 코드 무변경(본 스펙은 모델 산출물만 추가). `target_classes` 결선은 후속 작업.

## 6. 범위 밖 (후속)
- `perception.py` `target_classes=("nurse",)` 결선 및 실로봇 추종 검증.
- ReID(OSNet) — 보류 유지.
- obstacle 데이터 추가 수집(불균형 개선 필요 판정 시).
