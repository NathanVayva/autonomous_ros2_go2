import time

import pygame
import rclpy

from rclpy.node import Node
from geometry_msgs.msg import Twist


# =========================
# PARAMETERS
# =========================

LINEAR_SPEED = 0.60
LATERAL_SPEED = 0.40
ANGULAR_SPEED = 1.2

PUBLISH_RATE = 50.0          # Hz
COMMAND_TIMEOUT = 0.12       # seconds


# =========================
# KEYBOARD CONTROLLER
# =========================

class KeyboardController(Node):

    def __init__(self):

        super().__init__('keyboard_controller')

        self.publisher_ = self.create_publisher(
            Twist,
            '/cmd_vel_out',
            10
        )

        self.cmd = Twist()

        self.last_input_time = time.time()

        self.timer = self.create_timer(
            1.0 / PUBLISH_RATE,
            self.publish_cmd
        )

        self.print_help()

    def print_help(self):

        self.get_logger().info("")
        self.get_logger().info("========== GO2 KEYBOARD CONTROL ==========")
        self.get_logger().info("")
        self.get_logger().info("Movement:")
        self.get_logger().info("   z : forward")
        self.get_logger().info("   s : backward")
        self.get_logger().info("   q : left translation")
        self.get_logger().info("   d : right translation")
        self.get_logger().info("")
        self.get_logger().info("Rotation:")
        self.get_logger().info("   LEFT  : rotate left")
        self.get_logger().info("   RIGHT : rotate right")
        self.get_logger().info("")
        self.get_logger().info("Other:")
        self.get_logger().info("   SPACE : stop")
        self.get_logger().info("   ESC   : quit")
        self.get_logger().info("")
        self.get_logger().info("==========================================")
        self.get_logger().info("")

    def publish_cmd(self):

        now = time.time()

        # Auto stop if no recent keyboard input
        if now - self.last_input_time > COMMAND_TIMEOUT:
            self.stop_robot()

        self.publisher_.publish(self.cmd)

    def set_command(self, x=0.0, y=0.0, yaw=0.01):

        self.cmd.linear.x = x
        self.cmd.linear.y = y
        self.cmd.angular.z = yaw

        self.last_input_time = time.time()

    def stop_robot(self):

        # Conservation exacte de ton comportement
        self.set_command(
            x=0.0,
            y=0.0,
            yaw=0.01
        )

        self.last_input_time = time.time()


# =========================
# MAIN
# =========================

def main(args=None):

    rclpy.init(args=args)

    node = KeyboardController()

    pygame.init()

    # Petite fenêtre obligatoire pour pygame keyboard
    screen = pygame.display.set_mode((400, 120))
    pygame.display.set_caption("GO2 Keyboard Controller")

    clock = pygame.time.Clock()

    try:

        while rclpy.ok():

            rclpy.spin_once(node, timeout_sec=0.0)

            # Important pour mettre à jour l'état clavier
            pygame.event.pump()

            keys = pygame.key.get_pressed()

            # =========================
            # QUIT EVENTS
            # =========================

            for event in pygame.event.get():

                if event.type == pygame.QUIT:
                    raise KeyboardInterrupt

            # =========================
            # ESCAPE
            # =========================

            if keys[pygame.K_ESCAPE]:
                break

            # =========================
            # DEFAULT COMMAND
            # =========================

            x = 0.0
            y = 0.0

            # Conservation exacte de ton yaw idle
            yaw = 0.01

            key_pressed = False

            # =========================
            # TRANSLATION X
            # =========================

            if keys[pygame.K_z]:

                x = LINEAR_SPEED
                key_pressed = True

            elif keys[pygame.K_s]:

                x = -LINEAR_SPEED
                key_pressed = True

            # =========================
            # TRANSLATION Y
            # =========================

            if keys[pygame.K_q]:

                y = +LATERAL_SPEED
                key_pressed = True

            elif keys[pygame.K_d]:

                y = -LATERAL_SPEED
                key_pressed = True

            # =========================
            # ROTATION
            # =========================

            if keys[pygame.K_LEFT]:

                yaw = ANGULAR_SPEED
                key_pressed = True

            elif keys[pygame.K_RIGHT]:

                yaw = -ANGULAR_SPEED
                key_pressed = True

            # =========================
            # STOP
            # =========================

            if keys[pygame.K_SPACE]:

                x = 0.0
                y = 0.0
                yaw = 0.01

                key_pressed = True

            # =========================
            # APPLY COMMAND
            # =========================

            if key_pressed:

                node.set_command(
                    x=x,
                    y=y,
                    yaw=yaw
                )

            # =========================
            # FPS CONTROL
            # =========================

            clock.tick(PUBLISH_RATE)

    except KeyboardInterrupt:

        pass

    finally:

        node.stop_robot()

        # Publish stop several times
        for _ in range(5):

            node.publish_cmd()
            time.sleep(0.02)

        pygame.quit()

        node.destroy_node()

        rclpy.shutdown()


if __name__ == '__main__':

    main()
