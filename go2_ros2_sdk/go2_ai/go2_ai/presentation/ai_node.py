# Copyright (c) 2026, Nathan
# SPDX-License-Identifier: BSD-3-Clause
#
# ============================================================================
#  presentation/ai_node.py  —  LA PORTE D'ENTRÉE ROS2  (tuto §9)
# ============================================================================
#  Rôle : relier ROS et le cœur. Écoute la caméra/odom, fabrique une Observation,
#  appelle le service DANS UN THREAD (ne jamais bloquer l'exécuteur ROS), publie
#  /goal_pose et /ai/rationale. Couche PRESENTATION (si tu changes ROS, seul ce
#  fichier bouge).
#
#  Deux pièges gérés :
#   - chargement du modèle = LENT -> fait UNE fois au démarrage (build_service).
#   - inférence = 0.3–3 s -> thread worker + lock _busy (une seule à la fois).
#
#  imports probables :
import json, threading, time, traceback, rclpy
from collections import deque
from rclpy.node import Node
from rclpy.time import Time
from rclpy.qos import qos_profile_sensor_data  # BEST_EFFORT : profil des capteurs
from rclpy.qos import QoSProfile, QoSDurabilityPolicy
from tf2_ros import Buffer, TransformListener, TransformException
from sensor_msgs.msg import Image
from nav_msgs.msg import Odometry, OccupancyGrid
from geometry_msgs.msg import PoseStamped
from std_msgs.msg import String
from cv_bridge import CvBridge
from ..domain.types import Observation
from ..application.reasoning_service import ReasoningService
from ..application.spatial_memory import SpatialMemory
from ..adapter.registry import build_backend        # NB: 'adapter' (singulier)
from ..adapter import som_map                        # voie C : rendu carte annotée
import math


def build_service(node: Node) -> ReasoningService:
    # lit les paramètres 'backend' et 'device', build_backend(...) CHARGE le
    # modèle, renvoie ReasoningService(vlm=adapter, reasoner=adapter) # mono-modèle
    #   device="cuda" -> GPU (quantif 4-bit possible) ; "cpu" -> pleine précision
    #   (utile si le GPU est déjà pris par Isaac Sim).
    #   nav_mode : "heading" (cap+distance) | "pixel" (pixel->monde) | "map_som" (POI carte)
    backend = node.declare_parameter("backend", "qwen3_vl_4b").value
    device = node.declare_parameter("device", "cuda").value
    nav_mode = node.declare_parameter("nav_mode", "heading").value
    if nav_mode not in ("heading", "pixel", "map_som"):
        node.get_logger().warn(f"nav_mode '{nav_mode}' inconnu -> 'heading'")
        nav_mode = "heading"
    reasoning_mode = node.declare_parameter("reasoning_mode", "fused").value
    if reasoning_mode not in ("fused", "chained"):
        node.get_logger().warn(f"reasoning_mode '{reasoning_mode}' inconnu -> 'fused'")
        reasoning_mode = "fused"
    node.get_logger().info(
        f"chargement du backend '{backend}' sur '{device}', navigation '{nav_mode}', "
        f"reasoning '{reasoning_mode}' (peut prendre du temps)...")
    adapter = build_backend(backend, device, nav_mode) # <-- CHARGE les poids
    node.get_logger().info("modèle chargé.")
    return ReasoningService(vlm=adapter, reasoner=adapter, reasoning_mode=reasoning_mode)

class AINode(Node):
     def __init__(self):
         # super().__init__("go2_ai")  ; self.service = build_service(self)
         # déclare params : image_topic, odom_topic, instruction, period_s
         # subs Image/Odometry ; pubs PoseStamped 'goal_pose', String 'ai/rationale'
         # self._busy = threading.Lock() ; self.create_timer(period_s, self._tick)
        super().__init__("go2_ai")
        self.bridge = CvBridge()
        self.service = build_service(self) # bloque au démarrage le temps du chargement
        image_topic = self.declare_parameter("image_topic", "camera/image_raw").value
        odom_topic = self.declare_parameter("odom_topic", "odom").value
        self.instruction = self.declare_parameter("instruction", "explore and note interesting places. When a noted place is found and noted, continue exploring.").value
        self.period = self.declare_parameter("period_s", 2.0).value
        # Ne lancer l'inférence QUE si le robot est immobile depuis settle_time_s
        # (image nette). Le mouvement est mesuré par le déplacement entre deux
        # échantillons odom ; seuils à calibrer selon le bruit réel de l'odom.
        self.settle_time = self.declare_parameter("settle_time_s", 1.0).value
        self.motion_pos_tol = self.declare_parameter("motion_pos_tol", 0.03).value  # m / échantillon
        self.motion_yaw_tol = self.declare_parameter("motion_yaw_tol", 0.05).value  # rad / échantillon
        # dédup goal : on ne republie pas un goal à moins de goal_min_move du dernier
        self.goal_min_move = self.declare_parameter("goal_min_move", 0.3).value  # m
        # mémoire spatiale : note du modèle + position, persistée en JSONL
        memory_path = self.declare_parameter(
            "memory_path", "/ros2_ws/src/go2_ai/spatial_memory.jsonl").value
        memory_dedup_dist = self.declare_parameter("memory_dedup_dist", 0.5).value  # m
        # RAPPEL : nb max d'amers réinjectés dans le prompt (les plus pertinents/proches)
        self.memory_recall_limit = self.declare_parameter("memory_recall_limit", 20).value
        self.memory = SpatialMemory(memory_path, memory_dedup_dist)
        # nav_mode déjà déclaré/validé dans build_service (au-dessus). Voie C
        # (map_som) : carte annotée (flèche robot + POI numérotés), le modèle choisit
        # un numéro. POI arbitraires en JSON pour tester (cf. tools/annotate_map.py).
        self.nav_mode = self.get_parameter("nav_mode").value
        if self.nav_mode == "map_som":
            map_yaml = self.declare_parameter("map_yaml", "/ros2_ws/src/map/lab.yaml").value
            poi_path = self.declare_parameter("poi_path", "/ros2_ws/src/map/lab_pois.json").value
            self._som_base, self._som_meta = som_map.load_map(map_yaml)
            self._pois = json.load(open(poi_path))
            # mémoire ÉPISODIQUE : N derniers POI ciblés (fenêtre glissante). Sert à
            # (a) griser-vert les visités sur la carte, (b) tracer "recently visited"
            # dans le prompt -> casse l'oscillation 2<->1. Sort de la fenêtre = redevient rouge.
            self._recent = deque(maxlen=self.declare_parameter("recent_goals_window", 5).value)
            # "visité" = robot ARRÊTÉ (porte d'immobilité) à < visit_radius d'un POI,
            # PAS "ciblé". Rayon un peu > xy_goal_tolerance Nav2 (~0.3) pour attraper l'arrêt.
            self.visit_radius = self.declare_parameter("visit_radius", 0.6).value  # m
            # rendu live : on republie l'image EXACTE envoyée au modèle -> à voir dans
            # rqt_image_view / RViz (Image) / Foxglove sur le topic 'ai/som_map'.
            self.som_pub = self.create_publisher(Image, "ai/som_map", 1)
            self.get_logger().info(f"SoM: carte '{map_yaml}', {len(self._pois)} POI '{poi_path}'")
        # TF pour lire la pose en repère 'map' (persistant) si une carte est
        # chargée (localisation) ; sinon on retombe sur odom (relatif au boot).
        self._tf_buffer = Buffer()
        self._tf_listener = TransformListener(self._tf_buffer, self)
        # Caméra = données capteur -> BEST_EFFORT, sinon QoS incompatible avec le
        # publisher (réel comme sim) et "No messages will be received".
        self.create_subscription(Image, image_topic, self._on_image, qos_profile_sensor_data)
        self.create_subscription(Odometry, odom_topic, self._on_odom, 10)
        # costmap local Nav2 (repère odom = celui du goal) : sert à refuser un goal
        # tombé dans un obstacle. Publié en TRANSIENT_LOCAL (latché) -> QoS assortie.
        costmap_topic = self.declare_parameter("costmap_topic", "/local_costmap/costmap").value
        self.goal_cost_threshold = self.declare_parameter("goal_cost_threshold", 90).value  # 0..100
        self._costmap = None
        self.create_subscription(
            OccupancyGrid, costmap_topic, self._on_costmap,
            QoSProfile(depth=1, durability=QoSDurabilityPolicy.TRANSIENT_LOCAL))
        self.goal_pub = self.create_publisher(PoseStamped, "goal_pose", 1)
        self.rationale_pub = self.create_publisher(String, "ai/rationale", 1)
        self._last_image = None
        self._pose = (0.0, 0.0, 0.0)
        self._prev_pose = None                     # (x, y, yaw) échantillon odom précédent
        self._last_motion_time = time.monotonic()  # démarre "en mouvement" -> attend le settle
        self._last_goal = None                     # (x, y) dernier goal publié (dédup)
        self._busy = threading.Lock()
        self.create_timer(self.period, self._tick)
        self.get_logger().info("go2_ai prêt.")
         
         
     def _on_image(self, msg):         # cv_bridge -> self._last_image (bgr8)
        self._last_image = self.bridge.imgmsg_to_cv2(msg, "bgr8")
        
     def _on_odom(self, msg):         # -> self._pose (x, y, yaw)
        p = msg.pose.pose.position
        quaternions = msg.pose.pose.orientation
        # conversion quaternion -> yaw (Z) : yaw = atan2(2*(w*z + x*y), 1 - 2*(y*y + z*z))
        qw, qx, qy, qz = quaternions.w, quaternions.x, quaternions.y, quaternions.z
        yaw = math.atan2( 2.0 * (qw * qz + qx * qy), 1.0 - 2.0 * (qy * qy + qz * qz))

        self._pose = (p.x, p.y, yaw)

        # détection de mouvement : déplacement depuis l'échantillon précédent
        if self._prev_pose is not None:
            px, py, pyaw = self._prev_pose
            dpos = math.hypot(p.x - px, p.y - py)
            dyaw = abs(math.atan2(math.sin(yaw - pyaw), math.cos(yaw - pyaw)))
            if dpos > self.motion_pos_tol or dyaw > self.motion_yaw_tol:
                self._last_motion_time = time.monotonic()
        self._prev_pose = (p.x, p.y, yaw)
        
     def _map_pose(self):
        # pose (x, y, yaw) en repère 'map' via TF, ou None si indisponible
        # (pas de carte chargée / pas encore localisé).
        try:
            t = self._tf_buffer.lookup_transform("map", "base_link", Time())
        except TransformException:
            return None
        q = t.transform.rotation
        yaw = math.atan2(2.0 * (q.w * q.z + q.x * q.y),
                         1.0 - 2.0 * (q.y * q.y + q.z * q.z))
        return (t.transform.translation.x, t.transform.translation.y, yaw)

     def _on_costmap(self, msg):       # dernier costmap local (OccupancyGrid, repère odom)
        self._costmap = msg

     def _goal_blocked(self, gx, gy):
        # True si (gx, gy) [odom] tombe dans une cellule occupée du costmap local.
        # Fail-open : pas de costmap ou hors fenêtre -> on ne bloque pas.
        cm = self._costmap
        if cm is None:
            return False
        info = cm.info
        col = int((gx - info.origin.position.x) / info.resolution)
        row = int((gy - info.origin.position.y) / info.resolution)
        if not (0 <= col < info.width and 0 <= row < info.height):
            print(f"goal ({gx:.2f}, {gy:.2f}) hors costmap local -> on ne bloque pas", flush=True)
            return False
        return cm.data[row * info.width + col] >= self.goal_cost_threshold

     def _tick(self):                     # si pas _busy.acquire(blocking=False): return
         # sinon lance Thread(self._infer, (obs,), daemon=True)
        #self.get_logger().info(f"last_image = {self._last_image.shape[0]} x {self._last_image.shape[1]} pixels" if self._last_image is not None else "last_image = None")
        if self._last_image is None:
            self.get_logger().warn("aucune image reçue -> on saute ce tick")
            return
        if time.monotonic() - self._last_motion_time < self.settle_time:
            self.get_logger().info("robot en mouvement -> on attend l'immobilité")
            return
        if not self._busy.acquire(blocking=False):
            self.get_logger().warn("inférence déjà en cours -> on saute ce tick")
            return # inférence déjà en cours -> on saute ce tick
        obs = Observation(image_bgr=self._last_image.copy(),
                stamp=self.get_clock().now().nanoseconds / 1e9,
                robot_xy_yaw=self._pose)
       
        threading.Thread(target=self._infer, args=(obs,), daemon=True).start()
        
    
     def _infer(self, obs):               # service.step(...), publie, finally: _busy.release()
        print("infer START", flush=True)
        try:
            # pose courante (map si localisé, sinon odom) : sert au RAPPEL et au STOCKAGE
            mp = self._map_pose()
            (mx, my, myaw), frame = (mp, "map") if mp else (obs.robot_xy_yaw, "odom")
            # voie C : construit la carte annotée (flèche robot + POI) -> obs.extra.
            # Le goal sortira en repère MAP (les POI sont en map) ; besoin d'être localisé.
            if self.nav_mode == "map_som":
                if mp is None:
                    self.get_logger().warn("SoM: pose 'map' indisponible (non localisé) -> skip")
                    return
                # visité : le robot est arrêté ici (porte d'immobilité) -> tout POI à
                # portée devient vert. Dédup consécutif : pas de spam tant qu'on stationne dessus.
                for k, v in self._pois.items():
                    if (math.hypot(v["xy"][0] - mx, v["xy"][1] - my) < self.visit_radius
                            and (not self._recent or self._recent[-1] != k)):
                        self._recent.append(k)
                        self.get_logger().info(f"SoM: POI {k} visité (robot arrêté à portée)")
                obs.extra["pois"] = self._pois
                obs.extra["map_bgr"] = som_map.render(
                    self._som_base, self._som_meta, mp, self._pois, visited=set(self._recent))
                self.som_pub.publish(self.bridge.cv2_to_imgmsg(obs.extra["map_bgr"], "bgr8"))
            # RAPPEL : réinjecte les amers mémorisés (label + distance + cap relatif),
            # triés pertinence-mission puis proximité -> le modèle "se souvient" et
            # peut y retourner (même mécanisme que chained : on enrichit l'instruction).
            instruction = self.instruction
            known = self.memory.recall(mx, my, myaw, frame,
                                       mission=self.instruction, limit=self.memory_recall_limit)
            if known:
                instruction += ("\n\nLandmarks you already recorded "
                                "(label: distance, heading): " + " | ".join(known))
            # mémoire ÉPISODIQUE : trace des derniers POI ciblés (SoM). Fait = liste ;
            # le NUDGE ("évite de repiquer sauf si nécessaire") reste à toi d'écrire ici.
            if self.nav_mode == "map_som" and self._recent:
                trace = ", ".join(f'{n}({self._pois[n].get("label", "?")})' for n in self._recent)
                instruction += f"\n\nRecently visited markers (oldest first): {trace}"
            decision = self.service.step(obs, instruction)
            self.rationale_pub.publish(String(data=decision.rationale))
            # STOCKAGE : seulement si le modèle a flaggé landmark=true (option 1 : filtre
            # de réutilisation). Log EXPLICITE de la raison -> on voit pourquoi ça ne
            # stocke pas (note vide / non-landmark / dédup) au lieu d'un échec muet.
            self.get_logger().info(
                f"note='{decision.note}' landmark={decision.landmark}")
            if not decision.note:
                pass                                       # rien à mémoriser
            elif not decision.landmark:
                self.get_logger().info("  -> non-landmark : pas mémorisée")
            elif self.memory.remember(mx, my, myaw, decision.note, frame):
                self.get_logger().info(f"  -> mémoire[{frame}]: '{decision.note}' @ ({mx:.2f}, {my:.2f})")
            else:
                self.get_logger().info(f"  -> déjà un amer à <{self.memory.dedup_dist}m (dédup) : ignorée")
            # (3) pas de goal si le modèle décide de s'arrêter (sinon rotation sur place)
            if decision.action == "stop" or decision.goal_xy is None:
                return
            gx, gy = float(decision.goal_xy[0]), float(decision.goal_xy[1])
            # voie C : goal + POI sont en repère MAP -> pose courante = pose map,
            # et le costmap local (odom) ne s'applique pas (POI déjà curés).
            if self.nav_mode == "map_som":
                goal_frame, cx, cy = "map", mx, my
            else:
                goal_frame, (cx, cy) = "odom", obs.robot_xy_yaw[:2]
            # (4) goal quasi SUR le robot (distance ~0) -> Nav2 ne pourrait que tourner
            # sur place pour l'orientation -> on saute (cause du "il tourne sans avancer").
            if math.hypot(gx - cx, gy - cy) < self.goal_min_move:
                self.get_logger().info("goal trop proche du robot -> ignoré (pas de rotation sur place)")
                return
            # (5) goal tombé dans un obstacle (costmap local, repère odom) -> ignoré.
            if goal_frame == "odom" and self._goal_blocked(gx, gy):
                self.get_logger().info("goal dans un obstacle -> ignoré")
                return
            # (2) dédup : ne pas republier un goal quasi identique -> Nav2 ne repivote pas
            if self._last_goal is not None:
                lx, ly = self._last_goal
                if math.hypot(gx - lx, gy - ly) < self.goal_min_move:
                    return
            goal = PoseStamped()
            goal.header.frame_id = goal_frame
            goal.header.stamp = self.get_clock().now().to_msg()
            goal.pose.position.x = gx
            goal.pose.position.y = gy
            # (1) orienter le goal vers la direction de marche (pas +X fixe) -> le
            # robot arrive déjà tourné dans le bon sens, plus de rotation "retour à +X".
            yaw_goal = math.atan2(gy - cy, gx - cx)
            goal.pose.orientation.z = math.sin(yaw_goal / 2.0)
            goal.pose.orientation.w = math.cos(yaw_goal / 2.0)
            self.goal_pub.publish(goal)
            self._last_goal = (gx, gy)
        except Exception as e:
            # traceback complète -> pointe la ligne exacte de l'adaptateur qui plante
            self.get_logger().error(f"inférence échouée: {e}\n{traceback.format_exc()}")
        finally:
            self._busy.release()
            print("infer END", flush=True)


def main():
    # rclpy.init(); node = AINode(); rclpy.spin(node); ... shutdown
    rclpy.init()
    node = AINode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
    
    
 #referencé par l'entry point 'ai_node' dans setup.py)
# ============================================================================
