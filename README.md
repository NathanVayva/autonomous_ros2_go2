# autonomous_ros2_go2

Integration workspace for an **autonomous Unitree Go2** quadruped. It brings together a ROS 2
control/perception stack and an **Isaac Sim 4.5** simulation of the robot under a single
**Docker** setup, and adds a **vision-language model (VLM) navigation layer**: the model decides
*where* to go on a known map, while Nav2 handles *how* to get there.

> **This repository stands on third-party work.** The two lower layers (the Go2 ROS 2 SDK and
> the Isaac Sim simulation) are open-source projects by other authors — see [Credits](#credits).
> My own work is the integration between them, the Nav2 tuning, and the `go2_ai` navigation
> package — see [What I contributed](#what-i-contributed).

## Repository layout

- **`go2_ros2_sdk/`** — the community ROS 2 SDK for the Go2 (WebRTC / CycloneDDS bridge,
  telemetry → ROS 2 topics, SLAM / Nav2 / teleop launch files). *Upstream, with my changes.*
  - **`go2_ai/`** — my ROS 2 package: the VLM navigation node (Set-of-Mark planning, spatial
    memory, sim/real-agnostic topics). See [`AI_BACKEND_TUTORIAL.md`](AI_BACKEND_TUTORIAL.md).
- **`isaac-go2-ros2-isaacsim-4.5-docker/`** — a Go2 simulation on **Isaac Sim 4.5 / Isaac Lab
  2.1** that streams sensor/odometry over ROS 2 Humble and takes velocity commands.
  *Fork of an upstream project (see Credits).*

Design notes and the running work journal are in [`NAVIGATION_AUTONOME.md`](NAVIGATION_AUTONOME.md).

## What I contributed

- **`go2_ai` navigation package** — a VLM decides the destination, Nav2 executes the path. Uses
  **Set-of-Mark** prompting: the map is shown with numbered points of interest and the robot's
  pose; the model answers a single number, whose map coordinates are known. Goals can never land
  in a wall (points are pre-filtered), and the model never drives the motors. Includes spatial
  memory (visited points) and a hexagonal architecture so the VLM backend is a swappable adapter.
- **Nav2 tuning** for the quadruped: turn-in-place before moving (goal behind the robot), a 2D
  planner that allows U-turns in narrow corridors, and wider global inflation to keep paths
  centered.
- **Keyboard safety override** — grabbing manual control has priority over Nav2 (via `twist_mux`)
  **and cancels the active goal**, so the robot does not drive off on its own after a takeover.
- **Sim ⇄ real plumbing** — the same control/perception stack and the `go2_ai` node run against
  either the simulated or the physical Go2, selected at run time (topic/frame namespacing handled).
- **Dockerized the stack** so it builds and runs reproducibly on a single-GPU laptop.

Everything under `go2_ros2_sdk/` (outside `go2_ai/`) and the Isaac simulation itself is upstream
work; the value I added is the navigation layer and making the pieces run together end-to-end.

## Requirements

- Linux with **Docker** and **Docker Compose** (v2).
- **NVIDIA GPU** + driver + [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
  (`runtime: nvidia`). Needed for Isaac Sim, and for running a real VLM backend on the GPU.
- An X server for the GUIs (RViz, Isaac Sim viewport). `launch.sh` calls `xhost` for you.
- For the **real robot**: a Unitree Go2 reachable over the network, plus its `ROBOT_IP`
  (and `ROBOT_TOKEN` for WebRTC).

The simulator and the SDK talk over the host ROS 2 (DDS) graph, so both halves must share the
same `ROS_DOMAIN_ID` (the launcher enforces this).

## Installation

```bash
git clone https://github.com/NathanVayva/autonomous_ros2_go2.git
cd autonomous_ros2_go2

# Build the SDK image
cd go2_ros2_sdk/docker
./launch.sh build
```

Isaac Sim builds/downloads its assets on first launch (several minutes: asset load + shader
compile). In `sim` mode `launch.sh` starts the Isaac container for you; to build it separately:

```bash
cd isaac-go2-ros2-isaacsim-4.5-docker
./isaac-launch.sh build
```

> The VLM Python deps (`transformers`, `accelerate`, `bitsandbytes`) are **not** in
> `requirements.txt` and are only needed for a real VLM backend. Install them inside the SDK
> container when you switch off the `mock` backend (see [`AI_BACKEND_TUTORIAL.md`](AI_BACKEND_TUTORIAL.md)).

## Usage

All commands run from `go2_ros2_sdk/docker/`.

### Simulation (no robot needed)

```bash
./launch.sh sim              # launches Isaac Sim + the SDK driver in sim mode
# performance presets (RTF vs. sensors):
SIM_PERF=max ./launch.sh sim     # keep lidar + color cam, drop depth/semantic
HEADLESS=1 SIM_PERF=light ./launch.sh sim   # no viewport, no camera (lightest)
```

### Real robot

```bash
ROBOT_IP=192.168.12.1 ROBOT_TOKEN=<token> ./launch.sh real
```

### Other commands

```bash
./launch.sh shell [real|sim]   # start the container + a shell (no driver)
./launch.sh enter              # open a shell in the running container
./launch.sh down               # stop the SDK container (+ Isaac if running)
```

### VLM navigation node (`go2_ai`)

`go2_ai` lives under the mounted workspace (`/ros2_ws/src/go2_ai`). Bring up the robot (sim or
real) first, then, from inside the container (`./launch.sh enter`):

```bash
colcon build --packages-select go2_ai --symlink-install
source install/setup.bash

# against the real robot / GPU (Set-of-Mark on the map, default):
ros2 launch go2_ai ai_backend.launch.py

# against the simulation with the mock backend (no GPU, no VLM download):
ros2 launch go2_ai ai_sim.launch.py

# override backend / device / mode on the command line:
ros2 launch go2_ai ai_backend.launch.py backend:=qwen3_vl_4b device:=cpu nav_mode:=map_som \
    instruction:="find the door"
```

`device:=cpu` runs the VLM in RAM and leaves the GPU to Isaac Sim.

## Configuration

Tune the navigation node without recompiling in `go2_ros2_sdk/go2_ai/config/ai.yaml`
(`ai_sim.yaml` for simulation). Key knobs:

| Parameter | Meaning |
|---|---|
| `backend` | VLM to load (`mock`, `qwen3_vl_*`, `robobrain2_7b`) — defined in `go2_ai/adapter/registry.py` |
| `device` | `cuda` (GPU, 4-bit) or `cpu` (RAM, leaves the GPU free) |
| `nav_mode` | `map_som` (numbered POI on the map), `heading` (bearing + distance), `pixel` (placeholder) |
| `map_yaml` / `poi_path` | map shown to the model and its points of interest |
| `instruction` | high-level mission given to the model (e.g. `"find the door"`) |
| `goal_cost_threshold` | reject a goal that falls on a Nav2 costmap obstacle |
| `image_topic` / `odom_topic` | input topics (differ between sim and real) |

## Roadmap (work in progress)

- **Robustness of the goal → action path** in Nav2 (recovery on rejected/unreachable goals).
- **On-board or remote-GPU VLM** so inference is not tied to the laptop running the sim.
- **Generic semantic exploration** using the Go2 as a testbed, rather than a fixed POI set.
- **Quadruped-aware planning** — evaluating a planner better suited to legged locomotion than the
  differential-drive assumptions of the default Nav2 setup. *Under study.*

## Credits

- **Go2 ROS 2 SDK** — RoboVerse community / `abizovnuralem`:
  https://github.com/abizovnuralem/go2_ros2_sdk (BSD-2-Clause). Depends on a patched
  `aioice` fork by `legion1581`.
- **Isaac Sim Go2 simulation** — fork of `Zhefan-Xu/isaac-go2-ros2`
  (https://github.com/Zhefan-Xu/isaac-go2-ros2), with Docker support originally by `SeanChangX`.

Please refer to each subproject's own `LICENSE` and README for the terms and full author list.
