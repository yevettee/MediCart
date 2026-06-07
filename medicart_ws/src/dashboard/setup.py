from setuptools import find_packages, setup

package_name = 'dashboard'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    package_data={
        package_name: [
            'web/static/*',
            'web/maps/*',
        ],
    },
    data_files=[
        (
            'share/ament_index/resource_index/packages',
            ['resource/' + package_name],
        ),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=False,
    maintainer='MediCart Team',
    maintainer_email='dev@medicart.local',
    description='Operator dashboard for MediCart',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'dashboard_node = dashboard.dashboard_node:main',
        ],
    },
)
