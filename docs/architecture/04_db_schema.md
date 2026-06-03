# DB Schema

Firebase (Firestore) 사용. 아래 SQL은 **데이터 모델 정의용**이며, Firestore에서는 컬렉션/문서로 매핑한다.

`db_bridge`가 `/robot6/db/get_prescription` / `/robot6/db/verify_medicine` 서비스로 이 스키마를 ROS에 노출한다. 연동 흐름은 [db_bridge](02_ros2_packages.md#db_bridge).

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
```

`prescriptions.admin_order` → ROS `MedicineInfo.sequence_order` / `ScanPatient.medicines[]` 순서.
