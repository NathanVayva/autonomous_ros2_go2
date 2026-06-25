# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Unofficial ROS2 SDK for the Unitree Go2 quadruped (Edu/Pro/Air). It connects to the
robot over **WebRTC** (the consumer protocol) or **CycloneDDS** (the EDU low-level
protocol), republishes telemetry (state, IMU, odometry, LiDAR voxel maps, camera) as
ROS2 topics, and forwards motion/WebRTC commands back to the robot. SLAM, Nav2,
teleop, Foxglove, and RViz are wired up in the launch files.

This directory is a **ROS2 workspace `src/` folder**: each top-level subdirectory is a
separate ament package. `unitree-go2-ros2/` is the CHAMP-based Gazebo simulation stack
(git submodule contents); `external_lib/aioice` is a patched aioice submodule that the
WebRTC stack depends on.

## Build & Run

This is built with `colcon` from the parent workspace (the dir containing this one as
`src/`). The aioice submodule **must** be initialized or the driver exits on import
(`go2_robot_sdk/__init__.py` checks for it).

```bash
# from workspace root, one level above this dir
git submodule update --init --recursive
sudo apt install ros-$ROS_DISTRO-image-tools ros-$ROS_DISTRO-vision-msgs \
  python3-pip clang portaudio19-dev
rosdep install --from-paths src --ignore-src -r -y
pip install -r src/requirements.txt          # aiortc, open3d, torch, opencv, etc.

colcon build                                  # or: colcon build --symlink-install
source install/setup.bash

# required env vars before launching
export ROBOT_IP="192.168.1.50"                # comma-separated list => multi-robot mode
export CONN_TYPE="webrtc"                      # or "cyclonedds"
export ROBOT_TOKEN=""                          # required for remote WebRTC connections

ros2 launch go2_robot_sdk robot.launch.py
```

Build a single package: `colcon build --packages-select go2_robot_sdk`.

Supported ROS2 distros: **humble** and **jazzy** (see `.github/workflows/ros_build.yaml`;
CI builds both but runs with `skip-tests: true`).

### Launch arguments

`robot.launch.py` toggles subsystems via args (all default `true`):
`rviz2`, `nav2`, `slam`, `foxglove`, `joystick`, `teleop`. e.g.
`ros2 launch go2_robot_sdk robot.launch.py rviz2:=false nav2:=false`.

Other launch files: `mapping.launch.py`, `navigation.launch.py`, `webrtc_web.launch.py`,
`robot_cpp.launch.py` (uses the C++ LiDAR processor instead of Python).

### Lint & test

Each Python package uses the standard ament test trio (`test_flake8.py`,
`test_pep257.py`, `test_copyright.py`). Flake8 config is in `setup.cfg`
(max-line-length 100, max-complexity 10). Run tests with:

```bash
colcon test --packages-select robot_control
colcon test-result --verbose
# single test directly:
python -m pytest robot_control/test/test_flake8.py
```

## Architecture

### `go2_robot_sdk` — main driver (clean / DDD layering)

The core package is organized into clean-architecture layers under
`go2_robot_sdk/go2_robot_sdk/`. Dependencies point inward (presentation → application →
domain; infrastructure implements domain interfaces):

- **`presentation/go2_driver_node.py`** — `Go2DriverNode`, the single ROS2 node. Owns all
  publishers/subscribers, declares parameters, wires the other layers together. Topic
  names differ by `conn_mode`: `single` uses bare names (`odom`, `point_cloud2`,
  `camera/image_raw`), `multi` prefixes everything with `robot{i}/`.
- **`application/`** — use-case services. `RobotControlService` (cmd_vel/joy/webrtc
  command handling), `RobotDataService` (routes incoming WebRTC messages to the
  publisher). `utils/command_generator.py` builds the robot's JSON command envelopes.
- **`domain/`** — pure logic, no ROS/network deps. `entities/` (`RobotConfig`,
  `RobotData`, `CameraData`), `interfaces/` (`IRobotController`, `IRobotDataReceiver`,
  `IRobotDataPublisher` — the ports), `constants/` (`ROBOT_CMD` command IDs,
  `RTC_TOPIC` WebRTC topic map), `math/` (kinematics, geometry).
- **`infrastructure/`** — adapters implementing the domain ports:
  - `webrtc/` — `WebRTCAdapter` (implements `IRobotController` + `IRobotDataReceiver`),
    `go2_connection.py` (`Go2Connection`, the aiortc peer connection per robot),
    `http_client.py` (WebRTC signaling), `data_decoder.py`, `crypto/encryption.py`.
  - `sensors/lidar_decoder.py` — decodes the compressed voxel map; uses the WASM module
    `external_lib/libvoxel.wasm` via wasmtime.
  - `ros2/ros2_publisher.py` — `ROS2Publisher`, the only place that converts domain data
    into ROS2 messages and publishes / broadcasts TF.

**Concurrency model** (`main.py`): runs asyncio and ROS2 together — the ROS2 executor
spins in a daemon thread while robot WebRTC connections and per-robot control loops run
as asyncio tasks on the main event loop. The event loop is passed explicitly into
`Go2DriverNode` and down to `WebRTCAdapter` so callbacks from aiortc threads can
schedule work back onto it.

**Adding a new robot data type** typically touches all layers: a domain entity/field, a
publisher method in `ros2_publisher.py`, a route in `RobotDataService`, and a publisher
registration in `Go2DriverNode._setup_publishers`.

### Supporting packages

- **`go2_interfaces`** — all custom messages (`.msg`). Merge of the former `unitree_go`
  and `go2_interfaces`. Includes `Go2State`, `IMU`, `LowState`, `VoxelMapCompressed`,
  `WebRtcReq`, etc. `ament_cmake` package — rebuild it after changing any `.msg`.
- **`lidar_processor`** (Python) / **`lidar_processor_cpp`** (C++) — interchangeable
  point-cloud pipeline: `lidar_to_pointcloud` (voxel map → PointCloud2, optional map
  save) and `pointcloud_aggregator` (range/height filtering, downsampling).
- **`robot_control`** — `keyboard_controller` node for keyboard teleop.
- **`speech_processor`** — TTS / audio nodes (`tts_node`, `speech_synthesizer`,
  `audio_manager`); ElevenLabs TTS via `ELEVENLABS_API_KEY`.
- **`coco_detector`** — torchvision COCO object detection node publishing `vision_msgs`.
- **`unitree-go2-ros2/`** — CHAMP-based Gazebo simulation (`go2_config`,
  `go2_description`, `champ*`). See its own README; launched with
  `ros2 launch go2_config gazebo.launch.py`.

## Conventions

- Connection mode is derived, not configured directly: a single IP in `ROBOT_IP` with a
  non-cyclonedds `conn_type` ⇒ `single` mode; otherwise `multi`. This drives topic
  namespacing, the URDF (`go2.urdf` vs `multi_go2.urdf`), and the RViz config.
- Config is read from env vars **and** ROS2 parameters (`robot_ip`, `token`, `conn_type`,
  `enable_video`, `decode_lidar`, `publish_raw_voxel`, `obstacle_avoidance`).
  `obstacle_avoidance` is the one runtime-settable parameter (see
  `_on_set_parameters`).
- License headers: `# Copyright (c) 2024, RoboVerse community` / `# SPDX-License-Identifier: BSD-3-Clause`.
