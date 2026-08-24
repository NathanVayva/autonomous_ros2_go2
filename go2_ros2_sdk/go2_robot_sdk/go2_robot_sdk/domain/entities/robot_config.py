# Copyright (c) 2024, RoboVerse community
# SPDX-License-Identifier: BSD-3-Clause

from dataclasses import dataclass
from typing import List


@dataclass
class RobotConfig:
    """Robot configuration parameters"""
    robot_ip_list: List[str]
    token: str
    conn_type: str
    enable_video: bool
    decode_lidar: bool
    publish_raw_voxel: bool
    obstacle_avoidance: bool
    conn_mode: str  # 'single' or 'multi'

    @classmethod
    def from_params(cls, robot_ip: str, token: str, conn_type: str, 
                   enable_video: bool, decode_lidar: bool, 
                   publish_raw_voxel: bool, obstacle_avoidance: bool):
        """Создание конфигурации из параметров"""
        # Drop empty entries so an unset/blank ROBOT_IP yields [] (not ['']),
        # which would otherwise become a phantom robot with an empty IP.
        robot_ip_list = [ip for ip in robot_ip.replace(" ", "").split(",") if ip]
        conn_mode = "single" if (
            len(robot_ip_list) <= 1 and conn_type != "cyclonedds") else "multi"
        
        return cls(
            robot_ip_list=robot_ip_list,
            token=token,
            conn_type=conn_type,
            enable_video=enable_video,
            decode_lidar=decode_lidar,
            publish_raw_voxel=publish_raw_voxel,
            obstacle_avoidance=obstacle_avoidance,
            conn_mode=conn_mode
        ) 