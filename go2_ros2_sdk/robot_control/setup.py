from setuptools import setup

package_name = 'robot_control'

setup(
    name=package_name,
    version='0.0.0',
    packages=[package_name],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Nathan',
    maintainer_email='nathan.vayva@gmail.com',
    description='Teleoperation clavier du Go2, prioritaire sur Nav2 (garde-fou)',
    license='BSD-3-Clause',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'keyboard_controller = robot_control.keyboard_controller:main',
        ],
    },
)
