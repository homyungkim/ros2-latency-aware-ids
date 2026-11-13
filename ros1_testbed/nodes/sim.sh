#!/bin/bash
# roscore + headless Gazebo Classic + UR5e with the effort joint trajectory controller.
# ur_gazebo runs ros_control at the Gazebo physics rate (1 kHz) and publishes /joint_states at 500 Hz.
source /opt/ros/noetic/setup.bash
export ROS_HOSTNAME=sim
exec roslaunch ur_gazebo ur5e_bringup.launch gazebo_gui:=false
