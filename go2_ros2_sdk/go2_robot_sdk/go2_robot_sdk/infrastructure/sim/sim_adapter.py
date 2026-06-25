# Copyright (c) 2024, RoboVerse community
# SPDX-License-Identifier: BSD-3-Clause


import json
import logging
from sensor_msgs.msg import Image
from typing import Callable, Any
from ...domain.interfaces import IRobotController, IRobotDataReceiver
from ...domain.entities import RobotConfig 
import numpy as np
from geometry_msgs.msg import Twist
from std_msgs.msg import String
from sensor_msgs.msg import PointCloud2   
from sensor_msgs_py import point_cloud2   
from ...domain.constants import RTC_TOPIC


logger = logging.getLogger(__name__)


class SimAdapter(IRobotController, IRobotDataReceiver):

    def __init__(self, config: RobotConfig, node):
        self.config = config
        self.node = node
        self.data_callback: Callable = None
        self.connections = {}
        self.cmd_vel_pub = {}
        self.image_bridge = {}

    # --- IRobotDataReceiver ---
    async def connect(self, robot_id: str) -> None:
        self.cmd_vel_pub[robot_id] = self.node.create_publisher(
            Twist,
            f"sim/robot{robot_id}/cmd_vel",
            10,
        )
        self.node.create_subscription(
            String,
            f"sim/robot{robot_id}/telemetry",
            lambda msg, rid=robot_id: self.telemetry_callback(msg, rid),
            10,
        )
        self.node.create_subscription(
            PointCloud2,
            f"sim/robot{robot_id}/lidar",
            lambda msg, rid=robot_id:self.lidar_callback(msg, rid),
            10,
        )
        self.node.create_subscription(
            Image,
            f"/unitree_go2/front_cam/color_image",
            lambda msg, rid=robot_id: self.camera_callback(msg, rid),
            10,
        )
        self.image_bridge[robot_id] = self.node.create_publisher(
            Image,
            f"camera/image_raw",
            10,
        )
        #        self.image_bridge[robot_id] = self.node.ros2_publisher.publishers['camera'][int(robot_id)]

        self.connections[robot_id] = True
        logger.info(f"Connecting to simulated robot with ID: {robot_id}")

    async def disconnect(self, robot_id: str) -> None:
        logger.info(f"Disconnecting from simulated robot with ID: {robot_id}")

    def set_data_callback(self, callback: Callable) -> None:
        self.data_callback = callback
    def send_command(self, robot_id: str, command: Any) -> None:
        logger.info(f"Sending command to simulated robot {robot_id}: {command}")


    # --- IRobotController ---
    def send_movement_command(self, robot_id: str, x:float, y:float, z:float) -> None:
        logger.info(f"Sending movement command to robot {robot_id}: x={x}, y={y}, z={z}")
        msg = Twist()
        msg.linear.x = x
        msg.linear.y = y
        msg.angular.z = z
        self.cmd_vel_pub[robot_id].publish(msg)
    
    def send_stand_up_command(self,robot_id: str) -> None:
        logger.info(f"Sending stand up command to robot {robot_id}")

    def send_stand_down_command(self, robot_id: str) -> None:
        logger.info(f"Sending stand down command to robot {robot_id}")

    def send_webrtc_request(self, robot_id: str, api_id: int, parameter: Any, topic: str) -> None:
        logger.info(f"Sending WebRTC request to robot {robot_id}: api_id={api_id}, parameter={parameter}, topic={topic}")
        
    def process_webrtc_commands(self, robot_id: str) -> None:
        logger.info(f"Processing WebRTC command for robot {robot_id}")




    # --- Internal Callbacks ---
    def telemetry_callback(self, msg: String, robot_id: str):
        enveloppe = json.loads(msg.data)
        if self.data_callback:
            self.data_callback(enveloppe, robot_id)

    def lidar_callback(self, msg: PointCloud2, robot_id: str):
        pts = point_cloud2.read_points_numpy(msg, field_names=("x", "y", "z"), skip_nans=True)
        positions = pts.reshape(-1).tolist()
        uvs = [1.0,1.0] * len(pts)

        envelope = {
            "topic": RTC_TOPIC["ULIDAR_ARRAY"],
            "decoded_data": {"positions":positions, "uvs": uvs},
            "data":{"resolution": 1.0, "origin": [0.0,0.0,0.0]}
        }
        if self.data_callback:
            self.data_callback(envelope, robot_id)

    def camera_callback(self, msg: Image, robot_id: str):
        self.image_bridge[robot_id].publish(msg)