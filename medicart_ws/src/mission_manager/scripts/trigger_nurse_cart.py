#!/usr/bin/env python3
"""시나리오 B 테스트 스크립트 — 미션 시작 / OCR 완료 / 회진 완료 신호 주입.

사용:
  # 미션 시작 (nurse_cart_mission push)
  python3 trigger_nurse_cart.py start

  # OCR 완료 신호 주입 (WAIT_OCR → GOTO_STANDBY 전이)
  python3 trigger_nurse_cart.py ocr_done

  # 회진 완료 신호 주입 (WAIT_ROUND_DONE → GOTO_HOME+DOCK 전이)
  python3 trigger_nurse_cart.py round_done

  # RTDB nurse_cart 상태 확인
  python3 trigger_nurse_cart.py status
"""
import sys
import time

import firebase_admin
from firebase_admin import credentials, db

FB_CRED = '/home/rokey/MediCart/common/serviceAccountKey.json'
FB_DB_URL = 'https://medi-cart-ea39f-default-rtdb.asia-southeast1.firebasedatabase.app'
NS = 'robot6'


def init():
    if not firebase_admin._apps:
        cred = credentials.Certificate(FB_CRED)
        firebase_admin.initialize_app(cred, {'databaseURL': FB_DB_URL})


def start_mission():
    init()
    key = f'test_{int(time.time())}'
    db.reference(f'{NS}/mission_pool/{key}').set({
        'action': 'nurse_cart_mission',
        'status': 'pending',
        'params': {},
        'ts': int(time.time() * 1000),
    })
    print(f'[시나리오 B] nurse_cart_mission 전송 완료: {key}')
    print(f'  → RTDB: {NS}/mission_pool/{key}')


def inject_ocr_done():
    init()
    db.reference(f'{NS}/nurse_cart/ocr_done').set(True)
    print(f'[시나리오 B] OCR 완료 신호 전송 완료')
    print(f'  → RTDB: {NS}/nurse_cart/ocr_done = true')


def inject_round_done():
    init()
    db.reference(f'{NS}/nurse_cart/round_done').set(True)
    print(f'[시나리오 B] 회진 완료 신호 전송 완료')
    print(f'  → RTDB: {NS}/nurse_cart/round_done = true')
    print(f'  → 로봇: WAIT_ROUND_DONE → GOTO_HOME → DOCK')


def show_status():
    init()
    phase = db.reference(f'{NS}/nurse_cart/phase').get()
    ocr_done = db.reference(f'{NS}/nurse_cart/ocr_done').get()
    pool = db.reference(f'{NS}/mission_pool').get() or {}
    status = db.reference(f'{NS}/mission_status').get() or {}

    print(f'=== 시나리오 B 상태 ===')
    print(f'  nurse_cart/phase    : {phase}')
    print(f'  nurse_cart/ocr_done : {ocr_done}')
    print(f'  mission_pool 건수   : {len(pool)}')
    print(f'  현재 미션           : {status.get("current_action")} / {status.get("current_id")}')
    print(f'  경과               : {status.get("current_elapsed")}s')


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'status'
    if cmd == 'start':
        start_mission()
    elif cmd == 'ocr_done':
        inject_ocr_done()
    elif cmd == 'round_done':
        inject_round_done()
    elif cmd == 'status':
        show_status()
    else:
        print(f'알 수 없는 명령: {cmd}')
        print('사용법: python3 trigger_nurse_cart.py [start|ocr_done|round_done|status]')
        sys.exit(1)
