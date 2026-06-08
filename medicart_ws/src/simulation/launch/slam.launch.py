#!/usr/bin/env python3
"""
slam.launch.py — 병원 방 매핑용 SLAM (turtlebot4_navigation slam.launch.py 래퍼).

tb4 패키지를 수정하지 않고, 설치된 slam.launch.py 에 우리 simulation/config/slam.yaml
(작은 방 튜닝)을 params 인자로 주입한다. 시뮬이므로 use_sim_time 기본 true.

사용:
    # 1) 터미널 A: ros2 launch simulation hospital_sim.launch.py
    # 2) 터미널 B: ros2 launch simulation slam.launch.py
    # 3) teleop 으로 방 한 바퀴 → 맵 저장:
    #    ros2 run nav2_map_server map_saver_cli -f ~/MediCart/medicart_ws/src/simulation/maps/hospital_map
"""
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

    slam_launch = PathJoinSubstitution(
        [pkg_tb4_navigation, 'launch', 'slam.launch.py'])
    slam_params = PathJoinSubstitution(
        [pkg_simulation, 'config', 'slam.yaml'])

    slam = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([slam_launch]),
        launch_arguments=[
            ('namespace', LaunchConfiguration('namespace')),
            ('use_sim_time', LaunchConfiguration('use_sim_time')),
            ('params', slam_params),
        ]
    )

    ld = LaunchDescription(ARGUMENTS)
    ld.add_action(slam)
    return ld
