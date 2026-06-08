#!/usr/bin/env python3
"""capture_gui — robot6(192.168.109.106) OAK-D compressed RGB 뷰어 + YOLO11 데이터셋 캡처.

기능
  · robot6 의 compressed RGB(/robot6/oakd/rgb/image_raw/compressed)만 구독해 ~10fps 표시.
  · 시작 시 dualsense_teleop 을 자동 기동(robot6 수동 주행 — DualSense → /robot6/cmd_vel).
  · [캡처] 토글 ON → 0.5초마다 1장씩 dataset/ 에 저장(YOLO11 학습 이미지용).

실행(로봇 연결 위해 ROS env·discovery 필요):
  source /opt/ros/humble/setup.bash
  source ~/rokey_ws/install/setup.bash               # dualsense_teleop 패키지
  source ~/rokey_ws/src/intel1/common/discovery.sh   # robot6(.106) 디스커버리(도메인6)
  python3 ~/MediCart/medicart_ws/src/temp/capture_gui.py

주의: dualsense_teleop 은 실제 robot6 을 움직입니다(조작자 컨트롤). 컨트롤러 페어링 필요.
"""
import os
import subprocess
import threading
import time
import tkinter as tk

ROBOT_ENV = "/home/rokey/MediCart/common/robot.env"


def _setup_discovery_env(robot_env=ROBOT_ENV):
    """robot.env 를 읽어 FastDDS 디스커버리 서버 env 를 self-config (rclpy.init 이전 필수).

    로봇이 디스커버리 서버 뒤에 있어, RMW=rmw_fastrtps_cpp + ROS_DISCOVERY_SERVER 가
    없으면 기본 멀티캐스트로는 토픽을 못 찾는다(=0 수신). 셸 소싱 의존을 없앤다.
    """
    cfg = {}
    try:
        with open(robot_env) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    cfg[k.strip()] = v.strip()
    except OSError:
        return os.environ.get("ROBOT_NAMESPACE", "robot6").strip("/")
    ns = cfg.get("ROBOT_NAMESPACE", "robot6").strip("/")
    ip = cfg.get("DISCOVERY_IP", "")
    sid = int(cfg.get("DISCOVERY_SERVER_ID", "0") or 0)
    os.environ.setdefault("RMW_IMPLEMENTATION", "rmw_fastrtps_cpp")
    os.environ["ROS_DOMAIN_ID"] = cfg.get("ROBOT_DOMAIN_ID", os.environ.get("ROS_DOMAIN_ID", "0"))
    os.environ["ROS_SUPER_CLIENT"] = "True"
    if ip:                                  # ;*sid + ip:11811; (server-id = sid)
        os.environ["ROS_DISCOVERY_SERVER"] = ";" * sid + f"{ip}:11811;"
    return ns


# 디스커버리 env 를 import/init 이전에 설정(아래 NS 할당 시 적용).
import cv2
import numpy as np
import rclpy
from PIL import Image, ImageTk
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import CompressedImage

NS = _setup_discovery_env()
RGB_TOPIC = f"/{NS}/oakd/rgb/image_raw/compressed"
SAVE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dataset")
SAVE_PERIOD = 0.5          # 초당 2장(0.5s 간격)
DISPLAY_MS = 100           # ~10fps 표시
JPEG_QUALITY = 92
_QOS = QoSProfile(depth=5, reliability=ReliabilityPolicy.BEST_EFFORT,
                  durability=DurabilityPolicy.VOLATILE)


class RgbSubscriber(Node):
    """compressed RGB 만 구독해 최신 BGR 프레임을 보관."""

    def __init__(self):
        super().__init__("temp_capture_gui")
        self.latest = None        # 최신 BGR numpy
        self._lock = threading.Lock()
        self.create_subscription(CompressedImage, RGB_TOPIC, self._on_rgb, _QOS)
        self.get_logger().info(f"[capture_gui] 구독: {RGB_TOPIC}")

    def _on_rgb(self, msg):
        try:
            img = cv2.imdecode(np.frombuffer(msg.data, np.uint8), cv2.IMREAD_COLOR)
        except Exception as exc:                       # noqa: BLE001
            self.get_logger().warn(f"rgb decode 실패: {exc}", throttle_duration_sec=3.0)
            return
        if img is not None:
            with self._lock:
                self.latest = img

    def get_frame(self):
        with self._lock:
            return None if self.latest is None else self.latest.copy()


class CaptureGUI:
    def __init__(self, node):
        self.node = node
        self.capturing = False
        self.count = 0
        self._last_save = 0.0
        os.makedirs(SAVE_DIR, exist_ok=True)

        self.root = tk.Tk()
        self.root.title(f"capture_gui — {NS} RGB / YOLO11 dataset")
        self.video = tk.Label(self.root, bg="black")
        self.video.pack(padx=6, pady=6)

        bar = tk.Frame(self.root)
        bar.pack(fill="x", padx=6, pady=(0, 6))
        self.toggle_btn = tk.Button(bar, text="캡처 시작", width=14, command=self._toggle,
                                    bg="#0ca39a", fg="white", font=("", 12, "bold"))
        self.toggle_btn.pack(side="left")
        self.status = tk.Label(bar, text="대기 중", anchor="w")
        self.status.pack(side="left", padx=10)

        # dualsense teleop 자동 기동
        self.teleop = self._start_teleop()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(DISPLAY_MS, self._tick)

    def _start_teleop(self):
        cmd = ["ros2", "run", "dualsense_teleop", "teleop",
               "--ros-args", "-p", f"namespace:={NS}"]
        try:
            p = subprocess.Popen(cmd, env=os.environ.copy())
            self.node.get_logger().info(f"[capture_gui] dualsense_teleop 기동: {' '.join(cmd)}")
            return p
        except Exception as exc:                       # noqa: BLE001
            self.node.get_logger().warn(
                f"[capture_gui] teleop 기동 실패({exc}) — rokey_ws source 확인. 캡처는 가능.")
            return None

    def _toggle(self):
        self.capturing = not self.capturing
        self.toggle_btn.config(text="캡처 정지" if self.capturing else "캡처 시작",
                               bg="#df4448" if self.capturing else "#0ca39a")

    def _tick(self):
        frame = self.node.get_frame()
        if frame is not None:
            now = time.monotonic()
            # 0.5초마다 저장(토글 ON)
            if self.capturing and (now - self._last_save) >= SAVE_PERIOD:
                self._last_save = now
                fn = os.path.join(SAVE_DIR, time.strftime("frame_%Y%m%d_%H%M%S_") +
                                  f"{int((now * 1000) % 1000):03d}.jpg")
                cv2.imwrite(fn, frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
                self.count += 1
            # 표시(BGR→RGB)
            disp = frame
            h, w = disp.shape[:2]
            if w > 640:
                disp = cv2.resize(disp, (640, int(h * 640 / w)))
            rgb = cv2.cvtColor(disp, cv2.COLOR_BGR2RGB)
            imgtk = ImageTk.PhotoImage(Image.fromarray(rgb))
            self.video.imgtk = imgtk
            self.video.config(image=imgtk)
            state = "● 캡처 중" if self.capturing else "수신 중"
        else:
            state = "프레임 대기(로봇/디스커버리 확인)"
        self.status.config(text=f"{state} · 저장 {self.count}장 → {SAVE_DIR}")
        self.root.after(DISPLAY_MS, self._tick)

    def _on_close(self):
        self.capturing = False
        if self.teleop is not None:
            try:
                self.teleop.terminate()
            except Exception:                          # noqa: BLE001
                pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    rclpy.init()
    node = RgbSubscriber()
    spin = threading.Thread(target=rclpy.spin, args=(node,), daemon=True)
    spin.start()
    gui = CaptureGUI(node)
    try:
        gui.run()
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
