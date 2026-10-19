# Copyright (c) 2026, Nathan
# SPDX-License-Identifier: BSD-3-Clause

"""Keyboard teleop for the Go2.

Uses only the Python standard library (sys/tty/termios/select) plus rclpy and
geometry_msgs, so it runs in the SDK Docker image with no extra dependencies.

Reads the keyboard in non-blocking raw mode and republishes a Twist on
``/cmd_vel_teleop`` at a fixed rate. Movement is "hold to move": while a key is
held, the terminal's auto-repeat keeps the command alive; when released, no key
arrives for ``KEY_TIMEOUT`` seconds and the robot is commanded to stop.

Layouts supported simultaneously: AZERTY (ZQSD), QWERTY (WASD) and arrow keys.
"""

import select
import sys
import termios
import tty

import rclpy
from rclpy.node import Node

from geometry_msgs.msg import Twist

# Default speeds (m/s and rad/s); adjustable at runtime with +/-.
MOVE_SPEED = 0.5
STRAFE_SPEED = 0.4
TURN_SPEED = 1.0

# Publish/poll rate and how long after the last key press we command a stop.
RATE_HZ = 20.0
KEY_TIMEOUT = 0.3

# Min/max bounds and step for runtime speed tuning.
SPEED_MIN = 0.1
SPEED_MAX = 1.5
SPEED_STEP = 0.1

HELP = """
Go2 keyboard teleop  (AZERTY layout + arrows)
---------------------------------------------
  forward    Z / W / Up
  backward   S / Down
  turn left  Q / Left
  turn right D / Right
  strafe L   A
  strafe R   E
  stop       space
  speed +/-  + / -
  quit       x  or  Ctrl-C

Hold a key to keep moving; release to stop automatically.
"""

# Arrow keys arrive as the escape sequences below.
ARROW_UP = '\x1b[A'
ARROW_DOWN = '\x1b[B'
ARROW_RIGHT = '\x1b[C'
ARROW_LEFT = '\x1b[D'


class KeyboardController(Node):

    def __init__(self):
        super().__init__('keyboard_controller')

        self.publisher_ = self.create_publisher(Twist, '/cmd_vel_teleop', 10)

        self.move_speed = MOVE_SPEED
        self.strafe_speed = STRAFE_SPEED
        self.turn_speed = TURN_SPEED

        self._twist = Twist()
        self._time_of_last_key = self.get_clock().now()
        self._should_quit = False

        # Put the terminal in raw mode so we get keys immediately, one at a
        # time, without waiting for Enter. Restored in restore_terminal().
        self._stdin_fd = sys.stdin.fileno()
        self._old_term_settings = termios.tcgetattr(self._stdin_fd)
        tty.setcbreak(self._stdin_fd)

        self.timer = self.create_timer(1.0 / RATE_HZ, self._on_timer)

        print(HELP)
        self.get_logger().info('Keyboard controller started')

    def restore_terminal(self):
        termios.tcsetattr(
            self._stdin_fd, termios.TCSADRAIN, self._old_term_settings)

    def _read_keys(self):
        """Drain all keys currently buffered on stdin (non-blocking).

        Returns a list of single chars and/or arrow escape sequences.
        """
        keys = []
        while select.select([sys.stdin], [], [], 0.0)[0]:
            ch = sys.stdin.read(1)
            if ch == '\x1b':
                # Possible arrow-key sequence: ESC '[' <A/B/C/D>.
                if select.select([sys.stdin], [], [], 0.0)[0]:
                    ch += sys.stdin.read(1)
                if select.select([sys.stdin], [], [], 0.0)[0]:
                    ch += sys.stdin.read(1)
            keys.append(ch)
        return keys

    def _adjust_speed(self, delta):
        self.move_speed = min(SPEED_MAX, max(SPEED_MIN, self.move_speed + delta))
        self.strafe_speed = min(
            SPEED_MAX, max(SPEED_MIN, self.strafe_speed + delta))
        self.turn_speed = min(SPEED_MAX, max(SPEED_MIN, self.turn_speed + delta))
        self.get_logger().info(
            'speed: move=%.1f strafe=%.1f turn=%.1f'
            % (self.move_speed, self.strafe_speed, self.turn_speed))

    def _apply_key(self, key, twist):
        """Update *twist* in place for a single key. Returns True if recognized."""
        if key in ('z', 'w', ARROW_UP):
            twist.linear.x += self.move_speed
        elif key in ('s', ARROW_DOWN):
            twist.linear.x -= self.move_speed
        elif key in ('q', ARROW_LEFT):
            twist.angular.z += self.turn_speed
        elif key in ('d', ARROW_RIGHT):
            twist.angular.z -= self.turn_speed
        elif key == 'a':
            twist.linear.y += self.strafe_speed
        elif key == 'e':
            twist.linear.y -= self.strafe_speed
        elif key in ('+', '='):
            self._adjust_speed(SPEED_STEP)
        elif key in ('-', '_'):
            self._adjust_speed(-SPEED_STEP)
        elif key == ' ':
            pass  # explicit stop: recognized but adds no velocity
        elif key in ('x', '\x03'):  # 'x' or Ctrl-C
            self._should_quit = True
        else:
            return False
        return True

    def _on_timer(self):
        keys = self._read_keys()

        if keys:
            twist = Twist()
            recognized = False
            for key in keys:
                if self._apply_key(key, twist):
                    recognized = True
            if self._should_quit:
                raise KeyboardInterrupt
            if recognized:
                self._twist = twist
                self._time_of_last_key = self.get_clock().now()

        # Auto-stop if no key has been pressed recently (key released).
        elapsed = (self.get_clock().now() - self._time_of_last_key).nanoseconds / 1e9
        if elapsed > KEY_TIMEOUT:
            self._twist = Twist()

        self.publisher_.publish(self._twist)


def main(args=None):
    rclpy.init(args=args)
    controller = KeyboardController()
    try:
        rclpy.spin(controller)
    except KeyboardInterrupt:
        pass
    finally:
        # Best-effort: command a final stop before shutting down.
        try:
            controller.publisher_.publish(Twist())
        except Exception:
            pass
        controller.restore_terminal()
        controller.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
