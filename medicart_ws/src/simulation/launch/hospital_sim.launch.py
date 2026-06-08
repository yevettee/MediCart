#!/usr/bin/env python3
"""
hospital_sim.launch.py — MediCart 병원 Gazebo 시뮬 진입점.

turtlebot4_ws 를 수정하지 않으면서, tb4 의 turtlebot4_ignition.launch.py 가
IGN_GAZEBO_RESOURCE_PATH 를 '덮어쓰는' 문제를 피하기 위해 그 launch 의 작은 부분
(리소스 경로 설정 + ign_gazebo 실행 + clock bridge)만 여기서 재현한다.
로봇 spawn 은 tb4 의 turtlebot4_spawn.launch.py 를 그대로 include 한다.

핵심: world 인자는 '경로' 가 아니라 '이름'(hospital) 으로 넘긴다.
  - ign 은 IGN_GAZEBO_RESOURCE_PATH(여기에 우리 worlds 디렉토리를 맨 앞에 추가)에서
    'hospital.sdf' 를 찾아 로드한다.
  - tb4 ros_ign_bridge 는 world 이름으로 ign 토픽(/world/hospital/...)을 구독한다.
  → world 이름이 SDF <world name='hospital'> 과 일치해야 /scan·카메라가 ROS 로 넘어온다.
    (이전에 절대경로를 넘겼더니 bridge 가 /world//abs/path/... 로 깨져서 죽었음)

사용 예:
    ros2 launch simulation hospital_sim.launch.py
    ros2 launch simulation hospital_sim.launch.py rviz:=true
    ros2 launch simulation hospital_sim.launch.py x:=0.0 y:=0.0 yaw:=0.0
"""
import os
from pathlib import Path

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import (DeclareLaunchArgument, IncludeLaunchDescription,
                            SetEnvironmentVariable)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node


ARGUMENTS = [
    DeclareLaunchArgument('world', default_value='hospital',
                          description='World 이름 (worlds/<world>.sdf, SDF <world name> 과 동일)'),
    DeclareLaunchArgument('rviz', default_value='false',
                          choices=['true', 'false'], description='Start rviz.'),
    DeclareLaunchArgument('model', default_value='standard',
                          choices=['standard', 'lite'],
                          description='Turtlebot4 model (standard = OAK-D 포함)'),
    DeclareLaunchArgument('namespace', default_value='',
                          description='Robot namespace'),
    # 로봇 spawn pose — 기본값 = 우상단 도킹스테이션(robot1).
    # yaw=0 → 로봇이 +x(우측 벽)를 향해 도크가 벽에 붙는다. x=5.70 → 도크가 우측 벽에 근접.
    DeclareLaunchArgument('x', default_value='5.70', description='spawn x'),
    DeclareLaunchArgument('y', default_value='4.05', description='spawn y'),
    DeclareLaunchArgument('z', default_value='0.0', description='spawn z'),
    DeclareLaunchArgument('yaw', default_value='0.0', description='spawn yaw'),
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

    # IGN 리소스 경로 — 우리 worlds 디렉토리를 '맨 앞'에 두어 hospital.sdf 를 찾게 하고,
    # 그 뒤로 tb4/create 의 worlds·description 경로(로봇 메쉬 등)를 그대로 포함.
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

    # Ignition Gazebo — world 이름.sdf 로드 (tb4 ignition.launch.py 의 ignition_gazebo 재현)
    ign_gazebo_launch = PathJoinSubstitution(
        [pkg_ros_ign_gazebo, 'launch', 'ign_gazebo.launch.py'])
    ignition_gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([ign_gazebo_launch]),
        launch_arguments=[
            ('ign_args', [world, '.sdf', ' -r', ' -v 4', ' --gui-config ',
                          PathJoinSubstitution([pkg_tb4_ignition, 'gui', model, 'gui.config'])])
        ]
    )

    # Clock bridge (sim time)
    clock_bridge = Node(
        package='ros_gz_bridge', executable='parameter_bridge', name='clock_bridge',
        output='screen',
        arguments=['/clock' + '@rosgraph_msgs/msg/Clock' + '[ignition.msgs.Clock'])

    # 로봇 spawn — tb4 의 spawn launch 그대로 include.
    # spawn 은 'world' 인자를 선언하지 않지만, 위에서 선언한 top-level world='hospital'
    # config 가 context 상속으로 spawn 내부 ros_ign_bridge 까지 전파되어
    # bridge 가 /world/hospital/... 를 구독한다. (명시 전달은 생략)
    robot_spawn_launch = PathJoinSubstitution(
        [pkg_tb4_ignition, 'launch', 'turtlebot4_spawn.launch.py'])
    robot_spawn = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([robot_spawn_launch]),
        launch_arguments=[
            ('namespace', LaunchConfiguration('namespace')),
            ('rviz', LaunchConfiguration('rviz')),
            ('model', model),
            ('x', LaunchConfiguration('x')),
            ('y', LaunchConfiguration('y')),
            ('z', LaunchConfiguration('z')),
            ('yaw', LaunchConfiguration('yaw')),
        ]
    )

    ld = LaunchDescription(ARGUMENTS)
    ld.add_action(ign_resource_path)
    ld.add_action(ign_gui_plugin_path)
    ld.add_action(ignition_gazebo)
    ld.add_action(clock_bridge)
    ld.add_action(robot_spawn)
    return ld
