FROM ros:humble-ros-base

# Install basic requirements
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gnupg2 \
    lsb-release \
    python3-pip \
    portaudio19-dev \
    mesa-utils \
    libgl1-mesa-glx \
    libgl1-mesa-dri \
    ros-humble-rviz2 \
    software-properties-common \
    ros-humble-rmw-cyclonedds-cpp \
    ffmpeg\
    ros-humble-vision-msgs \
    nano



# Install specific numpy version first
RUN pip install 'numpy<2.0.0'

# Create workspace
WORKDIR /ros2_ws

# Clone the repository with submodules
COPY . /ros2_ws/src

# Install Python requirements (with numpy constraint)
RUN cd src && pip install -r requirements.txt

# Install ROS dependencies
RUN . /opt/ros/${ROS_DISTRO}/setup.sh && \
    rosdep install --from-paths src --ignore-src -r -y

# go2_ai : deps d'inference VLM locale (Qwen3-VL). Installées AVANT le pin de
# setuptools ci-dessous, car elles remontent setuptools (ex. 83.x) — on veut que
# ce soit le pin qui gagne, pas ces deps.
RUN pip install transformers accelerate bitsandbytes

# pip (requirements + deps VLM ci-dessus) remonte setuptools (ex. 83.x), ce qui
# casse le build ament_python de ROS Humble : "canonicalize_version() got an
# unexpected keyword argument 'strip_trailing_zero'". On restaure la version
# d'origine (défaut Humble) EN DERNIER, pour qu'elle persiste dans l'image finale
# (utile aussi pour les `colcon build` refaits à la main dans le conteneur).
# Vérifié : 83.0.0 -> Failed, 59.6.0 -> OK.
RUN pip install "setuptools==59.6.0"

# Build the workspace
RUN . /opt/ros/${ROS_DISTRO}/setup.sh && \
    colcon build

# Source ROS2 and workspace in bashrc
RUN echo "source /opt/ros/${ROS_DISTRO}/setup.bash" >> /root/.bashrc && \
    echo "source /ros2_ws/install/setup.bash" >> /root/.bashrc

# Set environment variables
ENV ROBOT_IP=""
ENV CONN_TYPE="webrtc"
ENV WEBRTC_SERVER_HOST="0.0.0.0"
ENV WEBRTC_SERVER_PORT="9991"

# Remove apt cache
RUN rm -rf /var/lib/apt/lists/*

# add /ros2_ws to the entrypoint
RUN sed --in-place --expression \
      '$isource "/ros2_ws/install/setup.bash"' \
      /ros_entrypoint.sh

#CMD ["ros2", "launch", "go2_robot_sdk", "robot.launch.py"]
CMD ["tail", "-f", "/dev/null"]
