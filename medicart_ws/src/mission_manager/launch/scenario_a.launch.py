#!/usr/bin/env python3
"""scenario_a.launch.py — 시나리오 A(병실 순회 + QR 환자식별 + 문진표) 앱 노드 일괄 기동.

띄우는 노드(모두 namespace 파라미터로 동작 — 기본은 env ROBOT_NAMESPACE=robot3):
  db_bridge:        prescription_server (QR 환자/병실 DB검증)
                    rooms_server        (순찰 waypoint = ListRooms)
                    display_bridge      (patient_identified → RTDB display/current_patient)
                    db_node             (mission_pool → mission_request, 웹 순찰시작 트리거)
  mission_manager:  mission_manager_node (undock→patrol→dock 시퀀스 라우팅)
                    patrol_mode_node     (병상 순회 + dwell QR 스캔창)
  patient_identifier: identifier_node    (웹캠/카메라 QR 디코드)

전제(이 런치에 포함 안 됨 — 로봇/시뮬 브링업 따로):
  - Nav2 (patrol 의 NavigateToPose)
  - 카메라 노드: identifier 가 구독할 image_topic 을 발행해야 함
    (터틀봇4 웹캠이면 image_topic:=/{ns}/<webcam토픽> 으로 지정)

robot6 보호: namespace 기본값을 env(로컬 override=robot3)에서 가져오며, env 미설정 시
fallback 도 robot3 다. robot6 으로 돌리려면 명시적으로 namespace:=robot6 을 줘야 한다.

사용:
  source /opt/ros/humble/setup.bash
  source ~/MediCart/common/discovery.sh           # ROBOT_NAMESPACE/도메인/디스커버리
  source ~/MediCart/medicart_ws/install/setup.bash
  ros2 launch mission_manager scenario_a.launch.py
  # 웹캠 토픽 지정 예:
  ros2 launch mission_manager scenario_a.launch.py image_topic:=/robot3/webcam/image_raw
"""
import os

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

_DEFAULT_FB_CRED = '/home/rokey/MediCart/common/serviceAccountKey.json'
_DEFAULT_FB_DB_URL = (
    'https://medi-cart-ea39f-default-rtdb.asia-southeast1.firebasedatabase.app')


def launch_setup(context, *args, **kwargs):
    ns = LaunchConfiguration('namespace').perform(context).strip('/')
    fb_cred = LaunchConfiguration('fb_cred').perform(context)
    fb_db_url = LaunchConfiguration('fb_db_url').perform(context)
    image_topic = LaunchConfiguration('image_topic').perform(context).strip()
    start_db_node = LaunchConfiguration('start_db_node').perform(context).lower() == 'true'

    # image_topic 미지정 시 identifier 가 ns 로 만드는 기본값과 동일하게 채운다.
    if not image_topic:
        image_topic = f'/{ns}/oakd/rgb/image_raw'

    db_params = [{'namespace': ns, 'fb_cred': fb_cred, 'fb_db_url': fb_db_url}]

    nodes = [
        Node(package='db_bridge', executable='prescription_server',
             name='prescription_server', output='screen', parameters=db_params),
        Node(package='db_bridge', executable='rooms_server',
             name='rooms_server', output='screen', parameters=db_params),
        Node(package='db_bridge', executable='display_bridge',
             name='display_bridge', output='screen', parameters=db_params),
        Node(package='mission_manager', executable='mission_manager_node',
             name='mission_manager_node', output='screen',
             parameters=[{'namespace': ns}]),
        Node(package='mission_manager', executable='patrol_mode_node',
             name='patrol_mode_node', output='screen',
             parameters=[{'namespace': ns}]),
        Node(package='patient_identifier', executable='identifier_node',
             name='patient_identifier_node', output='screen',
             parameters=[{'namespace': ns, 'image_topic': image_topic}]),
    ]

    # db_node: 웹(mission_pool)에서 순찰을 트리거하려면 필요. 이미 별도로 db_node 를
    # 돌리고 있으면 중복 방지를 위해 start_db_node:=false 로 끌 수 있다.
    if start_db_node:
        nodes.append(
            Node(package='db_bridge', executable='db_node',
                 name='db_node', output='screen', parameters=db_params))

    return nodes


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument(
            'namespace',
            default_value=os.environ.get('ROBOT_NAMESPACE', 'robot3'),
            description='로봇 네임스페이스 (기본 env ROBOT_NAMESPACE, fallback robot3)'),
        DeclareLaunchArgument(
            'fb_cred',
            default_value=os.environ.get('FB_CRED', _DEFAULT_FB_CRED),
            description='Firebase 서비스계정 JSON 경로'),
        DeclareLaunchArgument(
            'fb_db_url',
            default_value=os.environ.get('FB_DB_URL', _DEFAULT_FB_DB_URL),
            description='Firebase RTDB databaseURL'),
        DeclareLaunchArgument(
            'image_topic',
            default_value=os.environ.get('QR_IMAGE_TOPIC', ''),
            description='QR 디코드용 카메라 image 토픽 (미지정 시 /{ns}/oakd/rgb/image_raw)'),
        DeclareLaunchArgument(
            'start_db_node',
            default_value='true',
            description='mission_pool→mission_request db_node 동시 기동 여부'),
        OpaqueFunction(function=launch_setup),
    ])
