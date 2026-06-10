"""Launch ocr_node in webcam mode (headless, no Gradio)."""
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
        Node(
            package='ocr_detector',
            executable='ocr_node',
            name='ocr_node',
            output='screen',
            parameters=[{
                'engine': LaunchConfiguration('engine'),
                'use_webcam': True,
                'webcam_device': LaunchConfiguration('webcam_device'),
                'confidence_threshold': LaunchConfiguration('confidence_threshold'),
                'gcp_rate_hz': LaunchConfiguration('gcp_rate_hz'),
            }],
        ),
    ])
