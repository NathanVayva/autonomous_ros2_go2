# Copyright (c) 2026, Nathan
# SPDX-License-Identifier: BSD-3-Clause
#
# ============================================================================
#  application/reasoning_service.py  —  LE CHEF D'ORCHESTRE
# ============================================================================
#  Rôle : enchaîner "perçois" puis "décide". Ne connaît QUE les ports (pas Qwen
#  ni RoboBrain). Court et stable : toute la complexité est chez les adaptateurs.
#  En mode mono-modèle, vlm et reasoner sont le MÊME objet -> il ne voit pas la
#  différence (il ne parle qu'aux interfaces).
#  Couche APPLICATION.
#
from ..domain.ports import IVisionLanguageModel, IEmbodiedReasoner
from ..domain.types import Observation, Decision

class ReasoningService:
    def __init__(self, vlm: IVisionLanguageModel, reasoner: IEmbodiedReasoner,
                 reasoning_mode: str = "fused"):
        # stocke vlm et reasoner (peuvent être le même objet)
        #   reasoning_mode :
        #     "fused"   (A) -> UNE génération : plan() décide directement de l'image.
        #     "chained" (B) -> DEUX générations : describe() d'abord, puis plan()
        #                      décide EN TENANT COMPTE de la description (injectée
        #                      dans l'instruction -> aucune modif des adaptateurs).
        self.vlm = vlm
        self.reasoner = reasoner
        self.reasoning_mode = reasoning_mode

    def step(self, obs: Observation, instruction: str) -> Decision:
        if self.reasoning_mode == "chained":
            # B : perçois -> décris -> décide à partir de la description
            seen = self.vlm.describe(
                obs,
                f'The instruction is: "{instruction}". '
                f"Briefly describe what is relevant.")
            # la description passe par l'instruction -> plan() la voit dans son prompt
            decision = self.reasoner.plan(
                obs, f"{instruction}\n\nScene description: {seen}")
            decision.rationale = f"[seen] {seen}\n[decided] {decision.rationale}"
        else:
            # A "fused" (défaut) : plan() décide en une seule génération
            seen = None
            decision = self.reasoner.plan(obs, instruction)

        print(f"*************************************************")
        print(f"OBSERVATION : {obs.robot_xy_yaw}")
        print(f"ReasoningService.step() : instruction = '{instruction}'")
        print(f"ReasoningService.step() : seen = '{seen}'")
        print(f"DECISION : action = '{decision.action}', goal_xy = {decision.goal_xy}, rationale = '{decision.rationale}'")
        print(f"*************************************************")

        
        return decision
# ============================================================================
