import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist

import sys
import tty
import termios

MOVE_SPEED = 0.3
TURN_SPEED = 0.8

class KeyboardController(Node):

    def __init__(self):
        super().__init__('keyboard_controller')

        self.publisher_ = self.create_publisher(
            Twist,
            '/cmd_vel_teleop',
            10
        )

        self.get_logger().info("Keyboard controller started")

    def get_key(self):
        tty.setraw(sys.stdin.fileno())
        key = sys.stdin.read(1)
        termios.tcsetattr(
            sys.stdin,
            termios.TCSADRAIN,
            self.settings
        )
        return key

    def run(self):

        self.settings = termios.tcgetattr(sys.stdin)

        print("")
        print("Controls:")
        print("w = forward")
        print("s = backward")
        print("a = left")
        print("d = right")
        print("space = stop")
        print("q = quit")
        print("")

        while True:

            key = self.get_key()

            msg = Twist()

            if key == 'z':
                msg.linear.x = MOVE_SPEED

            elif key == 's':
                msg.linear.x = -MOVE_SPEED

            elif key == 'q':
                msg.angular.z = TURN_SPEED

            elif key == 'd':
                msg.angular.z = -TURN_SPEED

            elif key == ' ':
                pass

            elif key == 'a':
                break

            self.publisher_.publish(msg)

def main(args=None):

    rclpy.init(args=args)

    controller = KeyboardController()

    controller.run()

    controller.destroy_node()

    rclpy.shutdown()

if __name__ == '__main__':
    main()
