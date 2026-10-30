# Copyright (c) 2026, Nathan
# SPDX-License-Identifier: BSD-3-Clause
#
# ============================================================================
#  adapter/robotbrain2_adapter.py  —  RoboBrain 2.0, EN PROCESS
# ============================================================================
#  Rôle : RoboBrain 2.0 est un VLM HuggingFace (base Qwen2.5-VL) -> il se charge
#  COMME Qwen3Adapter. Le plus simple : HÉRITER, et ne surcharger QUE ce qui
#  diffère (prompts/parsing spécifiques : pointing, affordance, trajectory).
#  Format de référence : carte HF BAAI/RoboBrain2.0-*.
#  Couche ADAPTER = implémente les mêmes deux ports -> substituable à Qwen.
#
from ..domain.types import Decision
from .qwen3_adapter import Qwen3Adapter

class RoboBrain2Adapter(Qwen3Adapter):
    # Hérite du chargement + describe/ground/plan génériques.
    # Surcharge plan() (et/ou ground()) si RoboBrain impose un format dédié :
    def plan(self, obs, instruction) -> Decision: 
        return super().plan(obs, instruction)
    # Stub : le format RoboBrain dédié n'est pas encore intégré -> plan() de Qwen3.


# ============================================================================
