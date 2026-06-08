#!/usr/bin/env python3
"""
generate_hospital_world.py — MediCart 병원 Gazebo 월드(SDF) 생성기 (도면 기반 v2).

self-contained: turtlebot4_ws 의 어떤 파일에도 의존하지 않음 (SDF 헤더 내장).
좌표계: 방 좌하단 = 월드 원점(0,0), x→오른쪽(0~6.0), y→위(0~4.75), 단위 m.
        ※ 도면(손그림) 기반 1차 근사 — 벽/문 위치는 ASCII 미리보기로 보정한다.

레이아웃 (도면 해석):
  - 외곽 6.0 x 4.75 m, 하단 중앙에 입구(entrance) 개구부
  - 좌측(x:0~2.44) 병실 2개:
        병실1(상, y:2.40~4.75) — 침대1, 침대2
        병실2(하, y:0~2.40)   — 침대3
  - 중앙 복도(corridor)
  - 우상단 로봇 도킹스테이션 (로봇1/로봇2 spawn)
  - 우하단 약 보관실(pharmacy)
  침대 치수: 0.55(x) x 0.35(y) x 0.32(z) m.

사용:
    python3 generate_hospital_world.py            # worlds/hospital.sdf 생성
    python3 generate_hospital_world.py --preview  # 터미널 ASCII 미리보기
"""
import os
import sys
import numpy as np

WORLD_FILE = 'hospital'
WORLD_NAME = 'hospital'      # SDF <world name> — launch 의 world 인자와 일치해야 함
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, f'{WORLD_FILE}.sdf')

# ---- 전체 치수 (m) ----
W, H = 6.00, 4.75
# 실제 벽은 2mm 합판이라 도면 치수 ≈ 내부 clear 치수. Gazebo 벽도 얇게(2cm) 두어
# 도면과 오차를 최소화한다. 외벽은 바깥면이 0..W/0..H 가 되도록 중심선을 바깥으로
# T/2 밀고(→ 내부 = 정확히 6.0x4.75), 내부 벽은 도면 좌표(중심선)에 맞춘다.
T, HGT = 0.02, 0.50          # 벽 두께(2cm ~ 합판), 높이 50cm
WALL_RGB = '0.80 0.82 0.85'

# ---- 주요 분기 좌표 (도면 근사, 보정 대상) ----
LEFT_X = 2.44                # 좌측 병실 오른쪽 벽 x
DIV_Y = 2.40                 # 병실1/병실2 수평 분리벽 y
DOCK_X = 4.30                # 도킹스테이션 왼쪽 벽 x
DOCK_Y = 2.95                # 도킹스테이션 아래쪽 벽 y
PHARM_X = 4.60               # 약보관실 왼쪽 벽 x
PHARM_Y = 1.86               # 약보관실 위쪽 벽 y
ENT_X0, ENT_X1 = 2.95, 3.65  # 하단 입구 개구부 x 범위

# ---- 벽 선분 (x1,y1,x2,y2): 문은 선분을 끊어 gap 으로 표현 ----
def wall_segments():
    h = T / 2.0   # 외벽 바깥면이 0..W / 0..H 가 되도록 중심선을 바깥으로 h 만큼
    return [
        # ===== 외곽 (바깥면 정렬 → 내부 clear = 6.0 x 4.75) =====
        (-h, H + h, W + h, H + h),          # 상단
        (-h, -h, -h, H + h),                # 좌측
        (W + h, -h, W + h, H + h),          # 우측
        (-h, -h, ENT_X0, -h),               # 하단(좌)  ─┐ 입구 gap
        (ENT_X1, -h, W + h, -h),            # 하단(우)  ─┘

        # ===== 좌측 병실 =====
        (0, DIV_Y, LEFT_X, DIV_Y),          # 병실1/병실2 분리벽 (244cm)
        # 좌측 병실 오른쪽 벽 x=2.44 — 문 2개(병실2 142cm, 병실1 130cm) gap
        (LEFT_X, 0, LEFT_X, 0.90),          # 병실2 문 아래
        (LEFT_X, 2.32, LEFT_X, 3.20),       # 병실2 문 위 ~ 병실1 문 아래
        (LEFT_X, 4.50, LEFT_X, H),          # 병실1 문 위

        # ===== 우상단 도킹스테이션 =====
        (DOCK_X, DOCK_Y, DOCK_X, H),        # 도킹 왼쪽 벽 (180cm)
        (4.70, DOCK_Y, W, DOCK_Y),          # 도킹 아래 벽 (로봇 출구 gap: x 4.30~4.70)
        (5.10, 3.75, W, 3.75),              # 로봇1/로봇2 사이 도킹 선반

        # ===== 우하단 약 보관실 =====
        (PHARM_X, PHARM_Y, W, PHARM_Y),     # 약보관실 위 벽 (140cm)
        (PHARM_X, 0, PHARM_X, 0.60),        # 약보관실 왼쪽 벽 아래 ┐ 문 60cm gap(0.60~1.20)
        (PHARM_X, 1.20, PHARM_X, PHARM_Y),  # 약보관실 왼쪽 벽 위   ┘
    ]

# ---- 침대 (x,y center, yaw) : 0.55 x 0.35 x 0.32 m ----
BED_L, BED_W, BED_H = 0.55, 0.35, 0.32
BEDS = [
    ('bed1', 0.45, 3.95, 0.0),   # 병실1
    ('bed2', 0.45, 2.95, 0.0),   # 병실1
    ('bed3', 0.45, 1.05, 0.0),   # 병실2
]

# ---- 로봇 spawn 권장 위치 (도킹스테이션, 우측 벽에 도크가 붙도록) ----
# yaw=0 → 로봇이 +x(우측 벽)를 향하고, tb4 spawn 이 도크를 로봇 앞(+x)=벽쪽에 둔다.
# x=5.70 → 도크 뒷면이 우측 벽(x=6.0)에 거의 닿는다.
ROBOT_SPAWNS = {
    'robot1': (5.70, 4.05, 0.0),
    'robot2': (5.70, 3.35, 0.0),
}

HEADER = f"""<?xml version="1.0"?>
<sdf version='1.8'>
    <world name='{WORLD_NAME}'>
        <physics name='1ms' type='ignored'>
            <max_step_size>0.003</max_step_size>
            <real_time_factor>1</real_time_factor>
            <real_time_update_rate>1000</real_time_update_rate>
        </physics>
        <plugin name='ignition::gazebo::systems::Physics' filename='ignition-gazebo-physics-system' />
        <plugin name='ignition::gazebo::systems::UserCommands' filename='ignition-gazebo-user-commands-system' />
        <plugin name='ignition::gazebo::systems::SceneBroadcaster' filename='ignition-gazebo-scene-broadcaster-system' />
        <plugin name='ignition::gazebo::systems::Contact' filename='ignition-gazebo-contact-system' />
        <light name='sun' type='directional'>
            <cast_shadows>1</cast_shadows>
            <pose>0 0 10 0 -0 0</pose>
            <diffuse>0.8 0.8 0.8 1</diffuse>
            <specular>0.2 0.2 0.2 1</specular>
            <attenuation><range>1000</range><constant>0.9</constant><linear>0.01</linear><quadratic>0.001</quadratic></attenuation>
            <direction>-0.5 0.1 -0.9</direction>
            <spot><inner_angle>0</inner_angle><outer_angle>0</outer_angle><falloff>0</falloff></spot>
        </light>
        <gravity>0 0 -9.8</gravity>
        <magnetic_field>6e-06 2.3e-05 -4.2e-05</magnetic_field>
        <atmosphere type='adiabatic' />
        <scene><ambient>0.4 0.4 0.4 1</ambient><background>0.7 0.7 0.7 1</background><shadows>1</shadows></scene>
        <model name='ground_plane'>
            <static>1</static>
            <link name='link'>
                <collision name='collision'><geometry><plane><normal>0 0 1</normal><size>100 100</size></plane></geometry>
                    <surface><friction><ode /></friction><bounce /><contact /></surface></collision>
                <visual name='visual'><geometry><plane><normal>0 0 1</normal><size>100 100</size></plane></geometry>
                    <material><ambient>0.8 0.8 0.8 1</ambient><diffuse>0.8 0.8 0.8 1</diffuse><specular>0.8 0.8 0.8 1</specular></material></visual>
            </link>
            <pose>0 0 0 0 -0 0</pose>
        </model>
"""


def box_link(name, cx, cy, cz, sx, sy, sz, rgb, yaw=0.0, collision=True):
    size = f'{sx:.4f} {sy:.4f} {sz:.4f}'
    col = (f"                <collision name='col'><geometry><box><size>{size}"
           f"</size></box></geometry></collision>\n") if collision else ''
    return (
        f"            <link name='{name}'>\n"
        f"                <pose>{cx:.4f} {cy:.4f} {cz:.4f} 0 0 {yaw:.5f}</pose>\n"
        f"{col}"
        f"                <visual name='vis'><geometry><box><size>{size}</size></box></geometry>"
        f"<material><ambient>{rgb} 1</ambient><diffuse>{rgb} 1</diffuse><specular>0.2 0.2 0.2 1</specular></material></visual>\n"
        f"            </link>\n"
    )


def make_walls():
    parts = ["        <model name='walls'>\n            <static>true</static>\n"]
    for i, (ax, ay, bx, by) in enumerate(wall_segments()):
        dx, dy = bx - ax, by - ay
        length = (dx * dx + dy * dy) ** 0.5 + T
        yaw = float(np.arctan2(dy, dx))
        parts.append(box_link(f'wall{i}', (ax + bx) / 2, (ay + by) / 2, HGT / 2,
                              length, T, HGT, WALL_RGB, yaw))
    parts.append("        </model>\n")
    return ''.join(parts)


def make_beds():
    parts = ["        <model name='beds'>\n            <static>true</static>\n"]
    for nm, cx, cy, yaw in BEDS:
        parts.append(box_link(nm, cx, cy, BED_H / 2, BED_L, BED_W, BED_H,
                              '0.40 0.55 0.80', yaw))
    parts.append("        </model>\n")
    return ''.join(parts)


def preview():
    S = 14
    pw, ph = int(W * S) + 1, int(H * S) + 1
    c = np.full((ph, pw), ' ')
    for ax, ay, bx, by in wall_segments():
        n = int(max(abs(bx - ax), abs(by - ay)) * S) + 1
        for t in np.linspace(0, 1, n):
            x, y = ax + (bx - ax) * t, ay + (by - ay) * t
            px, py = int(x * S), int((H - y) * S)
            if 0 <= py < ph and 0 <= px < pw:
                c[py, px] = '#'
    for nm, cx, cy, yaw in BEDS:
        px, py = int(cx * S), int((H - cy) * S)
        if 0 <= py < ph and 0 <= px < pw:
            c[py, px] = 'B'
    for nm, (cx, cy, yaw) in ROBOT_SPAWNS.items():
        px, py = int(cx * S), int((H - cy) * S)
        if 0 <= py < ph and 0 <= px < pw:
            c[py, px] = nm[-1]
    print('  ' + '좌하단=(0,0)  # 벽  B 침대  1/2 로봇 spawn')
    for r in range(ph):
        print('  ' + ''.join(c[r, :]))


def main():
    if '--preview' in sys.argv:
        preview()
        return
    body = make_walls() + make_beds()
    with open(OUT, 'w') as f:
        f.write(HEADER + body + "    </world>\n</sdf>\n")
    print(f'전체 {W} x {H} m | 병실 2개 + 도킹 + 약보관실 | 침대 {len(BEDS)}개({BED_L}x{BED_W}x{BED_H})')
    print(f'로봇 spawn 권장: robot1 {ROBOT_SPAWNS["robot1"]}, robot2 {ROBOT_SPAWNS["robot2"]}')
    print(f'✅ {OUT}')


if __name__ == '__main__':
    main()
