import time

import pygame
import rclpy

from rclpy.node import Node
from geometry_msgs.msg import Twist
from action_msgs.srv import CancelGoal


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

        # Publie sur un topic DÉDIÉ (plus sur /cmd_vel_out partagé) : il passe par
        # twist_mux en priorité MAX -> le pilotage humain prime sur Nav2 (garde-fou).
        # Au relâchement des touches il se tait (silence-au-repos ci-dessous) -> le
        # mux time out sur cmd_vel_key et Nav2 reprend la main.
        self.publisher_ = self.create_publisher(
            Twist,
            '/cmd_vel_key',
            10
        )

        self.cmd = Twist()

        # GARDE-FOU : dès qu'on prend la main, on annule le goal Nav2 actif, sinon
        # au relâchement le robot y RETOURNE. Service action cancel_goal : requête
        # vide (UUID + stamp à zéro) = annule TOUS les goals en cours.
        self.cancel_cli = self.create_client(
            CancelGoal, '/navigate_to_pose/_action/cancel_goal')
        self.human_driving = False   # état frame précédente -> détecte le front montant

        # 0.0 (et non time.time()) -> silencieux au démarrage jusqu'à la 1re
        # touche : ne publie rien tant qu'on ne pilote pas (ne gêne pas Nav2).
        self.last_input_time = 0.0

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

        if now - self.last_input_time > COMMAND_TIMEOUT + (5.0 / PUBLISH_RATE):

            return  # Don't publish if no recent input and not in the last few ticks

        # Auto stop if no recent keyboard input
        if now - self.last_input_time > COMMAND_TIMEOUT:

            self.stop_robot()

        self.publisher_.publish(self.cmd)

    def take_over(self, driving):
        # front montant (idle -> pilote) : annule le goal Nav2 -> pas de retour au relâchement.
        # fire-and-forget : si Nav2 n'est pas là, call_async est sans effet.
        if driving and not self.human_driving:
            self.cancel_cli.call_async(CancelGoal.Request())
            self.get_logger().info("prise de contrôle -> goal Nav2 annulé")
        self.human_driving = driving

    def set_command(self, x=0.0, y=0.0, yaw=0.0):

        self.cmd.linear.x = x
        self.cmd.linear.y = y
        self.cmd.angular.z = yaw

        self.last_input_time = time.time()

    def stop_robot(self):

        # Met la commande à zéro SANS toucher last_input_time : sinon le garde de
        # publish_cmd (>0.22 s -> plus rien) ne se déclenche jamais, on garderait la
        # priorité MAX du mux en permanence et Nav2 ne reprendrait JAMAIS la main.
        self.cmd.linear.x = 0.0
        self.cmd.linear.y = 0.0
        self.cmd.angular.z = 0.0


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
            yaw = 0.0   

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
                yaw = 0.0

                key_pressed = True

            # =========================
            # APPLY COMMAND
            # =========================

            # garde-fou : annule le goal Nav2 au front montant de la prise de contrôle
            node.take_over(key_pressed)

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
