#!/usr/bin/env python3
"""ROS 1 teleoperation node: repeats the same pick-and-place trajectory as the ROS 2 testbed."""
import rospy
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint
J = ["shoulder_pan_joint", "shoulder_lift_joint", "elbow_joint", "wrist_1_joint", "wrist_2_joint", "wrist_3_joint"]
W = [[0.0, -1.57, 1.57, -1.57, -1.57, 0.0], [0.6, -1.20, 1.60, -1.97, -1.57, 0.0], [0.6, -1.00, 1.75, -2.32, -1.57, 0.0],
     [0.6, -1.20, 1.60, -1.97, -1.57, 0.0], [-0.6, -1.20, 1.60, -1.97, -1.57, 0.5], [-0.6, -1.00, 1.75, -2.32, -1.57, 0.5],
     [-0.6, -1.20, 1.60, -1.97, -1.57, 0.5], [0.0, -1.57, 1.57, -1.57, -1.57, 0.0]]
STEP = 1.5
rospy.init_node("teleop")
pub = rospy.Publisher("/eff_joint_traj_controller/command", JointTrajectory, queue_size=10)
rospy.sleep(2.0)
while not rospy.is_shutdown():
    m = JointTrajectory(); m.joint_names = J
    for k, q in enumerate(W, start=1):
        m.points.append(JointTrajectoryPoint(positions=q, time_from_start=rospy.Duration(STEP * k)))
    pub.publish(m); rospy.loginfo("pick-and-place trajectory sent")
    rospy.sleep(STEP * len(W))
