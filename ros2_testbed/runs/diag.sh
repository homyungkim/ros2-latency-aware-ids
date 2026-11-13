#!/bin/bash
# Cross-container diagnostics. Run:  docker compose exec teleop bash /data/diag.sh
source /opt/ros/jazzy/setup.bash
echo "=== 1. name resolution and ping ==="; getent hosts sim; ping -c 2 -W 1 sim | tail -2
echo "=== 2. environment ==="; printenv | grep -E "^(ROS|FASTDDS|RMW)" | sort
echo "=== 3. my IP ==="; hostname -i
echo "=== 4. topics (no daemon, 5 s discovery) ==="; timeout 8 ros2 topic list --no-daemon --spin-time 5
echo "=== 5. nodes (no daemon) ==="; timeout 8 ros2 node list --no-daemon --spin-time 5
