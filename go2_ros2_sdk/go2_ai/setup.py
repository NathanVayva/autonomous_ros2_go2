# Copyright (c) 2024, RoboVerse community
# SPDX-License-Identifier: BSD-3-Clause

import os
from glob import glob

from setuptools import find_packages, setup

package_name = 'go2_ai'

setup(
    name=package_name,
    version='0.1.0',
    # Découvre go2_ai + ses sous-modules (domain, adapter, application, presentation).
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'config'), glob('config/*.yaml')),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.py')),
        # cases.yaml + bench.py sont des données de dev (le bench se lance à la main).
        (os.path.join('share', package_name, 'bench'), glob('bench/*')),
    ],
    # Modèle EN LOCAL, en process : dépendances ML (pas de client API réseau).
    # NB Jetson : installe torch/transformers via jetson-containers, pas pip à l'aveugle.
    install_requires=[
        'setuptools',
        'torch',
        'transformers',
        'accelerate',
        'pillow',
        'numpy',
        'opencv-python',
        'pyyaml',
    ],
    zip_safe=True,
    maintainer='Nathan',
    maintainer_email='nathan.vayva@gmail.com',
    description='Backend IA local (VLM + raisonnement embarqué) pour le Go2',
    license='BSD-3-Clause',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            # Le nœud ROS. Son main() est à écrire dans presentation/ai_node.py.
            'ai_node = go2_ai.presentation.ai_node:main',
        ],
    },
)
