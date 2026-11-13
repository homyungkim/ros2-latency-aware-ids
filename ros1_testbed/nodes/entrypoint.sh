#!/bin/bash
source /opt/ros/noetic/setup.bash
export ROS_HOSTNAME=$(hostname)
exec "$@"
