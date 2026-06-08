"""patient_lookup 단위 테스트 — 가짜 fb(dict 기반)로 RTDB 조회 로직 검증."""
from db_bridge.patient_lookup import lookup_name, lookup_room, resolve_patient


class FakeFB:
    """read(path) 만 흉내내는 가짜 FirebaseClient. data: {path: value}."""

    def __init__(self, data):
        self.data = data

    def read(self, path):
        return self.data.get(path)


def test_lookup_name_korean_field():
    fb = FakeFB({'patients/P-1/info': {'성명': '홍길동', '진료과': '내과'}})
    assert lookup_name(fb, 'P-1') == '홍길동'


def test_lookup_name_fallback_and_missing():
    assert lookup_name(FakeFB({'patients/P-1/info': {'name': 'Gildong'}}), 'P-1') == 'Gildong'
    assert lookup_name(FakeFB({}), 'P-1') == ''


def test_lookup_room_priority_direct():
    fb = FakeFB({
        'patients/P-1/room': '101-A',
        'patient_rooms/P-1': {'room': '999'},
        'rooms': {'202-B': {'patient': 'P-1'}},
    })
    assert lookup_room(fb, 'P-1') == '101-A'   # 1순위가 이김


def test_lookup_room_patient_rooms_index():
    fb = FakeFB({'patient_rooms/P-1': {'room': '102-B'}})
    assert lookup_room(fb, 'P-1') == '102-B'


def test_lookup_room_reverse_search():
    fb = FakeFB({'rooms': {
        '101-A': {'x': 1.0, 'patient': 'P-9'},
        '101-B': {'x': 2.0, 'patient_id': 'P-1'},
    }})
    assert lookup_room(fb, 'P-1') == '101-B'


def test_lookup_room_unresolved():
    assert lookup_room(FakeFB({'rooms': {'101-A': {'x': 1.0}}}), 'P-1') == ''


def test_resolve_patient_full():
    fb = FakeFB({
        'patients/P-1': {'info': {'성명': '홍길동'}, 'room': '101-A'},
        'patients/P-1/info': {'성명': '홍길동'},
        'patients/P-1/room': '101-A',
    })
    res = resolve_patient(fb, 'P-1')
    assert res == {'found': True, 'name': '홍길동', 'room': '101-A', 'message': 'ok'}


def test_resolve_patient_not_found():
    res = resolve_patient(FakeFB({}), 'P-404')
    assert res['found'] is False
    assert 'not found' in res['message']


def test_resolve_patient_empty_id():
    res = resolve_patient(FakeFB({}), '   ')
    assert res['found'] is False
    assert res['message'] == 'empty patient_id'


def test_resolve_patient_room_unresolved():
    fb = FakeFB({'patients/P-1': {'info': {'성명': '홍길동'}},
                'patients/P-1/info': {'성명': '홍길동'}})
    res = resolve_patient(fb, 'P-1')
    assert res['found'] is True
    assert res['room'] == ''
    assert 'room unresolved' in res['message']
