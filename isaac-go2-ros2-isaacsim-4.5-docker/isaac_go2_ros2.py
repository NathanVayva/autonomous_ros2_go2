import os
import sys
import shlex
import hydra
import rclpy
import torch
import time
import math
import argparse
from isaaclab.app import AppLauncher

# Inject Hydra overrides from the SIM_ARGS env var (set by docker/launch.sh's
# perf preset) into sys.argv so @hydra.main picks them up. Done here because the
# entrypoint is baked into the image, while this script is bind-mounted (live).
# e.g. SIM_ARGS="sensor.depth_image=false freq=25"
_sim_args = shlex.split(os.environ.get("SIM_ARGS", ""))
if _sim_args:
    print(f"[isaac_go2_ros2] applying Hydra overrides from SIM_ARGS: {_sim_args}")
    sys.argv.extend(_sim_args)

# add argparse arguments
parser = argparse.ArgumentParser(description="Tutorial on running the cartpole RL environment.")

# append AppLauncher cli args
AppLauncher.add_app_launcher_args(parser)
# parse_known_args: AppLauncher flags (e.g. --headless, --enable_cameras) go into
# args_cli; Hydra key=value overrides come back as `hydra_overrides`. We then rebuild
# sys.argv with ONLY the Hydra overrides so @hydra.main doesn't choke on the --flags.
args_cli, hydra_overrides = parser.parse_known_args()
sys.argv = [sys.argv[0]] + hydra_overrides

# launch omniverse app
app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

"""Rest everything follows."""

# The headless rendering kit (used with --headless --enable_cameras) does not
# auto-load the camera sensor extension, yet go2/go2_sensors.py imports it at module
# top -> ModuleNotFoundError: 'isaacsim.sensors'. Force-enable it before that import
# (same pattern as the ROS2 bridge extension in go2_ros2_bridge.py). No-op if already on.
import omni.kit.app
omni.kit.app.get_app().get_extension_manager().set_extension_enabled_immediate(
    "isaacsim.sensors.camera", True)

import torch

from go2.go2_env import Go2RSLEnvCfg, camera_follow
import env.sim_env as sim_env
import go2.go2_sensors as go2_sensors
import omni
import carb
import go2.go2_ctrl as go2_ctrl
import ros2.go2_ros2_bridge as go2_ros2_bridge

FILE_PATH = os.path.join(os.path.dirname(__file__), "cfg")
@hydra.main(config_path=FILE_PATH, config_name="sim", version_base=None)
def run_simulator(cfg):

    # Go2 Environment setup
    go2_env_cfg = Go2RSLEnvCfg()
    go2_env_cfg.scene.num_envs = cfg.num_envs
    go2_env_cfg.decimation = math.ceil(1./go2_env_cfg.sim.dt/cfg.freq)
    go2_env_cfg.sim.render_interval = go2_env_cfg.decimation
    go2_ctrl.init_base_vel_cmd(cfg.num_envs)
    # env, policy = go2_ctrl.get_rsl_flat_policy(go2_env_cfg)
    env, policy = go2_ctrl.get_rsl_rough_policy(go2_env_cfg)

    # Simulation environment
    if (cfg.env_name == "obstacle-dense"):
        sim_env.create_obstacle_dense_env() # obstacles dense
    elif (cfg.env_name == "obstacle-medium"):
        sim_env.create_obstacle_medium_env() # obstacles medium
    elif (cfg.env_name == "obstacle-sparse"):
        sim_env.create_obstacle_sparse_env() # obstacles sparse
    elif (cfg.env_name == "warehouse"):
        sim_env.create_warehouse_env() # warehouse
    elif (cfg.env_name == "warehouse-forklifts"):
        sim_env.create_warehouse_forklifts_env() # warehouse forklifts
    elif (cfg.env_name == "warehouse-shelves"):
        sim_env.create_warehouse_shelves_env() # warehouse shelves
    elif (cfg.env_name == "full-warehouse"):
        sim_env.create_full_warehouse_env() # full warehouse

    # Sensor setup
    sm = go2_sensors.SensorManager(cfg.num_envs)
    lidar_annotators = sm.add_rtx_lidar()
    cameras = sm.add_camera(cfg.freq)

    # Keyboard control
    system_input = carb.input.acquire_input_interface()
    system_input.subscribe_to_keyboard_events(
        omni.appwindow.get_default_app_window().get_keyboard(), go2_ctrl.sub_keyboard_event)
    
    # ROS2 Bridge
    rclpy.init()
    dm = go2_ros2_bridge.RobotDataManager(env, lidar_annotators, cameras, cfg)

    # Run simulation
    sim_step_dt = float(go2_env_cfg.sim.dt * go2_env_cfg.decimation)
    obs, _ = env.reset()
    while simulation_app.is_running():
        start_time = time.time()
        with torch.inference_mode():            
            # control joints
            actions = policy(obs)

            # step the environment
            obs, _, _, _ = env.step(actions)

            # Headless has no viewport to pump the renderer, so the RTX lidar/camera
            # render products never refresh and their annotator .get_data() blocks the
            # loop after ~2 steps. Force one render per iteration when headless (the GUI
            # path already renders via the viewport, so skip it there to save RTF).
            if args_cli.headless:
                env.unwrapped.sim.render()

            # # ROS2 data
            dm.pub_ros2_data()
            rclpy.spin_once(dm)

            # Camera follow
            if (cfg.camera_follow):
                camera_follow(env)

            # limit loop time
            elapsed_time = time.time() - start_time
            if elapsed_time < sim_step_dt:
                sleep_duration = sim_step_dt - elapsed_time
                time.sleep(sleep_duration)
        actual_loop_time = time.time() - start_time
        rtf = min(1.0, sim_step_dt/elapsed_time)
        print(f"\rStep time: {actual_loop_time*1000:.2f}ms, Real Time Factor: {rtf:.2f}", end='', flush=True)
    
    dm.destroy_node()
    rclpy.shutdown()
    simulation_app.close()

if __name__ == "__main__":
    run_simulator()
    
