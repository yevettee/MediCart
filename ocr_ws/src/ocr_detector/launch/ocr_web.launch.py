"""Launch ocr_web node — Gradio UI + webcam OCR."""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('engine', default_value='easyocr',
                              description='OCR engine: easyocr or gcp'),
        DeclareLaunchArgument('webcam_device', default_value='2',
                              description='Video device index (e.g. 2 for /dev/video2)'),
        DeclareLaunchArgument('confidence_threshold', default_value='0.2'),
        DeclareLaunchArgument('gcp_rate_hz', default_value='1.0'),
        DeclareLaunchArgument('web_port', default_value='7864'),
        Node(
            package='ocr_detector',
            executable='ocr_web',
            name='ocr_web_node',
            output='screen',
            parameters=[{
                'engine': LaunchConfiguration('engine'),
                'webcam_device': LaunchConfiguration('webcam_device'),
                'confidence_threshold': LaunchConfiguration('confidence_threshold'),
                'gcp_rate_hz': LaunchConfiguration('gcp_rate_hz'),
                'web_port': LaunchConfiguration('web_port'),
            }],
        ),
    ])
