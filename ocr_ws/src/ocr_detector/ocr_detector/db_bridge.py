"""Firebase Realtime DB — 환자/주사 데이터 연동."""

import os
import time

import firebase_admin
from firebase_admin import credentials, db
from ament_index_python.packages import get_package_share_directory

_DATABASE_URL = 'https://medi-cart-ea39f-default-rtdb.asia-southeast1.firebasedatabase.app'


def _init():
    if not firebase_admin._apps:
        key_path = os.path.join(
            get_package_share_directory('ocr_detector'),
            'credentials',
            'firebase_key.json',
        )
        cred = credentials.Certificate(key_path)
        firebase_admin.initialize_app(cred, {'databaseURL': _DATABASE_URL})


def get_patients_with_injections() -> dict:
    """환자 목록과 주사 처방 정보 반환."""
    _init()
    patients = db.reference('/patients').get() or {}
    result = {}
    for pid, data in patients.items():
        injections = data.get('injections', {})
        if injections:
            info = data.get('info', {})
            result[pid] = {
                'name': info.get('성명', pid),
                'injections': injections,
            }
    return result


def save_ocr_result(text: str):
    """OCR 결과를 /ocr/latest에 저장."""
    _init()
    db.reference('/ocr/latest').set({
        'text': text,
        'ts': int(time.time() * 1000),
    })


def update_injection_status(patient_id: str, inj_id: str, status: str):
    """주사 상태 업데이트 (대기 → 완료 / 불일치)."""
    _init()
    db.reference(f'/patients/{patient_id}/injections/{inj_id}/상태').set(status)
