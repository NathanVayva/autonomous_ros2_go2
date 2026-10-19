# Copyright (c) 2026, Nathan
# SPDX-License-Identifier: BSD-3-Clause
#
# ============================================================================
#  adapter/som_map.py  —  RENDU "Set-of-Mark" de la carte  (voie C)
# ============================================================================
#  Détail concret (cv2) isolé ici : charge la carte .pgm+.yaml, convertit
#  monde <-> pixel, et dessine l'image montrée au modèle (flèche robot + POI
#  numérotés). Le node fournit la pose ; l'adaptateur ne voit qu'une image.
#
import os, yaml, cv2, math

# Convention map_server : image ligne 0 = HAUT ; carte y vers le HAUT -> on
# inverse v. Cellule centrée -> +0.5.


def load_map(yaml_path):
    """-> (base_bgr, meta) avec meta = {resolution, ox, oy, height, width}."""
    meta_yaml = yaml.safe_load(open(yaml_path))
    pgm = os.path.join(os.path.dirname(yaml_path), meta_yaml["image"])
    gray = cv2.imread(pgm, cv2.IMREAD_GRAYSCALE)
    base = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    meta = {"resolution": meta_yaml["resolution"],
            "ox": meta_yaml["origin"][0], "oy": meta_yaml["origin"][1],
            "height": gray.shape[0], "width": gray.shape[1]}
    return base, meta


def world_to_pixel(wx, wy, meta):
    res, ox, oy, h = meta["resolution"], meta["ox"], meta["oy"], meta["height"]
    u = int((wx - ox) / res - 0.5)
    v = int((h - 1) - ((wy - oy) / res - 0.5))
    return u, v


def render(base_bgr, meta, robot_xy_yaw, pois, visited=()):
    """Image annotée : flèche robot (repère map) + POI numérotés {num: {xy,label}}.

    visited = POI récemment ciblés -> dessinés en VERT (dispo = rouge). Pas de gris :
    l'espace inconnu de la carte est déjà gris, ça se confondrait.
    """
    img = base_bgr.copy()
    x, y, yaw = robot_xy_yaw
    u0, v0 = world_to_pixel(x, y, meta)
    tip = world_to_pixel(x + 0.5 * math.cos(yaw), y + 0.5 * math.sin(yaw), meta)
    cv2.arrowedLine(img, (u0, v0), tip, (255, 0, 0), 2, tipLength=0.4)  # bleu = robot
    for n, poi in pois.items():
        u, v = world_to_pixel(poi["xy"][0], poi["xy"][1], meta)
        color = (0, 160, 0) if n in visited else (0, 0, 255)           # BGR : vert visité / rouge dispo
        cv2.circle(img, (u, v), 6, color, -1)
        cv2.putText(img, str(n), (u + 8, v + 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    return img


def _check():
    # cellule-origine (bas-gauche) -> coin bas-gauche image ; +1 cellule Y -> 1 ligne plus HAUT.
    meta = {"resolution": 0.05, "ox": -10.3, "oy": -5.61, "height": 348, "width": 300}
    assert world_to_pixel(-10.3 + 0.025, -5.61 + 0.025, meta) == (0, 347)
    assert world_to_pixel(-10.3 + 0.025, -5.61 + 0.075, meta) == (0, 346)


if __name__ == "__main__":
    _check()
    print("som_map ok")
