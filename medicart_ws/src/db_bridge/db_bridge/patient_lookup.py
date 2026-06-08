"""patient_lookup — RTDB /patients·/rooms 에서 환자 이름·병실을 조회하는 순수 로직.

ROS/firebase 에 의존하지 않고 ``read(path)`` 만 제공하는 객체(fb)를 받으므로
단위 테스트에서 가짜 fb 로 검증 가능하다. (FirebaseClient.read 와 시그니처 동일)

RTDB 스키마(아키텍처 문서 §1.2~1.3 기준):
  /patients/{id}/info/성명           환자 이름
  /patients/{id}/room                (있으면) 병실 — 1순위
  /patient_rooms/{id}/room           역색인 — 2순위
  /rooms/{room_id}/patient(_id)      방→환자 매핑 역검색 — 3순위
"""

_NAME_KEYS = ('성명', 'name', 'patient_name')


def lookup_name(fb, patient_id):
    """/patients/{id}/info 에서 환자 이름을 뽑는다. 없으면 ''."""
    info = fb.read(f'patients/{patient_id}/info')
    if isinstance(info, dict):
        for key in _NAME_KEYS:
            val = info.get(key)
            if val:
                return str(val)
    return ''


def lookup_room(fb, patient_id):
    """우선순위(환자 직속 → 역색인 → 방 역검색)로 병실을 찾는다. 없으면 ''."""
    # 1순위: /patients/{id}/room
    direct = fb.read(f'patients/{patient_id}/room')
    if direct:
        return str(direct)

    # 2순위: /patient_rooms/{id}(/room)
    rev = fb.read(f'patient_rooms/{patient_id}')
    if isinstance(rev, dict):
        if rev.get('room'):
            return str(rev['room'])
    elif rev:
        return str(rev)

    # 3순위: /rooms/{room_id}/patient(_id) 역검색
    rooms = fb.read('rooms')
    if isinstance(rooms, dict):
        for room_id, room in rooms.items():
            if isinstance(room, dict) and patient_id in (room.get('patient'),
                                                         room.get('patient_id')):
                return str(room_id)
    return ''


def resolve_patient(fb, patient_id):
    """환자 존재 여부 + 이름 + 병실을 묶어 반환.

    반환: {'found': bool, 'name': str, 'room': str, 'message': str}
    """
    pid = (patient_id or '').strip()
    if not pid:
        return {'found': False, 'name': '', 'room': '', 'message': 'empty patient_id'}

    patient = fb.read(f'patients/{pid}')
    if not patient:
        return {'found': False, 'name': '', 'room': '',
                'message': f'patient {pid} not found'}

    name = lookup_name(fb, pid)
    room = lookup_room(fb, pid)
    if not room:
        return {'found': True, 'name': name, 'room': '',
                'message': f'patient {pid} found but room unresolved'}
    return {'found': True, 'name': name, 'room': room, 'message': 'ok'}
