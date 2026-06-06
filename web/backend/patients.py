"""patients — RTDB patients/ → 프론트 형식 (patient_data.py 대체).

RTDB 노드 {info, vitals[, intake][, visits]} 를 프론트가 기대하는 평탄 dict
({id, ...info, ...vitals, visits, intake})로 변환한다. 순수 변환은 단위테스트.
RTDB 읽기는 fb_read._init() 공유.
"""


def patient_node_to_api(pid, node):
    """patients/{pid} 노드 → 프론트 환자 dict."""
    node = node or {}
    out = {"id": pid}
    out.update(node.get("info") or {})
    out.update(node.get("vitals") or {})
    out["visits"] = node.get("visits") or []
    intake = node.get("intake")
    out["intake"] = (intake or {}).get("data") if isinstance(intake, dict) else None
    return out


def load_patients():
    from fb_read import _init
    raw = _init().reference("patients").get() or {}
    return [patient_node_to_api(pid, node) for pid, node in raw.items()]


def get_patient(pid):
    from fb_read import _init, valid_pid
    if not valid_pid(pid):
        return None
    node = _init().reference(f"patients/{pid}").get()
    return patient_node_to_api(pid, node) if node else None
