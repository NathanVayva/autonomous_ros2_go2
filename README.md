# autonomous_ros2_go2

Integration workspace for an **autonomous Unitree Go2** quadruped: it brings a ROS 2
control/perception stack and an **Isaac Sim 4.5** simulation of the robot together under a
single **Docker** setup, as a base for autonomous navigation and (in progress) LLM/VLM-driven
high-level planning.

> **This repository stands on third-party work.** The two main components are open-source
> projects by other authors (see [Credits](#credits)). My own contribution is the integration
> layer between them, not the SDK or the simulator — see [What I contributed](#what-i-contributed).

## Layout

- **`go2_ros2_sdk/`** — the community ROS 2 SDK for the Go2 (WebRTC / CycloneDDS bridge,
  telemetry → ROS 2 topics, SLAM / Nav2 / teleop launch files). *Upstream.*
- **`isaac-go2-ros2-isaacsim-4.5-docker/`** — a Go2 simulation on **Isaac Sim 4.5 / Isaac Lab
  2.1** that streams sensor/odometry data over ROS 2 Humble and takes velocity commands.
  *Fork of an upstream project (see Credits).*

## What I contributed

- **Wired the SDK to the Isaac Sim simulation** so the same ROS 2 control/perception stack
  runs against the simulated Go2 (topic/frame plumbing between the two components).
- **Dockerized and orchestrated the stack** so it builds and runs reproducibly on my machine
  (single-GPU laptop, Isaac Sim in a container alongside the ROS 2 workspace).

Everything under `go2_ros2_sdk/` and the Isaac simulation itself is upstream work; the value I
added is making the two run together end-to-end.

## Roadmap (work in progress — not yet done)

- **High-level planning with a VLM/LLM** on top of the stack (mission-level commands →
  navigation goals). *Not wired up yet.*
- **Replacing Nav2** with a planner better suited to a **quadruped** specifically (legged
  locomotion / footstep-aware navigation rather than the differential-drive assumptions of
  the default Nav2 setup). *Under study.*

## Credits

- **Go2 ROS 2 SDK** — RoboVerse community / `abizovnuralem`:
  https://github.com/abizovnuralem/go2_ros2_sdk (BSD-2-Clause). Depends on a patched
  `aioice` fork by `legion1581`.
- **Isaac Sim Go2 simulation** — fork of `Zhefan-Xu/isaac-go2-ros2`
  (https://github.com/Zhefan-Xu/isaac-go2-ros2), with Docker support originally by `SeanChangX`.

Please refer to each subproject's own `LICENSE` and README for the terms and full author list.
