# Copyright (c) 2026, Nathan
# SPDX-License-Identifier: BSD-3-Clause
#
# ============================================================================
#  domain/types.py  —  LE VOCABULAIRE PARTAGÉ
# ============================================================================
#  Rôle : des "boîtes de données" pures, sans ROS ni ML. Tout le projet parle
#  ce vocabulaire ; les adaptateurs traduisent entre lui et le monde extérieur.
#  Couche DOMAINE = ne dépend de RIEN (c'est le cœur).
#

import numpy as np
from dataclasses import dataclass, field


@dataclass
class Observation:  # une perception à l'instant t
    image_bgr: np.ndarray  # image OpenCV (BGR)
    stamp: float  # secondes
    robot_xy_yaw: tuple[float, float, float] = (0.0, 0.0, 0.0)  # pose odom
    extra: dict = field(default_factory=dict)


@dataclass
class Grounding:  # où est un objet dans l'image
    label: str
    point_px: tuple[int, int]  # centre (u, v) en pixels
    bbox_px: tuple[int, int, int, int] | None = None  # x1,y1,x2,y2
    confidence: float = 0.0


@dataclass
class Decision:  # sortie du raisonneur
    action: str  # "goto"|"stop"|"explore"
    goal_xy: tuple[float, float] | None = None  # waypoint en mètres (odom)
    rationale: str = ""  # explication (log/debug)
    note: str = ""  # ce que le modèle trouve digne d'être mémorisé (vide sinon)
    landmark: bool = False  # le modèle juge cette note "lieu réutilisable" -> mémorisée si True
