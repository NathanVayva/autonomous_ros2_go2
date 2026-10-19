# Copyright (c) 2026, Nathan
# SPDX-License-Identifier: BSD-3-Clause

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    # Charge le nœud avec ses paramètres depuis config/ai.yaml.
    # Surcharges en ligne de commande :
    #   ros2 launch go2_ai ai_backend.launch.py backend:=qwen3_vl_2b device:=cpu
    #   (device=cpu : VLM en RAM, laisse le GPU à Isaac Sim.)
    #   nav_mode:=map_som -> voie C (numéro de POI sur carte) ; heading | pixel sinon.
    cfg = os.path.join(get_package_share_directory('go2_ai'), 'config', 'ai.yaml')
    backend = LaunchConfiguration('backend')
    device = LaunchConfiguration('device')
    return LaunchDescription([
        DeclareLaunchArgument(
            'backend', default_value='qwen3_vl_4b',
            description="Backend à charger (mock | qwen3_vl_* | robobrain2_7b)."),
        DeclareLaunchArgument(
            'device', default_value='cuda',
            description="Device d'inférence : cuda (GPU) | cpu (RAM, laisse le GPU à Isaac)."),
        DeclareLaunchArgument(
            'nav_mode', default_value='heading',
            description="heading (cap+distance) | pixel (placeholder) | map_som (POI sur carte)."),
        DeclareLaunchArgument(
            'reasoning_mode', default_value='fused',
            description="fused = 1 génération ; chained = décris puis décide (2 gén.)."),
        DeclareLaunchArgument(
            'instruction', default_value='explore',
            description="Mission haut-niveau donnée au modèle (ex. \"find the door\")."),
        Node(
            package='go2_ai',
            executable='ai_node',
            name='go2_ai',
            output='screen',
            parameters=[cfg, {'backend': backend, 'device': device,
                              'nav_mode': LaunchConfiguration('nav_mode'),
                              'reasoning_mode': LaunchConfiguration('reasoning_mode'),
                              'instruction': LaunchConfiguration('instruction')}],
        ),
    ])
