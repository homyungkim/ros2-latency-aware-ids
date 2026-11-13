#!/bin/bash
# Headless Gazebo Harmonic + UR5e + ros2_control at 500 Hz
source /opt/ros/jazzy/setup.bash
SHARE=$(ros2 pkg prefix ur_simulation_gz)/share/ur_simulation_gz
SRC=$(ls $SHARE/config/*controllers*.yaml 2>/dev/null | head -1)
if [ -n "$SRC" ]; then
  # keep the package's own controller list, only force the controller-manager rate to 500 Hz
  sed -E 's/update_rate: *[0-9]+/update_rate: 500/' "$SRC" > /tmp/controllers.yaml
  echo "controllers: $SRC (update_rate -> 500)"; grep -m1 update_rate /tmp/controllers.yaml
else
  cp /opt/testbed/controllers_500hz.yaml /tmp/controllers.yaml
  echo "controllers: fallback controllers_500hz.yaml"
fi
exec ros2 launch ur_simulation_gz ur_sim_control.launch.py ur_type:=ur5e \
     launch_rviz:=false gazebo_gui:=false \
     controllers_file:=/tmp/controllers.yaml \
     initial_joint_controller:=joint_trajectory_controller
