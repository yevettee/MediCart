# Integration TODO List

> **상태**: 분석·결정 완료, **실제 정리작업은 보류(추후 진행)**.
> 작성 2026-06-09. 기준 브랜치 `integration`(main ↔ jaehoon 머지본, PR #3).

이 문서는 main↔jaehoon 통합 과정에서 도출된 **후속 정리 항목**을 보류 상태로 기록한다.
각 항목은 분석·결정까지 끝났고, 실행만 미뤄둔 것이다.

---

## A. 미사용/스텁 패키지 정리 (보류)

`medicart_ws/src` 분석 결과(구현 상태 + bringup 연결 + import/서비스 사용처):

| 패키지 | 판정 | 처리 결정 |
| --- | --- | --- |
| **ocr_detector** | 🔴 순수 스텁(노드 로그만, `OcrEngine.recognize→('',0.0)`), 미사용(웹이 GCP Vision으로 OCR) | **삭제(git rm)** — 단 ⚠️ 선행조건 있음(아래) |
| **scanner** | 🔴 노드 스텁, `medicine_matcher`만 로직 보유하나 **import·서비스서버 0**(미배선) | **삭제(git rm)** |
| temp | 🟠 ROS 패키지 아님(`capture_gui` 임시 유틸) | 정리 범위 외(원하면 별도 결정) |
| patient_identifier | 🟡 구현됨(~257줄, YOLO+QR) **but bringup 미연결** | 스텁 아님 → 정리 대상 아님(연결 여부만 추후 검토) |
| dashboard | 🟡 구현됨(~1256줄, 독립 운영자 도구, 수동 실행) | 유지 |
| simulation | 🟢 노드는 스텁이나 **Gazebo 자산 실재**(hospital.sdf·world 생성기·launch4·nav2/slam config) | 유지 |
| db_bridge · mission_manager · nurse_tracker · obstacle_detector | 🟢 구현 + `robot6_bringup.launch.py` 연결 | 유지 |
| medi_interfaces | 🟢 타입 계약(사용 중) | 유지(단 미사용 타입 trim은 B 참조) |

**정리 결정**: 범위 = **순수 스텁 2개(ocr_detector·scanner)만**, 방식 = **완전 삭제(git rm)**.
의존성 검증 완료: 다른 package.xml/코드에서 두 패키지를 의존·import하는 곳 **없음**(self 참조만).

### ⚠️ ocr_detector 삭제 전 선행조건 (중요)
`web/backend/ocr.py`가 GCP Vision 키를 다음 경로에서 읽는다:
- 기본값 `_DEFAULT_KEY = /home/rokey/MediCart/medicart_ws/src/ocr_detector/credentials/gcp_vision_key.json`
- env override `GCP_VISION_KEY_PATH` (백엔드 `.env`에 설정돼 있음)

`ocr_detector/credentials/gcp_vision_key.json`(2.3KB, gitignore된 시크릿)이 **삭제될 패키지 폴더 안**에 있다.
→ **삭제 전 키 파일을 패키지 밖(예: `~/secrets/` 또는 `web/backend/`)으로 이전**하고,
   `web/backend/.env`의 `GCP_VISION_KEY_PATH`와 `ocr.py`의 `_DEFAULT_KEY`를 새 경로로 갱신할 것.
   (이 단계 누락 시 웹 OCR이 키를 못 찾아 깨짐.)

---

## B. medi_interfaces 미사용 타입 trim 검토 (보류)

medi_interfaces(msg 5 + srv 11) 중 **실제 결선된 것**과 **정의만 있는 것**:

**실사용(5)** — 유지:
- `GetPrescription`(srv): 서버 `db_bridge/prescription_server.py` ↔ 클라 `patient_identifier/patient_validator.py`
- `ListRooms`(srv): 서버 `db_bridge/rooms_server.py` ↔ 클라 `mission_manager/patrol_mode_node.py`
- `PatientIdentified`(msg): 발행 `patient_identifier/identifier_node.py` → 구독 `mission_manager/patrol_mode_node.py`
- `PatientInfo`·`MedicineInfo`(msg): GetPrescription 응답에 중첩 사용

**미사용(정의만, 시나리오 B/문진 선정의)** — trim 후보:
- `RobotState`, `ScanMedicine`, `VerifyMedicine`, `ScanPatient`, `StartTracking`,
  `StartMedication`, `GetOcrResult`, `MoveHome`, `UpdateVisitStatus` (+ `StartPatrol` 서버 결선 미확인)
- 이 중 `ScanMedicine`/`VerifyMedicine`/`GetOcrResult`는 **A의 scanner/ocr_detector가 구현 예정이던 서비스** →
  스텁 삭제 시 함께 trim 고려.

**불일치 2건(정리 시 참고)**:
- `nurse_tracker/tracker_node.py`가 `TargetBBox`를 import하나 실제론 `String`을 `/nurse_tracker/target`에 발행 → TargetBBox import 사실상 미사용.
- 추종 시작은 `StartTracking.srv`가 아니라 `std_srvs/Trigger`(`/{ns}/start_tracking`) 사용 → StartTracking.srv 미사용.

> 주의: 미사용 srv를 삭제하면 추후 시나리오 B 구현 시 다시 정의해야 함. **선정의를 남길지/지울지**는 로드맵 결정 필요.

---

## C. 머지 후속 (PR #3 관련)

- **/debug 정책 충돌**: main이 `/debug` nav 추가 vs jaehoon이 `/debug → /console` 리다이렉트 → 공존 중.
  /debug 클릭 시 /console로 바운스. 둘 중 하나로 정리(콘솔 통합 유지 권장 → /debug nav 제거, 또는 리다이렉트 해제).
- **빌드 수정 기록**: 머지 중 `/intake`의 `useSearchParams`를 Suspense 경계로 래핑(Next16 요구) — 이미 반영됨.
- **colcon build · 실로봇 E2E**: 소스 통합·web 빌드까지만 검증됨. 로봇 환경에서 `cd ~/MediCart/medicart_ws && colcon build` + 실주행 검증 필요.
- **대용량 파일 정책**: `nurse_tracker/models/best.pt`(19MB)·`medicart_ws/src/temp/dataset`(75MB, gitignore됨) — git LFS/보관 정책 추후.

---

## 진행 순서(추후 재개 시 권장)
1. (A 선행) GCP 키 이전 + `.env`/`ocr.py` 경로 갱신
2. (A) `git rm -r ocr_detector scanner` → colcon list/build 검증
3. (B) 미사용 srv trim 여부 로드맵 결정 후 정리
4. (C) /debug 정책 정리 → PR #3 반영 → colcon/E2E 검증
