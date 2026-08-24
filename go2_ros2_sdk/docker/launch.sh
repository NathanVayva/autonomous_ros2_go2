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

# --- Isaac Sim render/perf preset (sim mode only) ----------------------------
# Heavier rendering => lower real-time factor (RTF). SIM_PERF picks how much
# Isaac renders; it expands to Hydra overrides for isaac_go2_ros2.py. Fine-tune
# or override anything with SIM_ARGS (raw Hydra, appended LAST so it wins).
#   SIM_PERF=max   -> max RTF: keep lidar (SLAM) + color cam, drop depth+semantic+cam-follow
#   SIM_PERF=light -> also drop the color camera (lightest; no Go2 vision)
#   SIM_PERF=full  -> cfg/sim.yaml untouched (default, heaviest)
# Also accepted (so natural commands "just work"):
#   HEADLESS=1            -> run Isaac without its GUI viewport (also accepts lowercase `headless`)
#   env_name=... freq=... -> common Hydra knobs promoted from the env into overrides
# Precedence (later wins, deduped per key): preset < promoted env vars < SIM_ARGS.
# Examples:
#   SIM_PERF=max ROBOT_IP=192.168.12.1 ./launch.sh sim
#   HEADLESS=1 SIM_PERF=light env_name=obstacle-sparse SIM_ARGS="freq=25" ./launch.sh sim rviz2:=false
build_sim_args() {
    local preset="${SIM_PERF:-full}"
    local args=""
    case "$preset" in
        max)
            args="camera_follow=false sensor.depth_image=false sensor.semantic_segmentation=false" ;;
        light)
            args="camera_follow=false sensor.enable_camera=false sensor.depth_image=false sensor.semantic_segmentation=false" ;;
        full)
            args="" ;;
        *)
            echo "WARN: unknown SIM_PERF='$preset' (expected max|light|full) — using full." >&2
            args="" ;;
    esac

    # Promote common Hydra knobs from the environment (names match cfg/sim.yaml keys),
    # so e.g. `env_name=obstacle-sparse ./launch.sh sim` works without wrapping in SIM_ARGS.
    local promoted="" k
    for k in env_name freq num_envs camera_follow; do
        if [ -n "${!k:-}" ]; then promoted="$promoted $k=${!k}"; fi
    done

    # Headless: accept HEADLESS or headless, case-insensitive truthy. Drops the Isaac GUI
    # viewport (biggest RTF lever on a muxless laptop); --enable_cameras keeps offscreen
    # sensor rendering so the RTX lidar still feeds SLAM. These are AppLauncher --flags,
    # routed past Hydra by isaac_go2_ros2.py (parse_known_args + sys.argv rewrite).
    local hl="${HEADLESS:-${headless:-}}"; local flags=""
    case "${hl,,}" in
        1|true|yes|on) flags="--headless --enable_cameras" ;;
    esac

    # Merge preset + promoted + SIM_ARGS; keep only the LAST value per key=… (Hydra rejects
    # a key given twice). Non key=value tokens (none expected here) pass through.
    local kv
    kv="$(printf '%s\n' $args $promoted ${SIM_ARGS:-} \
          | awk -F= 'NF{v[$1]=$0} END{for (key in v) printf "%s ", v[key]}')"
    echo "${flags}${flags:+ }${kv}" | xargs
}

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

# Records the SIM_ARGS the running Isaac was launched with, so we can tell whether a
# reuse is safe or whether the requested mode (e.g. HEADLESS) actually changed.
ISAAC_ARGS_MARKER="${ISAAC_ARGS_MARKER:-/tmp/isaac-sim.args}"

# Launch Isaac Sim (its own project/container) in the background, on OUR domain.
# IMPORTANT: a running Isaac is only reused when its launch args match the requested
# ones. Otherwise it is restarted — otherwise HEADLESS / SIM_ARGS changes are silently
# ignored (you'd keep whatever mode the leftover instance was started in).
start_isaac() {
    if docker ps --filter "name=isaac-go2-ros2" --filter "status=running" \
            | grep -q "isaac-go2-ros2"; then
        local prev=""; [ -f "$ISAAC_ARGS_MARKER" ] && prev="$(cat "$ISAAC_ARGS_MARKER")"
        if [ "$prev" = "$ISAAC_SIM_ARGS" ]; then
            echo "==> Isaac Sim already running with the same args — reusing it."
            return 0
        fi
        echo "==> Isaac Sim running with DIFFERENT args — restarting to apply the new mode."
        echo "    was: [${prev:-<none>}]"
        echo "    now: [${ISAAC_SIM_ARGS:-<none>}]"
        stop_isaac
        # wait for the container to actually disappear before relaunching
        for _ in $(seq 1 30); do
            docker ps --filter "name=isaac-go2-ros2" --filter "status=running" \
                | grep -q "isaac-go2-ros2" || break
            sleep 1
        done
    fi
    if [ ! -x "$ISAAC_DIR/isaac-launch.sh" ]; then
        echo "WARN: Isaac launcher not found at '$ISAAC_DIR' — skipping Isaac startup."
        echo "      Start it yourself, or set ISAAC_DIR=/path/to/isaac-go2-ros2-isaacsim-4.5-docker"
        return 0
    fi
    echo "==> launching Isaac Sim (ROS_DOMAIN_ID=$ROS_DOMAIN_ID, SIM_PERF=${SIM_PERF:-full}), logs -> $ISAAC_LOG"
    echo "    Hydra overrides: ${ISAAC_SIM_ARGS:-<none>}"
    echo "    (first run takes several minutes: asset load + shader compile)"
    printf '%s' "$ISAAC_SIM_ARGS" > "$ISAAC_ARGS_MARKER"
    ( cd "$ISAAC_DIR" && ROS_DOMAIN_ID="$ROS_DOMAIN_ID" SIM_ARGS="$ISAAC_SIM_ARGS" ./isaac-launch.sh run ) \
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
        ISAAC_SIM_ARGS="$(build_sim_args)"
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
