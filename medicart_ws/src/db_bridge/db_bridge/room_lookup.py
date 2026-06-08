"""room_lookup — RTDB /rooms 에서 waypoint 목록을 뽑는 순수 로직.

firebase 비의존(``read(path)`` 만 쓰는 fb 객체) → 단위 테스트 가능.

RTDB 스키마(아키텍처 문서 §1.2): /rooms/{room_id}/{x,y,yaw,patient(_id)}.
병상이 아닌 특수 지점은 home / nurse_station / pharmacy.
"""

_NON_BED = {'home', 'nurse_station', 'pharmacy'}


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def list_rooms(fb, room_filter=''):
    """RTDB /rooms → [{'room_id','x','y','yaw','patient_id'}] (room_id 오름차순).

    room_filter='bed' 이면 병상만(home/nurse_station/pharmacy 제외).
    x/y/yaw 가 숫자가 아닌 항목은 건너뛴다.
    """
    rooms = fb.read('rooms')
    out = []
    if not isinstance(rooms, dict):
        return out
    want_bed = (room_filter or '').lower() == 'bed'
    for room_id in sorted(rooms):
        room = rooms[room_id]
        if not isinstance(room, dict):
            continue
        if want_bed and room_id in _NON_BED:
            continue
        x, y, yaw = _num(room.get('x')), _num(room.get('y')), _num(room.get('yaw'))
        if x is None or y is None or yaw is None:
            continue
        patient_id = room.get('patient_id') or room.get('patient') or ''
        out.append({'room_id': room_id, 'x': x, 'y': y, 'yaw': yaw,
                    'patient_id': str(patient_id)})
    return out
