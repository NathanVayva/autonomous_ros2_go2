# Copyright (c) 2026, Nathan
# SPDX-License-Identifier: BSD-3-Clause
#
# ============================================================================
#  adapter/mock_adapter.py  —  BACKEND FACTICE (test du câblage, sim/CI)
# ============================================================================
#  CE N'EST PAS le cœur : aucune IA, aucun modèle, aucun GPU, aucun download.
#  Il remplit les DEUX ports avec des réponses triviales pour exercer tout le
#  node (caméra -> Observation -> service -> goal_pose) en simulation, sans
#  charger de VLM. Sers-t'en pour valider la plomberie, puis bascule
#  backend: qwen3_vl_* quand ton adaptateur réel est prêt.
#  Couche ADAPTER = mêmes contrats que Qwen -> substituable.
#
import math

from ..domain.ports import IVisionLanguageModel, IEmbodiedReasoner
from ..domain.types import Observation, Grounding, Decision


class MockAdapter(IVisionLanguageModel, IEmbodiedReasoner):
    """Adaptateur bouchon : réponses déterministes, latence ~0."""

    def __init__(self, *args, **kwargs):
        # Accepte n'importe quels args (model_id, load_in_4bit, ...) pour être
        # interchangeable avec les vrais adaptateurs, mais les ignore.
        self.last_latency_ms = 0.0

    # --- port perception ---
    def describe(self, obs: Observation, question: str) -> str:
        h, w = obs.image_bgr.shape[:2]
        return f"[mock] image {w}x{h}, question='{question}'"

    def ground(self, obs: Observation, target: str) -> Grounding | None:
        # Prétend trouver la cible au centre de l'image.
        h, w = obs.image_bgr.shape[:2]
        return Grounding(label=target, point_px=(w // 2, h // 2), confidence=0.5)

    # --- port raisonnement ---
    def plan(self, obs: Observation, instruction: str) -> Decision:
        # Renvoie un but 1 m DEVANT le robot (repère odom) : pas d'IA, juste de
        # quoi voir goal_pose bouger et suivre l'odométrie dans RViz.
        x, y, yaw = obs.robot_xy_yaw
        goal = (x + math.cos(yaw), y + math.sin(yaw))
        return Decision(
            action="goto",
            goal_xy=goal,
            
            rationale=f"[mock] instruction='{instruction}' -> avance 1 m",
        )
# ============================================================================
