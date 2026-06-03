from setuptools import find_packages, setup

package_name = 'ocr_detector'

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
    description='OCR service for medicine label recognition',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'ocr_node = ocr_detector.ocr_node:main',
        ],
    },
)
