# Copyright (c) 2026, Nathan
# SPDX-License-Identifier: BSD-3-Clause
#
# ============================================================================
#  domain/ports.py  —  LES CONTRATS (les "prises")  (tuto §2)
# ============================================================================
#  Rôle : décrire CE QU'ON SAIT FAIRE, jamais COMMENT. Ce sont des classes
#  abstraites (ABC) : des promesses vides. Un adaptateur les "remplit".
#  Deux rôles distincts = deux ports. Un même modèle peut implémenter les DEUX.
#  Couche DOMAINE = aucune dépendance ML/réseau ici.
#
#  À écrire : 2 classes abstraites.
#
from abc import ABC, abstractmethod
from .types import Observation, Grounding, Decision

class IVisionLanguageModel(ABC):        # rôle : percevoir / ancrer
    @abstractmethod
    def describe(self, obs: Observation, question: str) -> str: ...
    @abstractmethod
    def ground(self, obs: Observation, target: str) -> Grounding | None: ...

class IEmbodiedReasoner(ABC):           # rôle : décider / planifier
    @abstractmethod
    def plan(self, obs: Observation, instruction: str) -> Decision: ...
# ============================================================================
