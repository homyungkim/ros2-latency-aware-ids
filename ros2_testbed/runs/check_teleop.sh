#!/bin/bash
# Run inside the teleop container: docker compose exec teleop bash /data/check_teleop.sh
source /opt/ros/jazzy/setup.bash
echo "--- topics visible from teleop ---"; ros2 topic list | grep -E "joint|clock"
echo "--- /joint_states rate seen from teleop (cross-container) ---"; timeout 5 ros2 topic hz /joint_states | tail -2
echo "--- subscribers of the trajectory topic ---"; ros2 topic info /joint_trajectory_controller/joint_trajectory
