#!/usr/bin/env python3
"""scenario_b.launch.py — 시나리오 B(간호사 카트) 앱 노드 일괄 기동.

띄우는 노드 (기본값, namespace=robot6):
  db_bridge:       db_node            — RTDB mission_pool ↔ ROS 브리지 (웹 미션 수신)
  mission_manager: mission_manager_node — 모드 중재 허브 + nurse_cart_sequencer
  nurse_tracker:   tracker_node       — round(간호사 추종) 모드 [nurse_tracker:=true 시 기동]

시나리오 B 플로우:
  웹 "시작" 버튼
    → RTDB mission_pool → db_node → mission_manager → nurse_cart_sequencer
    → GOTO_PHARMACY (undock + Nav2 이동)
    → WAIT_OCR      (phase=arrived → 웹 /ocr 페이지 자동 이동)
    → GOTO_STANDBY  (약품실 입구 대기 위치 이동)
    → START_ROUND   (tracker_node 간호사 추종 활성화)

전제(이 런치에 포함 안 됨 — turtlebot4 패키지 필요):
  loc 6 ~/MediCart/medicart_ws/maps/ninety.yaml   # localization (AMCL)
  rv  6                                           # RViz → 2D Pose Estimate 초기 pose
  nav 6                                           # Nav2 → /robot6/navigate_to_pose 제공

실행:
  source /opt/ros/humble/setup.bash
  source ~/MediCart/common/discovery.sh
  source ~/MediCart/medicart_ws/install/setup.bash

  # 기본 (db_node + mission_manager)
  ros2 launch mission_manager scenario_b.launch.py

  # 간호사 추종까지 포함
  ros2 launch mission_manager scenario_b.launch.py nurse_tracker:=true

  # OCR 완료 신호 수동 주입 (테스트용)
  python3 ~/MediCart/medicart_ws/src/mission_manager/scripts/inject_ocr_done.py
"""
import os

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

_DEFAULT_FB_CRED = '/home/rokey/MediCart/common/serviceAccountKey.json'
_DEFAULT_FB_DB_URL = (
    'https://medi-cart-ea39f-default-rtdb.asia-southeast1.firebasedatabase.app')


def launch_setup(context, *args, **kwargs):
    ns = LaunchConfiguration('namespace').perform(context).strip('/')
    fb_cred = LaunchConfiguration('fb_cred').perform(context)
    fb_db_url = LaunchConfiguration('fb_db_url').perform(context)
    discovery_ip = LaunchConfiguration('discovery_ip').perform(context)

    db_params = [{'namespace': ns, 'fb_cred': fb_cred, 'fb_db_url': fb_db_url}]

    return [
        Node(package='db_bridge', executable='db_node',
             name='db_node', output='screen', parameters=db_params),

        Node(package='mission_manager', executable='mission_manager_node',
             name='mission_manager_node', output='screen',
             parameters=[{'namespace': ns, 'discovery_ip': discovery_ip}]),
    ]


def generate_launch_description():
    _ns = os.environ.get('ROBOT_NAMESPACE', 'robot6')
    _discovery_ip = os.environ.get('DISCOVERY_IP', '')

    return LaunchDescription([
        DeclareLaunchArgument(
            'namespace',
            default_value=_ns,
            description='로봇 네임스페이스 (기본 env ROBOT_NAMESPACE, fallback robot6)'),
        DeclareLaunchArgument(
            'fb_cred',
            default_value=os.environ.get('FB_CRED', _DEFAULT_FB_CRED),
            description='Firebase 서비스계정 JSON 경로'),
        DeclareLaunchArgument(
            'fb_db_url',
            default_value=os.environ.get('FB_DB_URL', _DEFAULT_FB_DB_URL),
            description='Firebase RTDB databaseURL'),
        DeclareLaunchArgument(
            'discovery_ip',
            default_value=_discovery_ip,
            description='로봇 PC IP (ros_restart/reboot ssh 용, 미설정 시 시스템 명령 불가)'),
        DeclareLaunchArgument(
            'nurse_tracker',
            default_value='true',
            description='round(간호사 추종) tracker_node 동시 기동 여부'),
        Node(
            package='nurse_tracker', executable='tracker_node',
            name='tracker_node', output='screen',
            condition=IfCondition(LaunchConfiguration('nurse_tracker')),
            parameters=[{'namespace': _ns}]),
        OpaqueFunction(function=launch_setup),
    ])
