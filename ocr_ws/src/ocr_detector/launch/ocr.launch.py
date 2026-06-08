from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('engine', default_value='easyocr',
                              description='OCR engine: easyocr or gcp'),
        DeclareLaunchArgument('image_topic', default_value='/robot6/color/image',
                              description='Camera image topic to subscribe'),
        DeclareLaunchArgument('confidence_threshold', default_value='0.2',
                              description='Minimum confidence to accept a token (EasyOCR)'),
        DeclareLaunchArgument('gcp_rate_hz', default_value='1.0',
                              description='GCP Vision API call rate in hz'),
        Node(
            package='ocr_detector',
            executable='ocr_node',
            name='ocr_node',
            output='screen',
            parameters=[{
                'engine': LaunchConfiguration('engine'),
                'image_topic': LaunchConfiguration('image_topic'),
                'confidence_threshold': LaunchConfiguration('confidence_threshold'),
                'gcp_rate_hz': LaunchConfiguration('gcp_rate_hz'),
            }],
        ),
    ])
