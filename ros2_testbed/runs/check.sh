#!/bin/bash
# Health check inside the sim container:  docker compose exec sim bash /data/check.sh
source /opt/ros/jazzy/setup.bash
echo "--- controllers ---"
ros2 service call /controller_manager/list_controllers controller_manager_msgs/srv/ListControllers \
  | grep -oE "name='[a-z_]+'|state='[a-z]+'" | paste - -
echo "--- update_rate ---"
ros2 param get /controller_manager update_rate
echo "--- /joint_states rate ---"
timeout 5 ros2 topic hz /joint_states | tail -2
echo "--- joint positions, 3 s apart (should differ while teleop runs) ---"
ros2 topic echo --once --field position /joint_states | head -6 | tr '\n' ' '; echo
sleep 3
ros2 topic echo --once --field position /joint_states | head -6 | tr '\n' ' '; echo
