"""patients 순수 변환 단위 테스트.

실행: cd MediCart/web/backend && python3 -m pytest test/test_patients.py -v
"""
import patients
from patients import patient_node_to_api


def test_patient_node_to_api_flattens():
    node = {"info": {"성명": "홍길동", "혈액형": "A"},
            "vitals": {"통증점수": 3},
            "intake": {"data": {"주호소": "두통"}, "ts": 5}}
    out = patient_node_to_api("P-2026-0001", node)
    assert out["id"] == "P-2026-0001"
    assert out["성명"] == "홍길동" and out["혈액형"] == "A"
    assert out["통증점수"] == 3
    assert out["intake"] == {"주호소": "두통"}
    assert out["visits"] == []          # visits 미임포트 → 빈 배열


def test_patient_node_to_api_with_visits_and_no_intake():
    node = {"info": {"성명": "김"}, "vitals": {}, "visits": [{"방문일": "2026-01-01"}]}
    out = patient_node_to_api("P-2026-0002", node)
    assert out["visits"] == [{"방문일": "2026-01-01"}]
    assert out["intake"] is None


def test_patient_node_exposes_intake_done_true():
    out = patients.patient_node_to_api("P-2024-0001", {"info": {}, "intake_done": True})
    assert out["intake_done"] is True


def test_patient_node_intake_done_defaults_false():
    out = patients.patient_node_to_api("P-2024-0001", {"info": {}})
    assert out["intake_done"] is False
