#!/usr/bin/env python3
"""MediCart 워크플로우 .drawio 생성기 (drawio MCP 미연결 → XML 직접 작성).

데이터 기반: 레인(컬럼)·노드(레인,행)·엣지(라벨)를 정의하면 좌표를 계산 배치해
겹침 없이 mxGraph XML 3개를 출력한다. 내용은 medicart_ws/ocr_ws 실제 코드 기준.

실행: python3 docs/architecture/diagrams/gen_workflow_drawio.py
"""
import html
import os

LANE_W, LANE_GAP, LANE_X0 = 270, 300, 40
BOX_W, ROW_H, ROW_Y0 = 234, 150, 95
TOP = 48

LANE_COLORS = ["#E8F0FE", "#FFF4E5", "#E6F4F1", "#EFE9FB", "#E9F7EA", "#F0F0F2"]
LANE_STROKE = ["#9CC0F5", "#F0B274", "#7FBFB3", "#B49AE0", "#8FCF92", "#B8B8C0"]
NODE_FILL = ["#D2E3FC", "#FFE0B2", "#C7E9E2", "#DDD0F5", "#CDEFCF", "#E2E2E8"]
NODE_STROKE = ["#5B8DEF", "#E08E3C", "#3FA796", "#8A63D2", "#5BB85F", "#9A9AA8"]


def esc(s):
    return html.escape(str(s), quote=True).replace("\n", "&#10;")


def lane_x(i):
    return LANE_X0 + i * LANE_GAP


def row_y(r):
    return ROW_Y0 + r * ROW_H


def node_h(subs):
    return max(58, 30 + 16 * (1 + len(subs)))


def build(diagram_name, lanes, nodes, edges, legend):
    # nodes: dict id -> (lane, row, title, [subs])
    max_row = max(n[1] for n in nodes.values())
    height = row_y(max_row) + node_h([1, 2]) + 90
    width = lane_x(len(lanes) - 1) + LANE_W + 40
    cells = []
    cid = [2]

    def nid():
        cid[0] += 1
        return f"c{cid[0]}"

    # lane backgrounds
    for i, title in enumerate(lanes):
        x = lane_x(i)
        style = (f"rounded=0;html=0;fillColor={LANE_COLORS[i % len(LANE_COLORS)]};"
                 f"strokeColor={LANE_STROKE[i % len(LANE_STROKE)]};opacity=55;"
                 f"verticalAlign=top;align=center;fontStyle=1;fontSize=13;fontColor=#333333")
        cells.append(
            f'<mxCell id="lane{i}" value="{esc(title)}" style="{style}" vertex="1" parent="1">'
            f'<mxGeometry x="{x}" y="{TOP}" width="{LANE_W}" height="{height - TOP - 20}" as="geometry"/></mxCell>')

    # legend (top-right)
    lx = width - 300
    cells.append(
        f'<mxCell id="legend" value="{esc(legend)}" '
        f'style="rounded=1;html=0;whiteSpace=wrap;align=left;verticalAlign=top;spacing=8;'
        f'fillColor=#FFFFFF;strokeColor=#999999;fontSize=10;dashed=1" vertex="1" parent="1">'
        f'<mxGeometry x="{lx}" y="6" width="290" height="78" as="geometry"/></mxCell>')

    # nodes
    for node_id, (lane, row, title, subs) in nodes.items():
        x = lane_x(lane) + (LANE_W - BOX_W) // 2
        y = row_y(row)
        h = node_h(subs)
        val = title + ("\n" + "\n".join("· " + s for s in subs) if subs else "")
        style = (f"rounded=1;html=0;whiteSpace=wrap;align=left;verticalAlign=top;spacing=7;"
                 f"fillColor={NODE_FILL[lane % len(NODE_FILL)]};"
                 f"strokeColor={NODE_STROKE[lane % len(NODE_STROKE)]};fontSize=11")
        cells.append(
            f'<mxCell id="{node_id}" value="{esc(val)}" style="{style}" vertex="1" parent="1">'
            f'<mxGeometry x="{x}" y="{y}" width="{BOX_W}" height="{h}" as="geometry"/></mxCell>')

    # edges
    for src, dst, label, *opt in edges:
        dashed = "dashed=1;" if (opt and "dash" in opt[0]) else ""
        loop = (opt and "loop" in opt[0])
        style = (f"edgeStyle=orthogonalEdgeStyle;rounded=1;html=0;{dashed}"
                 f"fontSize=9;fontColor=#222222;strokeColor=#666666;endArrow=block;"
                 f"labelBackgroundColor=#FFFFFF;jettySize=auto;orthogonalLoop=1")
        geo = '<mxGeometry relative="1" as="geometry"/>'
        if loop:
            geo = ('<mxGeometry relative="1" as="geometry">'
                   '<Array as="points"><mxPoint x="0" y="0"/></Array></mxGeometry>')
        cells.append(
            f'<mxCell id="{nid()}" value="{esc(label)}" style="{style}" edge="1" parent="1" '
            f'source="{src}" target="{dst}">{geo}</mxCell>')

    body = "\n".join(cells)
    return (
        f'<mxfile host="app.diagrams.net">\n'
        f'<diagram name="{esc(diagram_name)}">\n'
        f'<mxGraphModel dx="1400" dy="900" grid="1" gridSize="10" guides="1" '
        f'tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" '
        f'pageWidth="{width}" pageHeight="{height}" math="0" shadow="0">\n'
        f'<root><mxCell id="0"/><mxCell id="1" parent="0"/>\n{body}\n</root>\n'
        f'</mxGraphModel></diagram></mxfile>\n')


def build_tiered(diagram_name, tiers, meta, edges, legend):
    """수평 밴드(티어) 레이아웃 — 허브 토폴로지용(위→아래 계층, 흐름이 대부분 수직).
    tiers: [(title, color_idx, [node_id...])], meta: id->(title,[subs]). 노드는 밴드 내 좌→우 균등 배치."""
    TBOX_W, TGAP, BAND_TITLE, BAND_PAD, BAND_VGAP, TOP_T = 240, 48, 28, 16, 52, 86

    def tier_w(ids):
        return len(ids) * TBOX_W + (len(ids) - 1) * TGAP

    band_h = [max(node_h(meta[i][1]) for i in ids) + BAND_TITLE + BAND_PAD for _, _, ids in tiers]
    content_w = max(tier_w(ids) for _, _, ids in tiers)
    width = content_w + 120
    ys, y = [], TOP_T
    for bh in band_h:
        ys.append(y)
        y += bh + BAND_VGAP
    height = y + 20
    cells, cid = [], [2]

    def nid():
        cid[0] += 1
        return f"t{cid[0]}"

    for ti, (ttitle, col, ids) in enumerate(tiers):
        by, bh = ys[ti], band_h[ti]
        c = col % len(LANE_COLORS)
        bstyle = (f"rounded=0;html=0;fillColor={LANE_COLORS[c]};strokeColor={LANE_STROKE[c]};"
                  f"opacity=55;verticalAlign=top;align=left;spacingLeft=12;spacingTop=6;"
                  f"fontStyle=1;fontSize=13;fontColor=#333333")
        cells.append(
            f'<mxCell id="band{ti}" value="{esc(ttitle)}" style="{bstyle}" vertex="1" parent="1">'
            f'<mxGeometry x="40" y="{by}" width="{width - 80}" height="{bh}" as="geometry"/></mxCell>')
        tw = tier_w(ids)
        sx = (width - tw) // 2
        for i, node_id in enumerate(ids):
            t, subs = meta[node_id]
            x = sx + i * (TBOX_W + TGAP)
            ny = by + BAND_TITLE
            h = node_h(subs)
            val = t + ("\n" + "\n".join("· " + s for s in subs) if subs else "")
            nstyle = (f"rounded=1;html=0;whiteSpace=wrap;align=left;verticalAlign=top;spacing=7;"
                      f"fillColor={NODE_FILL[c]};strokeColor={NODE_STROKE[c]};fontSize=11")
            cells.append(
                f'<mxCell id="{node_id}" value="{esc(val)}" style="{nstyle}" vertex="1" parent="1">'
                f'<mxGeometry x="{x}" y="{ny}" width="{TBOX_W}" height="{h}" as="geometry"/></mxCell>')

    cells.append(
        f'<mxCell id="legend" value="{esc(legend)}" '
        f'style="rounded=1;html=0;whiteSpace=wrap;align=left;verticalAlign=top;spacing=8;'
        f'fillColor=#FFFFFF;strokeColor=#999999;fontSize=10;dashed=1" vertex="1" parent="1">'
        f'<mxGeometry x="40" y="8" width="460" height="62" as="geometry"/></mxCell>')

    for src, dst, label, *opt in edges:
        dashed = "dashed=1;" if (opt and "dash" in opt[0]) else ""
        style = (f"edgeStyle=orthogonalEdgeStyle;rounded=1;html=0;{dashed}"
                 f"fontSize=9;fontColor=#222222;strokeColor=#666666;endArrow=block;"
                 f"labelBackgroundColor=#FFFFFF;jettySize=auto;orthogonalLoop=1")
        cells.append(
            f'<mxCell id="{nid()}" value="{esc(label)}" style="{style}" edge="1" parent="1" '
            f'source="{src}" target="{dst}"><mxGeometry relative="1" as="geometry"/></mxCell>')

    body = "\n".join(cells)
    return (
        f'<mxfile host="app.diagrams.net">\n'
        f'<diagram name="{esc(diagram_name)}">\n'
        f'<mxGraphModel dx="1400" dy="900" grid="1" gridSize="10" guides="1" '
        f'tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" '
        f'pageWidth="{width}" pageHeight="{height}" math="0" shadow="0">\n'
        f'<root><mxCell id="0"/><mxCell id="1" parent="0"/>\n{body}\n</root>\n'
        f'</mxGraphModel></diagram></mxfile>\n')


# ============================================================================
# 다이어그램 1 — 간호사 투약 (robot6)
# ============================================================================
NC_LANES = ["Web (Next.js + Flask)", "Firebase RTDB", "db_bridge",
            "mission_manager", "nurse_tracker / mode", "nav / Create3 base"]
NC_NODES = {
    "n1": (0, 0, "홈: '간호사 투약'", ["page.tsx", "startRound(NURSE_CART_NS=robot6)"]),
    "n2": (0, 1, "Flask POST /api/nurse_cart/start", ["app.py", "push_mission(ns,'nurse_cart_mission')"]),
    "n3": (1, 2, "RTDB robot6/mission_pool", ["{action:nurse_cart_mission,", " status:pending}"]),
    "n4": (2, 3, "db_node (DbNode)", ["mission_queue.py", "firebase_client.py", "pool 폴링 → mission_request"]),
    "n5": (3, 4, "MissionManagerNode", ["action 디스패치", "mission_executor.py"]),
    "n6": (3, 5, "NurseCartSequencer", ["FSM: undock→약품실 goto", "→WAIT_OCR→추종→round→복귀"]),
    "n7": (5, 5, "NavExecutor", ["ActionClient", "navigate_to_pose / dock / undock"]),
    "n8": (0, 6, "처치실 /ocr (약품 OCR 검증)", ["ocr/page.tsx", "nurseCartOcrDone(robot6)"]),
    "n17": (4, 6, "ocr_detector (보조 ROS OCR)", ["ocr_node / web_node", "medicine_checker.py", "text_cleaner.py", "engines/easyocr|gcp"]),
    "n9": (1, 7, "RTDB robot6/nurse_cart/ocr_done", []),
    "n10": (2, 7, "db_node: ocr_done 브리지", ["RTDB flag → ROS String"]),
    "n11": (3, 8, "ModeArbiter", ["mode_arbitration.py", "arbitrate / safety_gate", "cmd_vel 단독소유·선점"]),
    "n12": (4, 8, "tracker_node (nurse_tracker)", ["perception.py → yolo_helper.py", "follow_control.py (85cm 유지)", "srv /robot6/start_tracking"]),
    "n13": (5, 9, "Create3 base (TurtleBot4)", ["/robot6/cmd_vel", "dock / undock action"]),
    "n18": (2, 5, "camera_bridge", ["annotated_image → RTDB", "firebase_client.py"]),
    "n14": (0, 9, "회진 완료 (round_done)", ["RoundOverlay", "nurseCartRoundDone(robot6)"]),
    "n15": (1, 10, "RTDB robot6/nurse_cart/round_done", []),
    "n16": (2, 10, "db_node: round_done 브리지", ["RTDB flag → ROS String"]),
}
NC_EDGES = [
    ("n1", "n2", "POST"),
    ("n2", "n3", "RTDB write (firebase-admin)"),
    ("n3", "n4", "poll mission_pool"),
    ("n4", "n5", "/robot6/mission_request (String)"),
    ("n5", "n6", "NURSE_CART_ACTION"),
    ("n6", "n7", "undock→goto 약품실 (NavigateToPose)"),
    ("n8", "n9", "set ocr_done"),
    ("n17", "n8", "OCR 결과 (옵션)", "dash"),
    ("n9", "n10", "read"),
    ("n10", "n6", "/robot6/nurse_cart/ocr_done → signal_ocr_done"),
    ("n6", "n11", "추종 모드 engage (/robot6/mode/nurse_tracker/set, latched)"),
    ("n11", "n12", "activate"),
    ("n12", "n11", "/robot6/mode/nurse_tracker/cmd_vel (Twist)"),
    ("n11", "n13", "/robot6/cmd_vel (Twist, 우선순위 게이트)"),
    ("n12", "n18", "/nurse_tracker/annotated_image (Image)"),
    ("n7", "n13", "dock/undock (Action)"),
    ("n14", "n15", "set round_done"),
    ("n15", "n16", "read"),
    ("n16", "n6", "/robot6/nurse_cart/round_done → signal_round_done → 복귀+dock"),
]
NC_LEGEND = ("범례: ns=robot6 (간호사 투약 전담)\n"
             "실선=토픽/액션·동기 호출, 점선=옵션 경로\n"
             "RTDB는 크로스-PC 버스(웹↔ROS)")

# ============================================================================
# 다이어그램 2 — 순회 문진 (robot3)
# ============================================================================
PI_LANES = ["Web (Next.js + Flask)", "Firebase RTDB", "db_bridge",
            "mission_manager", "patient_identifier / rooms", "nav / Create3 base"]
PI_NODES = {
    "p1": (0, 0, "홈: '순회 문진 시작'", ["page.tsx", "RoundsIntakeOverlay (PATROL_NS=robot3)"]),
    "p2": (0, 1, "Flask POST /api/patrol/start", ["app.py", "clear + reset_patrol", "startPatrol(ns,{stops,home})"]),
    "p3": (1, 2, "RTDB robot3/mission_pool", ["{action:patrol_intake_mission,", " params:{stops,home}}"]),
    "p4": (2, 3, "db_node (DbNode)", ["pool 폴링 → mission_request", "firebase_client.py"]),
    "p5": (3, 4, "MissionManagerNode", ["PATROL_INTAKE_ACTION 디스패치"]),
    "p6": (3, 5, "PatrolIntakeSequencer", ["FSM: undock → [정차 루프]", "→ 복귀 + dock"]),
    "p7": (5, 5, "NavExecutor", ["navigate_to_pose / dock / undock"]),
    "p14": (4, 4, "patient_identifier (ROS측 식별 옵션)", ["identifier_node.py", "patient_validator.py", "PersonDetector / webcam_node"]),
    "p9": (4, 6, "rooms_server (ListRooms srv)", ["room_lookup.py", "firebase_client.py"]),
    "p8": (0, 6, "정차 도착 → QR 배정환자 검증", ["QrScanner / useQrScanner", "verifyIdentify / getPatient"]),
    "p10": (0, 7, "문진 작성 / 부재중", ["IntakeForm", "setIntakeStatus / addVisit"]),
    "p11": (0, 8, "다음 정차 (advance)", ["sendPatrolAdvance", "POST /api/patrol/advance"]),
    "p12": (1, 9, "RTDB robot3/patrol (phase, intake_done)", []),
    "p13": (2, 9, "db_node: intake_done 브리지", ["RTDB flag → ROS String"]),
    "p15": (3, 8, "ModeArbiter (cmd_vel 게이트)", ["mode_arbitration.py", "arbitrate / safety_gate"]),
    "p16": (5, 9, "Create3 base (TurtleBot4)", ["/robot3/cmd_vel", "dock / undock action"]),
}
PI_EDGES = [
    ("p1", "p2", "POST"),
    ("p2", "p3", "clear+reset+push (RTDB)"),
    ("p3", "p4", "poll mission_pool"),
    ("p4", "p5", "/robot3/mission_request (String)"),
    ("p5", "p6", "PATROL_INTAKE_ACTION"),
    ("p6", "p7", "undock → goto stop_i (NavigateToPose)"),
    ("p7", "p16", "nav / dock action"),
    ("p6", "p12", "phase=arrived (db_node→RTDB)"),
    ("p12", "p8", "웹 getPatrolPhase 폴링"),
    ("p8", "p10", "검증 통과 → 문진"),
    ("p10", "p11", "완료 / 부재중"),
    ("p11", "p12", "set advance / intake_done"),
    ("p12", "p13", "read"),
    ("p13", "p6", "/robot3/patrol/intake_done → 다음 stop"),
    ("p6", "p6", "stop_i++ 반복", "loop"),
    ("p6", "p15", "mode gate"),
    ("p15", "p16", "/robot3/cmd_vel (Twist)"),
    ("p14", "p9", "ListRooms (srv)", "dash"),
    ("p14", "p12", "PatientIdentified (옵션)", "dash"),
]
PI_LEGEND = ("범례: ns=robot3 (순회 문진 전담)\n"
             "정차 루프: goto→검증→문진→advance 반복\n"
             "점선=ROS측 자동 식별(웹 QR 대안)")

# ============================================================================
# 다이어그램 3 — 공통 인프라
# ============================================================================
CI_META = {
    "x1": ("Next.js 프론트", ["page/console/ocr/patients/intake/qr", "lib/api.ts · auth.ts(RBAC) · telemetry.ts", "MapView · overlays · middleware"]),
    "x2": ("Flask 백엔드 app.py", ["/api: amrs · stream(SSE) · map · targets · patients", "nurse_cart/* · patrol/* · intake · missions", "auth.py required_role_for_path · _req_ns"]),
    "x3": ("RTDB robot3 / robot6 (per-robot)", ["amcl_pose·odom·battery·dock_status·imu·scan", "robot_mode·online·stamp(ms)", "mission_pool · nurse_cart · patrol"]),
    "x4": ("RTDB 공유 노드", ["patients · rooms · targets", "display · intake_pending · ocr"]),
    "x5": ("amr_bridge", ["telemetry topics → RTDB", "firebase_client.py"]),
    "x7": ("camera_bridge", ["annotated · rgb/depth → RTDB"]),
    "x6": ("db_node", ["mission_pool → /ns/mission_request", "+ 3 핸드셰이크 브리지", "mission_queue.py"]),
    "x8": ("prescription_server", ["GetPrescription srv", "patient_lookup.py"]),
    "x9": ("rooms_server", ["ListRooms srv", "room_lookup.py"]),
    "x10": ("display_bridge", ["display/current → topic"]),
    "x11": ("MissionManagerNode", ["action 디스패치 · mission_executor", "/ns/mission_feedback"]),
    "x12": ("ModeArbiter (cmd_vel 단독소유)", ["mode_arbitration: arbitrate/safety_gate", "우선순위 선점/복귀", "/ns/mode/*/set|cmd_vel|status"]),
    "x13": ("NavExecutor + 베이스", ["navigate_to_pose / dock / undock", "/ns/cmd_vel"]),
    "x14": ("robot AMR (TurtleBot4 / Create3)", ["amcl_pose·scan·battery·dock_status pub", "OAK-D rgb/depth"]),
}
CI_TIERS = [
    ("Web (Next.js + Flask)", 0, ["x1", "x2"]),
    ("Firebase RTDB — 크로스-PC 버스", 1, ["x3", "x4"]),
    ("db_bridge — RTDB ↔ ROS 브리지", 2, ["x5", "x7", "x6", "x8", "x9", "x10"]),
    ("mission_manager 런타임", 3, ["x11", "x12", "x13"]),
    ("robot AMR (하드웨어)", 5, ["x14"]),
]
CI_EDGES = [
    ("x1", "x2", "HTTP fetch / SSE"),
    ("x2", "x3", "read/write (firebase-admin)"),
    ("x2", "x4", "read/write"),
    ("x14", "x5", "ROS 토픽 (amcl_pose, odom, scan, ...)"),
    ("x5", "x3", "write 텔레메트리"),
    ("x3", "x6", "poll mission_pool / flags"),
    ("x6", "x11", "/ns/mission_request (String)"),
    ("x11", "x6", "/ns/mission_feedback (String)"),
    ("x6", "x3", "ocr_done/round_done/intake_done 브리지"),
    ("x14", "x7", "rgb/depth/annotated"),
    ("x7", "x3", "camera → RTDB"),
    ("x8", "x3", "GetPrescription ← RTDB", "dash"),
    ("x9", "x4", "ListRooms ← RTDB rooms", "dash"),
    ("x10", "x4", "display read", "dash"),
    ("x11", "x12", "mode apply"),
    ("x12", "x13", "/ns/cmd_vel (게이트)"),
    ("x13", "x14", "dock/undock/nav (Action)"),
    ("x14", "x11", "/ns/scan (LaserScan)"),
]
CI_LEGEND = ("범례: {ns} = robot3 | robot6\n"
             "RTDB = 유일한 크로스-PC 버스\n"
             "점선=서비스(요청/응답), 실선=토픽/액션")

WORKFLOWS = [
    ("medicart-nurse-cart-workflow", "간호사 투약 워크플로우 (robot6)", NC_LANES, NC_NODES, NC_EDGES, NC_LEGEND),
    ("medicart-patrol-intake-workflow", "순회 문진 워크플로우 (robot3)", PI_LANES, PI_NODES, PI_EDGES, PI_LEGEND),
]

if __name__ == "__main__":
    out_dir = os.path.dirname(os.path.abspath(__file__))

    def write(fname, xml, count):
        path = os.path.join(out_dir, fname + ".drawio")
        with open(path, "w", encoding="utf-8") as f:
            f.write(xml)
        print(f"wrote {path}  ({count})")

    for fname, title, lanes, nodes, edges, legend in WORKFLOWS:
        write(fname, build(title, lanes, nodes, edges, legend),
              f"{len(nodes)} nodes, {len(edges)} edges, vertical-lane")
    # 공통 인프라 — 수평 티어 레이아웃(허브 토폴로지)
    write("medicart-common-infra",
          build_tiered("공통 인프라 (양 시나리오 공유)", CI_TIERS, CI_META, CI_EDGES, CI_LEGEND),
          f"{len(CI_META)} nodes, {len(CI_EDGES)} edges, tiered")
