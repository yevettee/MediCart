from setuptools import find_packages, setup

package_name = 'db_bridge'

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
    description='Firebase Realtime Database (RTDB) bridge for MediCart data layer',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'db_node = db_bridge.db_node:main',
            'prescription_server = db_bridge.prescription_server:main',
            'rooms_server = db_bridge.rooms_server:main',
            'display_bridge = db_bridge.display_bridge:main',
        ],
    },
)
