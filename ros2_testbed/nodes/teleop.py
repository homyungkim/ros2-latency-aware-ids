"""Teleoperation node: repeatedly sends a pick-and-place trajectory to the joint trajectory controller."""
import rclpy
from rclpy.node import Node
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint
from builtin_interfaces.msg import Duration

JOINTS = ["shoulder_pan_joint", "shoulder_lift_joint", "elbow_joint", "wrist_1_joint", "wrist_2_joint", "wrist_3_joint"]
# home -> above pick -> pick -> above pick -> above place -> place -> above place -> home (rad), 1.5 s apart
WAYPOINTS = [
    [0.0, -1.57, 1.57, -1.57, -1.57, 0.0],
    [0.6, -1.20, 1.60, -1.97, -1.57, 0.0],
    [0.6, -1.00, 1.75, -2.32, -1.57, 0.0],
    [0.6, -1.20, 1.60, -1.97, -1.57, 0.0],
    [-0.6, -1.20, 1.60, -1.97, -1.57, 0.5],
    [-0.6, -1.00, 1.75, -2.32, -1.57, 0.5],
    [-0.6, -1.20, 1.60, -1.97, -1.57, 0.5],
    [0.0, -1.57, 1.57, -1.57, -1.57, 0.0],
]
STEP_S = 1.5


class Teleop(Node):
    def __init__(self):
        super().__init__("teleop")
        self.pub = self.create_publisher(JointTrajectory, "/joint_trajectory_controller/joint_trajectory", 10)
        period = STEP_S * len(WAYPOINTS)
        self.timer = self.create_timer(period, self.send)
        self.create_timer(2.0, self.send_once)   # first trajectory shortly after start
        self.first = True

    def send_once(self):
        if self.first:
            self.first = False
            self.send()

    def send(self):
        msg = JointTrajectory(); msg.joint_names = JOINTS
        for k, q in enumerate(WAYPOINTS, start=1):
            t = STEP_S * k
            msg.points.append(JointTrajectoryPoint(positions=q, time_from_start=Duration(sec=int(t), nanosec=int((t % 1) * 1e9))))
        self.pub.publish(msg)
        self.get_logger().info("pick-and-place trajectory sent")


def main():
    rclpy.init(); n = Teleop()
    try:
        rclpy.spin(n)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
