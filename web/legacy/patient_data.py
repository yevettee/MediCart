"""patient_data — 환자 xlsx(환자기본정보 + 외래방문기록) → JSON.

등록번호로 기본정보와 외래기록을 묶는다. 컬럼명의 줄바꿈 단위표기는 제거.
"""
import math
import os

import pandas as pd

XLSX = os.environ.get(
    "PATIENT_XLSX",
    "/home/rokey/rokey_ws/src/intel1/common/data/patient_manage.xlsx",
)


def _clean(col):
    """'생년월일\\n(YYYY-MM-DD)' → '생년월일'."""
    return str(col).split("\n")[0].strip()


def _val(v):
    """NaN/NaT → None, 그 외는 JSON 직렬화 가능 형태."""
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, (int, float, bool)):
        return v
    return str(v).strip()


def _records(sheet):
    df = pd.read_excel(XLSX, sheet_name=sheet)
    df.columns = [_clean(c) for c in df.columns]
    out = []
    for _, row in df.iterrows():
        rec = {k: _val(v) for k, v in row.to_dict().items()}
        if rec.get("등록번호"):          # 빈/안내 행 제외
            out.append(rec)
    return out


def load_patients():
    """[{등록번호, 성명, ..., id, visits:[외래기록...]}]."""
    base = _records("환자기본정보")
    visits = _records("외래방문기록")
    by_id = {}
    for v in visits:
        by_id.setdefault(v["등록번호"], []).append(v)
    patients = []
    for p in base:
        pid = p["등록번호"]
        p["id"] = pid
        p["visits"] = sorted(
            by_id.get(pid, []),
            key=lambda x: str(x.get("방문일") or ""),
            reverse=True,
        )
        patients.append(p)
    return patients


def get_patient(pid):
    for p in load_patients():
        if p["id"] == pid:
            return p
    return None
