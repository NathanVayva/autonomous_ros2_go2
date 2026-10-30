# Copyright (c) 2026, Nathan
# SPDX-License-Identifier: BSD-3-Clause
#
# ============================================================================
#  adapter/registry.py  —  L'ANNUAIRE / LE POINT DE SWITCH
# ============================================================================
#  Rôle : mapper un NOM -> un adaptateur configuré (model_id local + options).
#  C'est LE point unique où l'on choisit le modèle. Chaque entrée = un candidat
#  de benchmark. Ajouter un modèle = ajouter UNE ligne, rien d'autre ne bouge.
#
#  IMPORTS PARESSEUX : on n'importe PAS torch/transformers ni les adaptateurs
#  ici, en haut du module. Chaque backend est importé UNIQUEMENT quand on le
#  construit (dans _load). Conséquences voulues :
#    - importer ce module ne coûte rien et ne peut pas planter,
#    - le backend "mock" tourne même si l'adaptateur Qwen réel est en chantier,
#    - on ne charge torch que si on choisit vraiment un vrai modèle.
#
import importlib


def _load(module: str, cls: str, *args, **kwargs):
    """Importe adapter/<module>.py et instancie <cls>(*args, **kwargs)."""
    mod = importlib.import_module(f".{module}", __package__)
    return getattr(mod, cls)(*args, **kwargs)


# nom -> fonction qui construit (et CHARGE) l'adaptateur, paramétrée par le
# device ("cuda" | "cpu"). Chaque adaptateur remplit les DEUX ports -> mode
# mono-modèle. Le chargement se fait à l'appel.
#
# device : passé au constructeur de l'adaptateur (à lui de le poser dans
#          from_pretrained). La quantif 4-bit (bitsandbytes) est CUDA-only : on
#          ne l'active donc QUE sur "cuda" (sur "cpu" -> chargement pleine
#          précision, cf. bf16).
BACKENDS = {
    "mock":         lambda dev, mode: _load("mock_adapter", "MockAdapter"),
    "qwen3_vl_7b":  lambda dev, mode: _load("qwen3_adapter", "Qwen3Adapter", "Qwen/Qwen3-VL-7B-Instruct", device=dev, nav_mode=mode),
    "qwen3_vl_4b":  lambda dev, mode: _load("qwen3_adapter", "Qwen3Adapter", "Qwen/Qwen3-VL-4B-Instruct", device=dev, load_in_4bit=(dev == "cuda"), nav_mode=mode),
    "qwen3_vl_2b":  lambda dev, mode: _load("qwen3_adapter", "Qwen3Adapter", "Qwen/Qwen3-VL-2B-Instruct", device=dev, load_in_4bit=(dev == "cuda"), nav_mode=mode),
    "robobrain2_7b": lambda dev, mode: _load("robotbrain2_adapter", "RoboBrain2Adapter", "BAAI/RoboBrain2.0-7B"),
}


def build_backend(name: str, device: str = "cuda", nav_mode: str = "heading"):
    """Retourne UN adaptateur (qui remplit les deux ports). CHARGE le modèle.

    device : "cuda" (GPU, quantif 4-bit possible) ou "cpu" (pleine précision).
    nav_mode : comment le but est produit -> "heading" (cap+distance, sans calibration)
               | "pixel" (pixel caméra -> monde, placeholder) | "map_som" (numéro de POI
               sur carte annotée -> le node fournit carte+table via obs.extra).
    """
    if name not in BACKENDS:
        raise ValueError(f"backend inconnu '{name}'. Choix: {list(BACKENDS)}")
    return BACKENDS[name](device, nav_mode)
#
#  (Vérifie les model_id exacts sur HuggingFace.)
# ============================================================================
