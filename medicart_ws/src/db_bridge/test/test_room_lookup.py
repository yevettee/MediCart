"""room_lookup 단위 테스트 — 가짜 fb(dict)로 /rooms waypoint 추출 검증."""
from db_bridge.room_lookup import list_rooms


class FakeFB:
    def __init__(self, data):
        self.data = data

    def read(self, path):
        return self.data.get(path)


_ROOMS = {
    'rooms': {
        '101-A': {'x': 1.0, 'y': 2.0, 'yaw': 0.0, 'patient': 'P-2026-0001'},
        '101-B': {'x': 1.0, 'y': 3.2, 'yaw': 0.0, 'patient_id': 'P-2026-0002'},
        '102-A': {'x': 4.0, 'y': 2.0, 'yaw': 1.57},
        'home': {'x': 0.0, 'y': 0.0, 'yaw': 0.0},
        'pharmacy': {'x': 5.0, 'y': 5.0, 'yaw': 0.0},
        'nurse_station': {'x': 3.0, 'y': 0.0, 'yaw': 0.0},
    }
}


def test_list_all_rooms_sorted():
    rooms = list_rooms(FakeFB(_ROOMS), '')
    ids = [r['room_id'] for r in rooms]
    assert ids == ['101-A', '101-B', '102-A', 'home', 'nurse_station', 'pharmacy']


def test_filter_bed_excludes_special():
    rooms = list_rooms(FakeFB(_ROOMS), 'bed')
    ids = [r['room_id'] for r in rooms]
    assert ids == ['101-A', '101-B', '102-A']


def test_patient_id_from_both_keys():
    rooms = {r['room_id']: r for r in list_rooms(FakeFB(_ROOMS), 'bed')}
    assert rooms['101-A']['patient_id'] == 'P-2026-0001'   # 'patient'
    assert rooms['101-B']['patient_id'] == 'P-2026-0002'   # 'patient_id'
    assert rooms['102-A']['patient_id'] == ''              # 미배정


def test_pose_values():
    rooms = {r['room_id']: r for r in list_rooms(FakeFB(_ROOMS), 'bed')}
    assert rooms['102-A']['x'] == 4.0 and rooms['102-A']['yaw'] == 1.57


def test_skips_nonnumeric_and_nondict():
    fb = FakeFB({'rooms': {
        'bad': {'x': 'NaNish', 'y': 1.0, 'yaw': 0.0},
        'str': 'not-a-dict',
        'ok': {'x': 1.0, 'y': 1.0, 'yaw': 0.0},
    }})
    ids = [r['room_id'] for r in list_rooms(fb, '')]
    assert ids == ['ok']


def test_empty_rooms():
    assert list_rooms(FakeFB({}), 'bed') == []
