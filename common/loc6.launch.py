# MediCart: robot6 Localization with bond_timeout 패치.
# turtlebot4_navigation/localization.launch.py 와 동일 구조이되, 포함하는 nav2_bringup
# localization_launch 를 bond_timeout=60s 패치본(common/localization_bondpatched.launch.py)으로
# 교체. params/map 기본값을 MediCart 값으로 baked-in.
# (discovery-server .106 혼잡으로 map_server bond 4s abort 우회 — loc도 nav6와 동일 처리)

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, GroupAction, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import PushRosNamespace


ARGUMENTS = [
    DeclareLaunchArgument('use_sim_time', default_value='false',
                          choices=['true', 'false'],
                          description='Use sim time'),
    DeclareLaunchArgument('namespace', default_value='',
                          description='Robot namespace'),
    DeclareLaunchArgument('params',
                          default_value='/home/rokey/MediCart/common/loc6_amcl.yaml',
                          description='Localization parameters (amcl auto-seed)'),
    DeclareLaunchArgument('map',
                          default_value='/home/rokey/MediCart/common/maps/ninety.yaml',
                          description='Map yaml'),
]


def generate_launch_description():
    namespace = LaunchConfiguration('namespace')
    use_sim_time = LaunchConfiguration('use_sim_time')

    localization = GroupAction([
        PushRosNamespace(namespace),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                '/home/rokey/MediCart/common/localization_bondpatched.launch.py'),
            launch_arguments={'namespace': namespace,
                              'map': LaunchConfiguration('map'),
                              'use_sim_time': use_sim_time,
                              'params_file': LaunchConfiguration('params')}.items()),
    ])

    ld = LaunchDescription(ARGUMENTS)
    ld.add_action(localization)
    return ld
