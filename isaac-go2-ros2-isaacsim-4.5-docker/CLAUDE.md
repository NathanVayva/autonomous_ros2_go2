# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Unitree Go2 quadruped simulation built on **Isaac Sim 4.5 / Isaac Lab 2.1** that bridges
the simulated robot to **ROS 2 Humble**. The entry point `isaac_go2_ros2.py` launches the
Isaac Sim app, builds the Go2 RL environment, runs a pretrained locomotion policy, and streams
sensor/odometry data over ROS 2 topics while accepting velocity commands.

This is a fork targeting Isaac Sim 4.5 + Isaac Lab 2.1 (upstream: `Zhefan-Xu/isaac-go2-ros2`),
plus a Docker setup contributed by SeanChangX.

## Running

There is no test suite, lint config, or package build. The project runs as a single script.

**Docker (recommended)** — `isaac-launch.sh` wraps docker compose in `docker/`:
```bash
./isaac-launch.sh run      # build ROS ws if needed + run isaac_go2_ros2.py
./isaac-launch.sh sim      # Isaac Sim GUI only
./isaac-launch.sh enter    # interactive shell in the container
./isaac-launch.sh build    # colcon build the ROS workspace
./isaac-launch.sh close    # docker compose down
./isaac-launch.sh --command "<cmd>"   # run an arbitrary command in the container
```
The container auto-activates the `isaaclab` conda env, sources ROS 2 Humble, and sets
`RMW_IMPLEMENTATION=rmw_cyclonedds_cpp`. `ROS_DOMAIN_ID` defaults to 100. The repo root is
bind-mounted to `/home/ubuntu/isaac-go2-ros2`, so source edits on the host take effect
immediately inside the container (no rebuild for Python changes).

**Native** — requires Isaac Sim 4.5, Isaac Lab 2.1, ROS 2 Humble installed locally:
```bash
conda activate isaaclab
python isaac_go2_ros2.py
```

**Visualize:** `rviz2 -d rviz/go2.rviz`

**Teleop keyboard (in the Isaac Sim window):** `W/A/S/D` translate, `Z/C` turn. With multiple
robots, env 1 uses `I/J/K/L` + `M/>`.

## Configuration

`cfg/sim.yaml` is the single Hydra config (loaded via `@hydra.main` in `isaac_go2_ros2.py`).
Key knobs:
- `env_name` — selects the scene; dispatched by the if/elif chain in `isaac_go2_ros2.py` to a
  `create_*_env()` function in `env/sim_env.py`. Options: `warehouse`, `warehouse-forklifts`,
  `warehouse-shelves`, `full-warehouse`, `obstacle-sparse/medium/dense`.
- `num_envs` — number of robots. **The bridge and teleop branch heavily on `num_envs == 1`
  vs `> 1`**: with 1 robot, topics/frames are `unitree_go2/...`; with multiple, they become
  `unitree_go2_{i}/...`. Any change touching topics, TF frames, or odometry must handle both.
- `freq` — control/publish frequency in Hz; must divide 200 (sim runs at `dt=0.005` → 200 Hz).
  `decimation` is derived as `ceil(1/dt/freq)`.
- `sensor.*` — toggles for lidar, color/depth/semantic camera.

Hydra writes per-run logs and config snapshots to `outputs/<date>/<time>/`.

## Architecture

The runtime is a single synchronous loop in `isaac_go2_ros2.py:run_simulator`. Each iteration:
`policy(obs)` → `env.step(actions)` → `dm.pub_ros2_data()` → `rclpy.spin_once(dm)` → optional
camera follow, with a sleep to hold real-time factor. Note `AppLauncher` must be constructed and
`simulation_app` obtained **before** importing any `isaaclab`/`omni`/`go2`/`ros2` modules — those
imports trigger Omniverse extension loading and fail if the app isn't up. Preserve that import
ordering.

Pieces, in dependency order:

- **`go2/go2_env.py`** — `Go2RSLEnvCfg`, an Isaac Lab `ManagerBasedRLEnvCfg`. Defines the scene
  (`Go2SimCfg`: ground, lights, the `UNITREE_GO2_CFG` articulation, foot contact sensor, height
  scanner) plus the observation/action/command manager terms. The policy observation vector is
  assembled here in a fixed order — **the order of `ObsTerm`s in `PolicyCfg` must match what the
  checkpoint was trained on**. `camera_follow()` (third-person camera) lives here too.

- **`go2/go2_ctrl.py`** — loads the RL locomotion policy via `rsl_rl`'s `OnPolicyRunner`.
  `get_rsl_rough_policy` (default, used in `isaac_go2_ros2.py`) loads `ckpts/unitree_go2/rough_model_7850.pt`;
  `get_rsl_flat_policy` uses the flat checkpoint and disables the height scan. Also owns the global
  `base_vel_cmd_input` tensor: keyboard events (`sub_keyboard_event`) and ROS `cmd_vel` both write
  into it, and `base_vel_cmd()` feeds it back as an observation term. This global is the single
  channel through which all velocity commands reach the policy.

- **`go2/go2_ctrl_cfg.py`** — the `rsl_rl` PPO/ActorCritic runner configs (`unitree_go2_flat_cfg`,
  `unitree_go2_rough_cfg`) as plain dicts, including which checkpoint file to load. The MLP hidden
  dims here must match the saved checkpoint.

- **`env/sim_env.py`** — scene builders. Warehouse/hospital/office pull USD assets from the Isaac
  Sim Nucleus asset server; the `obstacle-*` envs procedurally generate terrain via
  `env/terrain.py` + `env/terrain_cfg.py` (`HfUniformDiscreteObstaclesTerrainCfg`, a custom
  height-field terrain). Each builder also tags the ground with a semantic label for segmentation.

- **`go2/go2_sensors.py`** — `SensorManager` attaches an RTX lidar (`Hesai_XT32_SD10`) and a front
  RGB-D camera to each robot's base prim, returning lidar annotators and `Camera` objects.

- **`ros2/go2_ros2_bridge.py`** — `RobotDataManager` (an `rclpy.Node`) is the whole ROS 2 surface.
  Importing this module force-enables the Omniverse ROS 2 bridge extension. It publishes odom/pose
  (rate-limited by wall clock in `pub_ros2_data`, ~50 Hz odom / 15 Hz lidar), broadcasts TF
  (static base→lidar/camera transforms + dynamic map→base), and sets up camera image publishing
  through Isaac OmniGraph / Replicator writers (`pub_color_image`, `pub_depth_image`,
  `pub_semantic_image`, `publish_camera_info`). It subscribes to `cmd_vel` (writes the
  `go2_ctrl.base_vel_cmd_input` global) and to the raw semantic image (re-colorizes it for viz).
  A `/clock` publisher OmniGraph is created so ROS consumers can use sim time.

### Coordinate / quaternion convention

Isaac stores quaternions as `(w, x, y, z)`; ROS/`geometry_msgs` expects `(x, y, z, w)`. The bridge
reorders them everywhere (e.g. `orientation.x = base_rot[1]`, `...w = base_rot[0]`). When adding
any pose/transform publishing, follow this same reordering or orientations will be wrong.

## Gotchas

- Many publishers/frames are duplicated across a `num_envs == 1` branch and a `> 1` branch with
  different naming. Edit both.
- Checkpoints in `ckpts/unitree_go2/` are tied to the observation layout and network dims; changing
  observations or `go2_ctrl_cfg` dims requires a matching checkpoint.
- `freq` must divide 200; otherwise decimation math produces a mismatched control rate.
