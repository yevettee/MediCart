#!/usr/bin/env python3
"""
hospital_multi.launch.py — 병원 world + TurtleBot4 '2대' (robot1 / robot2) 멀티로봇 시뮬.

hospital_sim.launch.py 와 동일하게 tb4 의 ignition 환경(resource path)을 재현해
우리 hospital.sdf 를 로드하고, turtlebot4_spawn.launch.py 를 namespace 를 달리해
'2번' include 한다. 토픽은 /robot1/..., /robot2/... 로 분리된다.

  - robot1: 우상단 도킹 상단,  robot2: 도킹 하단 (도면 로봇1/로봇2)
  - 시뮬은 SIM 모드(ROS_DOMAIN_ID=0, localhost)에서 실행.
    실제 로봇의 IP/discovery server/domain_id=6 네트워킹과는 무관하다.

사용:
    ros2 launch simulation hospital_multi.launch.py
    ros2 topic list | grep -E "robot1|robot2"
"""
import os
from pathlib import Path

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import (DeclareLaunchArgument, IncludeLaunchDescription,
                            SetEnvironmentVariable, TimerAction)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node


# 도면 도킹스테이션 좌표 (좌하단 원점). generate_hospital_world.py 의 ROBOT_SPAWNS 와 일치.
# delay: spawn 지연(초). Ignition Fortress 는 두 로봇을 동시에 spawn 하면 두 번째 로봇의
# GPU 라이다 센서가 등록에 실패한다 → robot2 를 지연시켜 robot1 센서가 다 뜬 뒤 띄운다.
ROBOTS = [
    {'namespace': 'robot1', 'x': '5.70', 'y': '4.05', 'yaw': '0.0', 'delay': 0.0},
    {'namespace': 'robot2', 'x': '5.70', 'y': '3.35', 'yaw': '0.0', 'delay': 12.0},
]

ARGUMENTS = [
    DeclareLaunchArgument('world', default_value='hospital',
                          description='World 이름 (worlds/<world>.sdf, SDF <world name> 과 동일)'),
    DeclareLaunchArgument('model', default_value='standard',
                          choices=['standard', 'lite'],
                          description='Turtlebot4 model (standard = OAK-D 포함)'),
    DeclareLaunchArgument('rviz', default_value='false',
                          choices=['true', 'false'], description='Start rviz.'),
]


def generate_launch_description():
    pkg_simulation = get_package_share_directory('simulation')
    pkg_tb4_ignition = get_package_share_directory('turtlebot4_ignition_bringup')
    pkg_tb4_ign_gui = get_package_share_directory('turtlebot4_ignition_gui_plugins')
    pkg_tb4_description = get_package_share_directory('turtlebot4_description')
    pkg_create_description = get_package_share_directory('irobot_create_description')
    pkg_create_ignition = get_package_share_directory('irobot_create_ignition_bringup')
    pkg_create_ign_plugins = get_package_share_directory('irobot_create_ignition_plugins')
    pkg_ros_ign_gazebo = get_package_share_directory('ros_ign_gazebo')

    world = LaunchConfiguration('world')
    model = LaunchConfiguration('model')

    ign_resource_path = SetEnvironmentVariable(
        name='IGN_GAZEBO_RESOURCE_PATH',
        value=[
            os.path.join(pkg_simulation, 'worlds'), ':' +
            os.path.join(pkg_tb4_ignition, 'worlds'), ':' +
            os.path.join(pkg_create_ignition, 'worlds'), ':' +
            str(Path(pkg_tb4_description).parent.resolve()), ':' +
            str(Path(pkg_create_description).parent.resolve())])

    ign_gui_plugin_path = SetEnvironmentVariable(
        name='IGN_GUI_PLUGIN_PATH',
        value=[
            os.path.join(pkg_tb4_ign_gui, 'lib'), ':' +
            os.path.join(pkg_create_ign_plugins, 'lib')])

    ign_gazebo_launch = PathJoinSubstitution(
        [pkg_ros_ign_gazebo, 'launch', 'ign_gazebo.launch.py'])
    ignition_gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([ign_gazebo_launch]),
        launch_arguments=[
            ('ign_args', [world, '.sdf', ' -r', ' -v 4', ' --gui-config ',
                          PathJoinSubstitution([pkg_tb4_ignition, 'gui', model, 'gui.config'])])
        ]
    )

    clock_bridge = Node(
        package='ros_gz_bridge', executable='parameter_bridge', name='clock_bridge',
        output='screen',
        arguments=['/clock' + '@rosgraph_msgs/msg/Clock' + '[ignition.msgs.Clock'])

    robot_spawn_launch = PathJoinSubstitution(
        [pkg_tb4_ignition, 'launch', 'turtlebot4_spawn.launch.py'])

    ld = LaunchDescription(ARGUMENTS)
    ld.add_action(ign_resource_path)
    ld.add_action(ign_gui_plugin_path)
    ld.add_action(ignition_gazebo)
    ld.add_action(clock_bridge)

    # 로봇 2대 — namespace 별로 spawn (각 spawn 내부 ros_ign_bridge 가
    # top-level world='hospital' 를 상속해 /world/hospital/model/<ns>/turtlebot4/... 구독).
    # 동시 spawn 시 두 번째 로봇 라이다가 누락되므로 delay 로 시차를 둔다.
    for r in ROBOTS:
        spawn = IncludeLaunchDescription(
            PythonLaunchDescriptionSource([robot_spawn_launch]),
            launch_arguments=[
                ('namespace', r['namespace']),
                ('model', model),
                ('rviz', LaunchConfiguration('rviz')),
                ('x', r['x']),
                ('y', r['y']),
                ('z', '0.0'),
                ('yaw', r['yaw']),
            ]
        )
        if r['delay'] > 0.0:
            ld.add_action(TimerAction(period=r['delay'], actions=[spawn]))
        else:
            ld.add_action(spawn)

    return ld
