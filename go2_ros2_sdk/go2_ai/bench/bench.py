# Copyright (c) 2024, RoboVerse community
# SPDX-License-Identifier: BSD-3-Clause
#
# ============================================================================
#  bench/bench.py  —  SWITCHER, MESURER, DÉCIDER  (tuto §11)
# ============================================================================
#  Rôle : charger chaque modèle candidat l'un après l'autre, le passer sur un
#  jeu de test FIXE (cases.yaml), mesurer (latence via last_latency_ms, mémoire
#  via jtop/nvidia-smi en parallèle), écrire un CSV. Hors ROS = mesure propre.
#  Lancement : python3 bench/bench.py > results.csv   (depuis le dossier du package)
#
#  imports probables :
#    import csv, gc, sys, os, yaml, cv2, torch
#    from go2_ai.adapter.registry import build_backend
#    from go2_ai.domain.types import Observation
#
#  CANDIDATES = ["qwen3_vl_2b", "qwen3_vl_4b", "qwen3_vl_7b"]   # à comparer
#
#  def load_cases(path):
#      # lit cases.yaml, charge chaque image (cv2.imread), yield (case, Observation)
#      ...
#
#  def main():
#      # entête CSV : backend, case, task, latency_ms, ok, output
#      # pour chaque name de CANDIDATES :
#      #     ad = build_backend(name)          # CHARGE le modèle
#      #     pour chaque (case, obs) :
#      #         ground(...) -> ok = (trouvé == expect_found) ; écrit ligne
#      #         plan(...)   -> écrit ligne (action)
#      #     del ad ; gc.collect() ; torch.cuda.empty_cache()   # LIBÈRE la mémoire !
#      ...
#
#  if __name__ == "__main__":
#      main()
# ============================================================================
