"""Firebase Realtime DB — 환자/주사 데이터 연동."""

import glob
import os
import time

import firebase_admin
from firebase_admin import credentials, db
from ament_index_python.packages import get_package_share_directory

_DATABASE_URL = 'https://medi-cart-ea39f-default-rtdb.asia-southeast1.firebasedatabase.app'


def _find_firebase_key() -> str:
    """Firebase 키 파일을 자동으로 찾아서 경로 반환."""

    # 1) 환경변수
    env_path = os.environ.get('FIREBASE_KEY_PATH', '')
    if env_path and os.path.exists(env_path):
        return env_path

    # 2) ~/rokey_ws/db_test/ — 팀 공용 키 위치
    pattern = os.path.expanduser('~/rokey_ws/db_test/medi-cart-*firebase*.json')
    matches = glob.glob(pattern)
    if matches:
        return matches[0]

    # 3) 패키지 내 credentials/ — 직접 넣은 경우
    pkg_key = os.path.join(
        get_package_share_directory('ocr_detector'),
        'credentials',
        'firebase_key.json',
    )
    if os.path.exists(pkg_key):
        return pkg_key

    raise FileNotFoundError(
        'Firebase 키 파일을 찾을 수 없어요.\n'
        '아래 중 하나를 해주세요:\n'
        '  1) ~/rokey_ws/db_test/ 에 medi-cart-*firebase*.json 파일이 있는지 확인\n'
        '  2) 환경변수 FIREBASE_KEY_PATH 에 키 파일 경로 지정\n'
        '  3) ~/ocr_ws/src/ocr_detector/credentials/firebase_key.json 에 직접 넣기'
    )


def _init():
    if not firebase_admin._apps:
        key_path = _find_firebase_key()
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
