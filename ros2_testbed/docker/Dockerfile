# One image for all testbed containers (simulation, teleoperation/recorder, IDS, attacker).
FROM ros:jazzy-ros-base
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
      ros-jazzy-ur-simulation-gz ros-jazzy-ur-description ros-jazzy-ros-gz \
      ros-jazzy-gz-ros2-control ros-jazzy-joint-trajectory-controller ros-jazzy-joint-state-broadcaster \
      ros-jazzy-control-msgs ros-jazzy-trajectory-msgs \
      python3-pip python3-numpy python3-pandas \
      tcpdump tcpreplay hping3 iproute2 iputils-ping procps \
    && rm -rf /var/lib/apt/lists/*
COPY nodes/ /opt/testbed/
RUN chmod +x /opt/testbed/*.sh
ENV ROS_DOMAIN_ID=7 PYTHONUNBUFFERED=1
SHELL ["/bin/bash", "-c"]
ENTRYPOINT ["/opt/testbed/entrypoint.sh"]
