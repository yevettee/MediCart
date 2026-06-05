# DB Schema

Firebase (Firestore) 사용. 아래 SQL은 **데이터 모델 정의용**이며, Firestore에서는 컬렉션/문서로 매핑한다.

`db_bridge`가 `/robot6/db/get_prescription` / `/robot6/db/verify_medicine` 서비스로 이 스키마를 ROS에 노출한다(시나리오 B). 연동 흐름은 [db_bridge](02_ros2_packages.md#db_bridge).

**시나리오 A(순찰)**: `db_bridge.update_patient_status()`가 순찰 결과(`identified`/`absent`/`mismatch` 등)를 환자 레코드에 기록한다. **문진표(interview)는 ROS가 아니라 웹 앱이 직접 Firestore에 저장**한다(아래 `patient_visits` / `interviews` 참고).

```sql
CREATE TABLE patients (
    patient_id   VARCHAR(20) PRIMARY KEY,
    name         VARCHAR(100) NOT NULL,
    room         VARCHAR(20),
    birth_date   DATE,
    created_at   TIMESTAMP DEFAULT NOW()
);

CREATE TABLE medicines (
    medicine_id  VARCHAR(50) PRIMARY KEY,
    name         VARCHAR(200) NOT NULL,
    dosage       VARCHAR(100),
    manufacturer VARCHAR(200),
    expiry_date  DATE
);

CREATE TABLE prescriptions (
    prescription_id  VARCHAR(50) PRIMARY KEY,
    patient_id       VARCHAR(20) REFERENCES patients(patient_id),
    medicine_id      VARCHAR(50) REFERENCES medicines(medicine_id),
    admin_order      INTEGER NOT NULL,           -- 투약 순서 (0-based)
    dose_amount      VARCHAR(100),
    frequency        VARCHAR(100),
    start_date       DATE,
    end_date         DATE,
    prescribed_by    VARCHAR(100),
    created_at       TIMESTAMP DEFAULT NOW()
);

CREATE TABLE medication_logs (
    log_id           SERIAL PRIMARY KEY,
    patient_id       VARCHAR(20) REFERENCES patients(patient_id),
    medicine_id      VARCHAR(50) REFERENCES medicines(medicine_id),
    prescription_id  VARCHAR(50) REFERENCES prescriptions(prescription_id),
    administered_by  VARCHAR(100),
    administered_at  TIMESTAMP NOT NULL,
    status           VARCHAR(20),
    robot_session_id VARCHAR(100),
    notes            TEXT
);

-- 시나리오 A: 순찰 방문 결과 (db_bridge.update_patient_status 기록)
CREATE TABLE patient_visits (
    visit_id         SERIAL PRIMARY KEY,
    patient_id       VARCHAR(20) REFERENCES patients(patient_id),
    room             VARCHAR(20),
    status           VARCHAR(20) NOT NULL,   -- identified/absent/mismatch/no_qr/db_error
    robot_session_id VARCHAR(100),
    visited_at       TIMESTAMP DEFAULT NOW()
);

-- 시나리오 A: 문진표 (웹 앱이 직접 저장; ROS 미경유)
CREATE TABLE interviews (
    interview_id     SERIAL PRIMARY KEY,
    patient_id       VARCHAR(20) REFERENCES patients(patient_id),
    pain_level       INTEGER,                -- 1~5
    sleep_quality    VARCHAR(50),
    meal_status      BOOLEAN,
    additional_note  TEXT,
    recorded_at      TIMESTAMP DEFAULT NOW()
);
```

`prescriptions.admin_order` → ROS `MedicineInfo.sequence_order` / `ScanPatient.medicines[]` 순서.

- `patient_visits.status` ← `PatientIdentified.status` (ROS, `db_bridge.update_patient_status`).
- `interviews` ← 웹 문진 앱 직접 기록 (통증 max 등 이상 수치 알림도 웹이 처리).
