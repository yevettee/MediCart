# MediCart: robot3 Nav2 bringup with bond_timeout 패치.
# nav6.launch.py 와 동일 구조 — namespace 기본값과 params_file 만 robot3 기준.

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    GroupAction,
    IncludeLaunchDescription,
    OpaqueFunction
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration

from launch_ros.actions import PushRosNamespace, SetRemap


ARGUMENTS = [
    DeclareLaunchArgument('use_sim_time', default_value='false',
                          choices=['true', 'false'],
                          description='Use sim time'),
    DeclareLaunchArgument('params_file',
                          default_value='/home/rokey/MediCart/common/nav3.yaml',
                          description='Nav2 parameters'),
    DeclareLaunchArgument('namespace', default_value='/robot3',
                          description='Robot namespace')
]


def launch_setup(context, *args, **kwargs):
    nav2_params = LaunchConfiguration('params_file')
    namespace = LaunchConfiguration('namespace')
    use_sim_time = LaunchConfiguration('use_sim_time')

    namespace_str = namespace.perform(context)
    if namespace_str and not namespace_str.startswith('/'):
        namespace_str = '/' + namespace_str

    launch_nav2 = '/home/rokey/MediCart/common/navigation_bondpatched.launch.py'

    nav2 = GroupAction([
        PushRosNamespace(namespace),
        SetRemap(namespace_str + '/global_costmap/scan', namespace_str + '/scan'),
        SetRemap(namespace_str + '/local_costmap/scan', namespace_str + '/scan'),

        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(launch_nav2),
            launch_arguments=[
                ('use_sim_time', use_sim_time),
                ('params_file', nav2_params.perform(context)),
                ('use_composition', 'False'),
                ('namespace', namespace_str)
            ]
        ),
    ])

    return [nav2]


def generate_launch_description():
    ld = LaunchDescription(ARGUMENTS)
    ld.add_action(OpaqueFunction(function=launch_setup))
    return ld
