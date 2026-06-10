#!/usr/bin/env python3
"""
nav2.launch.py — 저장된 병원 맵 위에서 localization(AMCL) + Nav2 자율주행.

tb4 패키지를 수정하지 않고, 설치된 localization.launch.py / nav2.launch.py 에
우리 simulation/config/nav2.yaml (좁은 방 costmap 튜닝)과 맵을 주입한다.
기본 맵: medicart_ws/maps/ninety.yaml (dashboard·patrol 좌표와 동일 프레임).
다른 맵을 쓰려면 slam.launch.py 로 매핑·저장 후 map:= 로 지정.

사용:
    # 1) ros2 launch simulation hospital_sim.launch.py
    # 2) ros2 launch simulation nav2.launch.py
    #    (다른 맵: ros2 launch simulation nav2.launch.py map:=/경로/xxx.yaml)
"""
import os

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution


ARGUMENTS = [
    DeclareLaunchArgument('use_sim_time', default_value='true',
                          choices=['true', 'false'], description='use_sim_time'),
    DeclareLaunchArgument('namespace', default_value='',
                          description='Robot namespace'),
]


def generate_launch_description():
    pkg_simulation = get_package_share_directory('simulation')
    pkg_tb4_navigation = get_package_share_directory('turtlebot4_navigation')

    localization_launch = PathJoinSubstitution(
        [pkg_tb4_navigation, 'launch', 'localization.launch.py'])
    nav2_launch = PathJoinSubstitution(
        [pkg_tb4_navigation, 'launch', 'nav2.launch.py'])

    nav2_params = PathJoinSubstitution([pkg_simulation, 'config', 'nav2.yaml'])
    # 현재 운영 맵: ~/MediCart/medicart_ws/maps/ninety.yaml (dashboard·patrol 좌표와 동일
    # 프레임). 홈 디렉토리만 사용자별로 다르고 MediCart 이하 경로는 모두 동일.
    # 다른 맵은 map:=/경로/xxx.yaml 로 override.
    default_map = os.path.expanduser('~/MediCart/medicart_ws/maps/ninety.yaml')

    map_arg = DeclareLaunchArgument(
        'map', default_value=default_map,
        description='저장된 맵 yaml 경로')

    localization = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([localization_launch]),
        launch_arguments=[
            ('namespace', LaunchConfiguration('namespace')),
            ('use_sim_time', LaunchConfiguration('use_sim_time')),
            ('map', LaunchConfiguration('map')),
        ]
    )

    nav2 = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([nav2_launch]),
        launch_arguments=[
            ('namespace', LaunchConfiguration('namespace')),
            ('use_sim_time', LaunchConfiguration('use_sim_time')),
            ('params_file', nav2_params),
        ]
    )

    ld = LaunchDescription(ARGUMENTS)
    ld.add_action(map_arg)
    ld.add_action(localization)
    ld.add_action(nav2)
    return ld
