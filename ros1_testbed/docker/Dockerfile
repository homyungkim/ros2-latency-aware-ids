# ROS 1 (Noetic) testbed: Gazebo Classic + UR5e, TCPROS traffic as in ROSIDS23. One image for sim/teleop/attacker.
FROM ros:noetic-robot
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
      ros-noetic-ur-gazebo ros-noetic-ur-description ros-noetic-ros-controllers ros-noetic-gazebo-ros-control \
      ros-noetic-control-msgs ros-noetic-trajectory-msgs \
      python3-numpy hping3 iproute2 iputils-ping procps \
    && rm -rf /var/lib/apt/lists/*
COPY nodes/ /opt/testbed/
RUN chmod +x /opt/testbed/*.sh
ENV PYTHONUNBUFFERED=1
SHELL ["/bin/bash", "-c"]
ENTRYPOINT ["/opt/testbed/entrypoint.sh"]
