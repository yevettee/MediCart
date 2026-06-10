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
    front_cone_deg = float(LaunchConfiguration('front_cone_deg').perform(context))
    lidar_stop = float(LaunchConfiguration('lidar_stop').perform(context))
    depth_stop = float(LaunchConfiguration('depth_stop').perform(context))

    db_params = [{'namespace': ns, 'fb_cred': fb_cred, 'fb_db_url': fb_db_url}]

    return [
        Node(package='db_bridge', executable='db_node',
             name='db_node', output='screen', parameters=db_params),

        Node(package='mission_manager', executable='mission_manager_node',
             name='mission_manager_node', output='screen',
             parameters=[{
                 'namespace': ns,
                 'discovery_ip': discovery_ip,
                 # round 추종은 Nav2가 아니라 reactive cmd_vel이라 좁은 통로에서
                 # 정면 안전 게이트가 너무 넓으면 oscillation/정지가 생긴다.
                 'front_cone_deg': front_cone_deg,
                 'lidar_stop': lidar_stop,
                 'depth_stop': depth_stop,
             }]),
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
        DeclareLaunchArgument(
            'front_cone_deg',
            default_value='14.0',
            description='round safety gate LiDAR 정면 cone 반각(deg), 좁은 통로용 기본값'),
        DeclareLaunchArgument(
            'lidar_stop',
            default_value='0.18',
            description='round safety gate 전진 차단 LiDAR 거리(m), 좁은 통로용 기본값'),
        DeclareLaunchArgument(
            'depth_stop',
            default_value='0.20',
            description='round safety gate 전진 차단 depth 거리(m)'),
        DeclareLaunchArgument(
            'desired_distance',
            default_value='0.30',
            description='간호사 cmd_vel 추종 유지 거리(m)'),
        DeclareLaunchArgument(
            'deadband',
            default_value='0.12',
            description='추종 거리 deadband(m), 이 안에서는 전후진 정지'),
        DeclareLaunchArgument(
            'max_lin',
            default_value='0.05',
            description='round direct cmd_vel 최대 선속도(m/s)'),
        DeclareLaunchArgument(
            'max_ang',
            default_value='0.25',
            description='round direct cmd_vel 최대 각속도(rad/s)'),
        DeclareLaunchArgument(
            'tracking_speed_limit',
            default_value='0.08',
            description='round_nav 추종 중 Nav2 선속도 제한(m/s), 0이면 제한 해제'),
        DeclareLaunchArgument(
            'speed_limit_topic',
            default_value='',
            description='Nav2 controller speed_limit topic, 비우면 /<namespace>/speed_limit'),
        DeclareLaunchArgument(
            'base_frame',
            default_value='base_link',
            description='추종 좌표 변환에 사용할 로봇 base TF frame'),
        DeclareLaunchArgument(
            'angle_deadzone',
            default_value='0.45',
            description='이 각도(rad) 이상이면 회전만 수행. 값이 클수록 전진+회전을 허용'),
        DeclareLaunchArgument(
            'round_nav_follower',
            default_value='false',
            description='Nav2 goal 기반 round_nav follower 기동 여부(기본 false: direct cmd_vel 사용)'),
        DeclareLaunchArgument(
            'goal_update_period',
            default_value='0.5',
            description='round_nav Nav2 goal 최소 갱신 주기(s)'),
        DeclareLaunchArgument(
            'goal_shift_min',
            default_value='0.15',
            description='round_nav goal 재전송 최소 위치 변화(m)'),
        Node(
            package='nurse_tracker', executable='tracker_node',
            name='tracker_node', output='screen',
            namespace=LaunchConfiguration('namespace'),
            condition=IfCondition(LaunchConfiguration('nurse_tracker')),
            remappings=[('/tf', 'tf'), ('/tf_static', 'tf_static')],
            parameters=[{
                'namespace': LaunchConfiguration('namespace'),
                'base_frame': LaunchConfiguration('base_frame'),
                'desired_distance': LaunchConfiguration('desired_distance'),
                'deadband': LaunchConfiguration('deadband'),
                'angle_deadzone': LaunchConfiguration('angle_deadzone'),
                'max_lin': LaunchConfiguration('max_lin'),
                'max_ang': LaunchConfiguration('max_ang'),
            }]),
        Node(
            package='nurse_tracker', executable='nav_goal_follower_node',
            name='nav_goal_follower_node', output='screen',
            namespace=LaunchConfiguration('namespace'),
            condition=IfCondition(LaunchConfiguration('round_nav_follower')),
            remappings=[('/tf', 'tf'), ('/tf_static', 'tf_static')],
            parameters=[{
                'namespace': LaunchConfiguration('namespace'),
                'base_frame': LaunchConfiguration('base_frame'),
                'desired_distance': LaunchConfiguration('desired_distance'),
                'goal_update_period': LaunchConfiguration('goal_update_period'),
                'goal_shift_min': LaunchConfiguration('goal_shift_min'),
                'tracking_speed_limit': LaunchConfiguration('tracking_speed_limit'),
                'speed_limit_topic': LaunchConfiguration('speed_limit_topic'),
            }]),
        OpaqueFunction(function=launch_setup),
    ])
