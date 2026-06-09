#!/usr/bin/env python3
"""robot6_bringup — MediCart robot6측 노드 일괄 기동.

기동 노드:
  · db_bridge/db_node            — RTDB mission_pool ↔ ROS 브리지(웹 명령 수신)
  · mission_manager/mission_manager_node — 모드 중재 허브 + goto(NavExecutor) + 시스템명령
  · (선택) nurse_tracker/tracker_node    — round(추종) 모드     [nurse_tracker:=true]
  · (선택) obstacle_detector/obstacle_node — 바닥 요철 감지      [obstacle_detector:=true]

선행(이 런치에 포함 안 됨 — turtlebot4 패키지, RViz 초기 pose 인터랙션 필요):
  loc 6 ~/MediCart/medicart_ws/maps/ninety.yaml   # localization(AMCL)
  rv 6                                            # RViz → 2D Pose Estimate 로 초기 pose
  nav 6                                           # Nav2 → /robot6/navigate_to_pose 제공

선행 env(실행 전):  source ~/MediCart/common/discovery.sh   # robot6·도메인6·디스커버리
파라미터 기본값은 env(ROBOT_NAMESPACE/DISCOVERY_IP/FB_CRED/FB_DB_URL)에서 채워지며,
없으면 아래 폴백을 사용한다.
"""
import os

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

# env 폴백(common/robot.env + 시크릿 경로 기준).
_NS = os.environ.get("ROBOT_NAMESPACE", "robot6")
_DISCOVERY_IP = os.environ.get("DISCOVERY_IP", "192.168.109.106")
_FB_CRED = os.environ.get("FB_CRED", "/home/rokey/secrets/serviceAccountKey.json")
_FB_DB_URL = os.environ.get(
    "FB_DB_URL",
    "https://medi-cart-ea39f-default-rtdb.asia-southeast1.firebasedatabase.app")


def generate_launch_description():
    use_tracker = LaunchConfiguration("nurse_tracker")
    use_obstacle = LaunchConfiguration("obstacle_detector")

    return LaunchDescription([
        DeclareLaunchArgument("nurse_tracker", default_value="false",
                              description="round(추종) 모드 tracker_node 동시 기동"),
        DeclareLaunchArgument("obstacle_detector", default_value="false",
                              description="바닥 요철 감지 obstacle_node 동시 기동"),

        # 웹→로봇 명령 브리지(RTDB mission_pool 대기).
        Node(package="db_bridge", executable="db_node", name="db_node", output="screen",
             parameters=[{"namespace": _NS, "fb_cred": _FB_CRED, "fb_db_url": _FB_DB_URL}]),

        # 모드 중재 허브(goto/NavExecutor + 시스템명령 + cmd_vel 단독소유).
        Node(package="mission_manager", executable="mission_manager_node",
             name="mission_manager_node", output="screen",
             parameters=[{"namespace": _NS, "discovery_ip": _DISCOVERY_IP}]),

        # 선택: round 추종 모드.
        Node(package="nurse_tracker", executable="tracker_node", name="tracker_node",
             output="screen", condition=IfCondition(use_tracker),
             parameters=[{"namespace": _NS}]),

        # 선택: 바닥 요철 감지.
        Node(package="obstacle_detector", executable="obstacle_node", name="obstacle_node",
             output="screen", condition=IfCondition(use_obstacle),
             parameters=[{"namespace": _NS}]),
    ])
