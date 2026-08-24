#!/usr/bin/env python3
"""Générateur DÉTERMINISTE de landmarks à partir d'une carte (.pgm + .yaml).

Méthode : squelette de l'espace libre (medial axis / thinning Zhang-Suen) -> graphe.
  - pixel à >=3 voisins squelette  -> INTERSECTION
  - pixel à  1 voisin              -> CUL-DE-SAC / fond de pièce
  - le reste du squelette          -> couloirs (échantillonnés à intervalle régulier)
Sort les mêmes fichiers que annotate_map.py : <carte>_landmarks.json (format POI, à
pointer via poi_path pour la voie C) + <carte>_landmarks.png (aperçu à l'œil).

Déps : opencv-contrib (cv2.ximgproc) + scipy. Offline, comme annotate_map.py.
Usage : python3 map_landmarks.py [carte.yaml]
"""
import json, os, sys, math, yaml, cv2
import numpy as np
from scipy.ndimage import label, center_of_mass, distance_transform_edt

# ---- boutons de calibration (la carte réelle est bruitée -> à ajuster) ----
FREE_VAL      = 250     # gris > FREE_VAL = libre (carte trinaire : 254 libre, 205 inconnu, 0 occupé)
SMOOTH_PX     = 5       # ouverture morpho : lisse les aspérités de murs qui créent des barbules
MIN_BRANCH_M  = 1.0   # élague les barbules du squelette plus courtes que ça (spurs)
MIN_SPACING_M = 3.0     # distance mini entre 2 landmarks (couvre sans surcharger ; monte-le si trop dense)
MIN_CLEARANCE_M = 0.4  # rejette tout landmark à moins de ça d'un mur (~1/2 empreinte + marge)
MAX_LANDMARKS = 10      # cap de sécurité (couverture globale ; le SoM en montrera un sous-ensemble local)

# 8 voisins ORDONNÉS autour de l'anneau (horaire : N, NE, E, SE, S, SW, W, NW).
_RING = [(-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1)]


def _branches(skel):
    """Nombre de branches par pixel = transitions 0/1 autour de l'anneau / 2.

    endpoint=1, couloir=2, intersection>=3. (Compter les PIXELS voisins surestime :
    un coude a 3 voisins sans être un carrefour ; les transitions, non.)
    """
    s = skel.astype(np.int8)
    ring = [np.roll(np.roll(s, -dr, 0), -dc, 1) for dr, dc in _RING]  # voisin (dr,dc) -> shift -dr,-dc
    trans = sum((ring[i] != ring[(i + 1) % 8]).astype(np.int16) for i in range(8))
    return (trans // 2) * skel


def _centroids(mask):
    lab, n = label(mask, structure=np.ones((3, 3)))
    return center_of_mass(mask, lab, range(1, n + 1)) if n else []   # [(row, col), ...]


def landmarks_from_map(yaml_path):
    meta = yaml.safe_load(open(yaml_path))
    res, (ox, oy) = meta["resolution"], meta["origin"][:2]
    gray = cv2.imread(os.path.join(os.path.dirname(yaml_path), meta["image"]),
                      cv2.IMREAD_GRAYSCALE)
    h = gray.shape[0]
    p2w = lambda c, r: (ox + (c + 0.5) * res, oy + (h - 1 - r + 0.5) * res)  # pixel(col,row)->monde

    # espace libre despecklé -> squelette 1px
    free = np.where(gray > FREE_VAL, 255, 0).astype(np.uint8)
    free = cv2.morphologyEx(free, cv2.MORPH_OPEN, np.ones((SMOOTH_PX, SMOOTH_PX), np.uint8))
    skel = cv2.ximgproc.thinning(free) > 0

    # élague les barbules : retire itérativement les pixels de degré 1 (endpoints)
    for _ in range(round(MIN_BRANCH_M / res)):
        skel = skel & ~(skel & (_branches(skel) == 1))

    # distance de chaque point libre au mur le plus proche (m) -> garde-dégagement.
    # Rejette les landmarks collés aux murs (passages étroits, ou centroïde de
    # carrefour tombé dans un mur). `clear(r,c)` = assez loin d'un mur ?
    dist_m = distance_transform_edt(free > 0) * res
    clear = lambda r, c: dist_m[int(round(r)), int(round(c))] >= MIN_CLEARANCE_M

    br = _branches(skel)
    # priorité : intersections, puis culs-de-sac, puis couloirs (ordre = priorité au thinning)
    cand = ([(p2w(c, r), "intersection") for r, c in _centroids(skel & (br >= 3)) if clear(r, c)] +
            [(p2w(c, r), "dead-end")     for r, c in _centroids(skel & (br == 1)) if clear(r, c)] +
            [(p2w(x, y), "corridor")     for y, x in zip(*np.where(skel)) if clear(y, x)])

    # thinning spatial glouton : garde le 1er, rejette tout ce qui est trop proche
    kept = []
    for (x, y), kind in cand:
        if all(math.hypot(x - qx, y - qy) >= MIN_SPACING_M for (qx, qy), _ in kept):
            kept.append(((x, y), kind))
    kept = kept[:MAX_LANDMARKS]

    table = {str(i): {"xy": [round(x, 2), round(y, 2)], "label": kind}
             for i, ((x, y), kind) in enumerate(kept, 1)}
    return table, meta, gray, skel


def _draw(gray, skel, table, meta):
    res, (ox, oy) = meta["resolution"], meta["origin"][:2]
    h = gray.shape[0]
    img = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    img[skel] = (0, 200, 200)                                   # squelette en jaune pâle
    color = {"intersection": (0, 0, 255), "dead-end": (255, 0, 0), "corridor": (0, 180, 0)}
    for n, poi in table.items():
        u = int((poi["xy"][0] - ox) / res - 0.5)
        v = int((h - 1) - ((poi["xy"][1] - oy) / res - 0.5))
        c = color[poi["label"]]
        cv2.circle(img, (u, v), 5, c, -1)
        cv2.putText(img, n, (u + 7, v + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, c, 1)
    return img


def _check():
    # squelette en '+' : centre = intersection (4 voisins), 4 pointes = endpoints.
    skel = np.zeros((7, 7), bool)
    skel[3, 1:6] = True
    skel[1:6, 3] = True
    br = _branches(skel)
    assert br[3, 3] == 4, br[3, 3]                 # centre = 4 branches
    assert (skel & (br == 1)).sum() == 4           # 4 pointes = endpoints


if __name__ == "__main__":
    _check()
    yaml_path = os.path.abspath(sys.argv[1] if len(sys.argv) > 1
                                else os.path.join(os.path.dirname(__file__), "../../map/lab.yaml"))
    table, meta, gray, skel = landmarks_from_map(yaml_path)
    base = os.path.splitext(yaml_path)[0]
    json.dump(table, open(base + "_landmarks.json", "w"), indent=2)
    cv2.imwrite(base + "_landmarks.png", _draw(gray, skel, table, meta))
    kinds = {}
    for p in table.values():
        kinds[p["label"]] = kinds.get(p["label"], 0) + 1
    print(f"écrit: {base}_landmarks.json  ({len(table)} landmarks {kinds})")
    print(f"écrit: {base}_landmarks.png")
