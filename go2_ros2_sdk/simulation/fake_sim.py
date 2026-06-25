 
class FakeSim:

    def __init__(self):
        self.x = 0.0
        self.y = 0.0
        self.theta = 0.0

    def apply_cmd(self, vx, vy, wz):
        self.vx = vx
        self.vy = vy
        self.wz = wz
