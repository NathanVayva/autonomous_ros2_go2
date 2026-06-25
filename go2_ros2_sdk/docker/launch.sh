#!/bin/bash
# Launcher for the go2_robot_sdk container.
#
# ONE image, ONE service (`unitree_ros`). The backend is chosen at run time by
# CONN_TYPE, not by a separate image:
#   real -> CONN_TYPE=webrtc   (drives the physical robot)
#   sim  -> CONN_TYPE=sim      (talks to Isaac Sim over the ROS graph)
#
# In sim mode this ALSO launches the Isaac Sim container (separate project) so a
# single command brings up both halves. Both MUST share ROS_DOMAIN_ID to discover
# each other on the (host) DDS graph — that is enforced below.
#
#   ./launch.sh real          # run the SDK driver against the real robot
#   ./launch.sh sim           # launch Isaac Sim + run the SDK driver in sim mode
#   ./launch.sh shell [real|sim]   # start the container + a shell (no driver)
#   ./launch.sh enter         # open a shell in the already-running container
#   ./launch.sh build         # (re)build the SDK image
#   ./launch.sh down          # stop & remove the SDK container (+ Isaac if running)
set -e
cd "$(dirname "$0")"
xhost +local:docker >/dev/null 2>&1 || true   # allow GUI (RViz) from the container

SERVICE=unitree_ros
# Where the Isaac Sim project lives. Override with: ISAAC_DIR=/path ./launch.sh sim
ISAAC_DIR="${ISAAC_DIR:-../../isaac-go2-ros2-isaacsim-4.5-docker}"
ISAAC_LOG="${ISAAC_LOG:-/tmp/isaac-sim.log}"
# Both halves must live on the SAME ROS domain to see each other. Default 0.
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"

# Run the SDK driver inside the container with the chosen connection type.
# `exec` does not run the image entrypoint, so we source ROS + the workspace here.
run_driver() {
    local conn="$1"; shift
    docker compose up -d
    # /ros2_ws/install lives INSIDE the container (not mounted) and is reset whenever
    # the container is recreated (e.g. after `down`), reverting to the image's baked
    # build. Rebuild the SDK from the mounted src so the running code matches the source
    # (incl. the sim backend). --symlink-install makes later Python edits live.
    echo "==> building go2_robot_sdk from mounted src..."
    docker compose exec "$SERVICE" bash -lc \
        'source /opt/ros/${ROS_DISTRO}/setup.bash && cd /ros2_ws && \
         colcon build --packages-select go2_robot_sdk --symlink-install'
    docker compose exec \
        -e CONN_TYPE="$conn" \
        -e ROBOT_IP="${ROBOT_IP:-}" \
        -e ROBOT_TOKEN="${ROBOT_TOKEN:-}" \
        -e ROS_DOMAIN_ID="$ROS_DOMAIN_ID" \
        "$SERVICE" bash -lc '
            source /opt/ros/${ROS_DISTRO}/setup.bash &&
            source /ros2_ws/install/setup.bash &&
            ros2 launch go2_robot_sdk robot.launch.py '"$*"
}

# Launch Isaac Sim (its own project/container) in the background, on OUR domain.
start_isaac() {
    if docker ps --filter "name=isaac-go2-ros2" --filter "status=running" \
            | grep -q "isaac-go2-ros2"; then
        echo "==> Isaac Sim already running — not starting a second instance."
        return 0
    fi
    if [ ! -x "$ISAAC_DIR/isaac-launch.sh" ]; then
        echo "WARN: Isaac launcher not found at '$ISAAC_DIR' — skipping Isaac startup."
        echo "      Start it yourself, or set ISAAC_DIR=/path/to/isaac-go2-ros2-isaacsim-4.5-docker"
        return 0
    fi
    echo "==> launching Isaac Sim (ROS_DOMAIN_ID=$ROS_DOMAIN_ID), logs -> $ISAAC_LOG"
    echo "    (first run takes several minutes: asset load + shader compile)"
    ( cd "$ISAAC_DIR" && ROS_DOMAIN_ID="$ROS_DOMAIN_ID" ./isaac-launch.sh run ) \
        >"$ISAAC_LOG" 2>&1 &
}

stop_isaac() {
    if [ -x "$ISAAC_DIR/isaac-launch.sh" ]; then
        ( cd "$ISAAC_DIR" && ./isaac-launch.sh close ) || true
    fi
}

case "${1:-}" in
    real)
        run_driver webrtc "${@:2}"
        ;;
    sim)
        # Sim needs EXACTLY ONE robot ip to land in `single` mode (bare topics,
        # go2.urdf). The value itself is unused in sim — it is only a robot counter.
        : "${ROBOT_IP:=127.0.0.1}"
        export ROBOT_IP
        start_isaac
        run_driver sim "${@:2}"
        ;;
    shell)
        case "${2:-real}" in
            real) CONN=webrtc ;;
            sim)  CONN=sim ;;
            *) echo "Usage: ./launch.sh shell [real|sim]"; exit 1 ;;
        esac
        docker compose up -d
        docker compose exec -e CONN_TYPE="$CONN" -e ROBOT_IP="${ROBOT_IP:-}" \
            -e ROBOT_TOKEN="${ROBOT_TOKEN:-}" -e ROS_DOMAIN_ID="$ROS_DOMAIN_ID" \
            "$SERVICE" bash
        ;;
    enter)
        docker compose exec "$SERVICE" bash
        ;;
    build)
        docker compose build
        ;;
    down)
        docker compose down
        stop_isaac
        ;;
    *)
        echo "Usage: ./launch.sh {real|sim|shell [real|sim]|enter|build|down}"
        exit 1
        ;;
esac
