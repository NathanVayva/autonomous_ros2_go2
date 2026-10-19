# Copyright (c) 2026, Nathan
# SPDX-License-Identifier: BSD-3-Clause
#
# ============================================================================
#  application/spatial_memory.py  —  MÉMOIRE SPATIALE
# ============================================================================
#  Rôle : consigner ce que le modèle trouve intéressant (note) avec la position
#  estimée du robot (x, y, yaw odom). Persistant (JSONL, une entrée par ligne),
#  rechargé au démarrage. Dédup par POSITION : on ne re-note pas un lieu déjà
#  mémorisé à moins de dedup_dist mètres.
#  Couche APPLICATION (pas de ROS ici).
#
import json
import math
import os
import time


class SpatialMemory:
    def __init__(self, path: str, dedup_dist: float = 0.5):
        self.path = path
        self.dedup_dist = dedup_dist
        self.entries: list[dict] = []   # {x, y, yaw, note, stamp}
        self._load()

    def _load(self) -> None:
        if not self.path or not os.path.exists(self.path):
            return
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    self.entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass  # ligne corrompue -> on ignore

    def recall(self, x: float, y: float, yaw: float, frame: str,
               mission: str = "", limit: int = 20) -> list[str]:
        """Amers du MÊME repère, en "label: distance, cap RELATIF à (x,y,yaw)".

        Réinjecté dans le prompt -> le modèle a une mémoire GLOBALE et actionnable
        (il peut retourner vers un amer). Cap (heading_deg) : 0 = devant, + = gauche,
        - = droite (même convention que la voie B). Tri pertinence-mission puis
        proximité, coupé à `limit` (limite la taille du prompt sans amputer la mémoire).
        """
        # ponytail: scan linéaire + match par sous-chaîne -> OK à cette échelle ;
        # embeddings/index si la mémoire devient énorme.
        words = [w for w in mission.lower().split() if len(w) >= 4]
        items = []
        for e in self.entries:
            if e.get("frame", "odom") != frame:
                continue
            dx, dy = e["x"] - x, e["y"] - y
            dist = math.hypot(dx, dy)
            bearing = math.degrees(math.atan2(dy, dx) - yaw)
            bearing = (bearing + 180.0) % 360.0 - 180.0   # -> [-180, 180]
            relevant = any(w in e["note"].lower() for w in words)
            items.append((0 if relevant else 1, dist, e["note"], bearing))
        items.sort(key=lambda t: (t[0], t[1]))   # pertinents d'abord, puis les plus proches
        return [f"{note}: {dist:.1f}m at heading {int(bearing)}"
                for _, dist, note, bearing in items[:limit]]

    def remember(self, x: float, y: float, yaw: float, note: str,
                 frame: str = "odom") -> bool:
        """Ajoute (x, y, yaw, note, frame) si non vide et hors zone déjà mémorisée.

        frame : "map" (persistant entre sessions) ou "odom" (relatif à ce boot).
        La dédup ne compare QUE les entrées du même repère (coordonnées d'un
        repère à l'autre incomparables). Retourne True si enregistré.
        """
        note = (note or "").strip()
        if not note:
            return False
        # ponytail: dédup par position seule -> une note différente près d'un
        # lieu déjà noté est ignorée. Clé sur (pos, note) si ça devient gênant.
        for e in self.entries:
            if e.get("frame", "odom") == frame and \
                    math.hypot(x - e["x"], y - e["y"]) < self.dedup_dist:
                return False
        entry = {"x": round(x, 3), "y": round(y, 3), "yaw": round(yaw, 3),
                 "note": note, "frame": frame, "stamp": time.time()}
        self.entries.append(entry)
        if self.path:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return True
# ============================================================================
