# medi_interfaces

Custom ROS2 message and service definitions for MediCart.

## Prescription flow

1. `ScanPatient` — load ordered `medicines[]`, start session (`total_steps`)
2. `ScanMedicine` (repeat) — verify OCR against `medicines[current_step]`, advance on match
3. `GetPrescription` — internal db_bridge API (same data as scan patient DB lookup)
4. `VerifyMedicine` — internal verification with `step_index` + `scanned_text`
