from setuptools import find_packages, setup

package_name = 'mission_manager'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='MediCart Team',
    maintainer_email='dev@medicart.local',
    description='Mission orchestration and state machine for MediCart',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'mission_manager_node = mission_manager.mission_manager_node:main',
        ],
    },
)
