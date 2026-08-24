#!/usr/bin/env python3
"""Annote une carte (.pgm + .yaml) avec des points d'intérêt numérotés, pour
TESTER la navigation Set-of-Mark à la main (POI arbitraires, pas de détection).

- tu poses les POI en PIXELS (à l'œil sur l'image), voir la liste POIS ci-dessous ;
- le script dessine ①②③… + écrit la table JSON numéro -> (x,y) monde (repère map).

Le modèle reçoit l'image annotée + la table, renvoie un NUMÉRO, tu publies xy.

Usage: python3 annotate_map.py [carte.yaml]   (défaut: la carte du labo)
Sort: <carte>_annotated.png  et  <carte>_pois.json
"""
import json, sys, os, yaml, cv2

# (u, v, label) en PIXELS de l'image .pgm. Édite librement pour tes tests.
# u = colonne (0 = gauche), v = ligne (0 = HAUT). Ouvre le png de sortie pour ajuster.
# label = nom lisible donné au modèle (facultatif, "" si tu ne veux qu'un point).
POIS = {
    1: (110, 180, "corridor junction"),
    2: (80, 260, "far corner"),
    3: (220, 250, "right room"),
}


def pixel_to_world(u, v, res, ox, oy, height):
    # ligne image 0 = haut -> on inverse v (grille map: y vers le haut). Cellule centrée: +0.5
    return (ox + (u + 0.5) * res, oy + (height - 1 - v + 0.5) * res)


def main(yaml_path):
    meta = yaml.safe_load(open(yaml_path))
    res = meta["resolution"]
    ox, oy = meta["origin"][0], meta["origin"][1]
    pgm = os.path.join(os.path.dirname(yaml_path), meta["image"])
    img = cv2.cvtColor(cv2.imread(pgm, cv2.IMREAD_GRAYSCALE), cv2.COLOR_GRAY2BGR)
    h = img.shape[0]

    table = {}
    for n, (u, v, *label) in POIS.items():
        wx, wy = pixel_to_world(u, v, res, ox, oy, h)
        table[str(n)] = {"xy": [round(wx, 2), round(wy, 2)], "label": label[0] if label else ""}
        cv2.circle(img, (u, v), 8, (0, 0, 255), -1)
        cv2.putText(img, str(n), (u + 10, v + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

    base = os.path.splitext(yaml_path)[0]
    cv2.imwrite(base + "_annotated.png", img)
    json.dump(table, open(base + "_pois.json", "w"), indent=2)
    print(f"écrit: {base}_annotated.png\nécrit: {base}_pois.json")
    print(json.dumps(table, indent=2))


def _check():
    # coin bas-gauche (u=0, v=H-1) doit retomber ~sur l'origine de la carte.
    wx, wy = pixel_to_world(0, 347, 0.05, -10.3, -5.61, 348)
    assert abs(wx - -10.275) < 1e-6 and abs(wy - -5.585) < 1e-6, (wx, wy)


if __name__ == "__main__":
    _check()
    default = os.path.join(os.path.dirname(__file__),
                           "../../map/lab.yaml")
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.abspath(default))
