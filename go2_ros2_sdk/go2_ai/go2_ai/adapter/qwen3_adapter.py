# Copyright (c) 2026, Nathan
# SPDX-License-Identifier: BSD-3-Clause
#
# ============================================================================
#  adapter/qwen3_adapter.py  —  ADAPTATEUR LOCAL, EN PROCESS
# ============================================================================
#  Rôle : charger UN VLM en local (aucun serveur, aucune API réseau) et remplir
#  LES DEUX ports (perception + raisonnement). Toute la "saleté" (torch, PIL,
#  génération, parsing JSON) vit ici, isolée du reste.
#  Couche ADAPTER = implémente les contrats du domaine.
#
#  imports probables :
import json, math, time, cv2, torch
from PIL import Image
from transformers import AutoModelForImageTextToText, AutoProcessor
from ..domain.ports import IVisionLanguageModel, IEmbodiedReasoner
from ..domain.types import Observation, Grounding, Decision


# ============================ PROMPTS (édite ici) ===========================
# Prompt SYSTÈME commun aux deux voies : rôle + consigne de format. C'est le
# socle ; on y concatène ensuite l'instruction puis le schéma propre au mode.
SYSTEM_PROMPT = (
    'You are controlling a quadruped robot. '
    'Based on the image, choose the next move. '
    'Respond ONLY with valid JSON, ASCII double quotes, no markdown. '
    # Règle "note" = mémoire spatiale. Chaque bout corrige un défaut observé :
    #   "ONE distinctive landmark, not the whole scene" -> stoppe les 6 notes
    #     redondantes "large room with equipment".
    #   "specific object/feature, e.g. ..." -> exemples concrets (amers relocalisables).
    #   "noun phrase only, no reasoning, no room description" -> plus de justif qui
    #     fuit dans la note ("...so exploring is interesting", "no immediate danger").
    #   'Use "" if ... or already noted nearby' -> ne note PLUS à chaque tick.
    'note: name ONE distinctive landmark to recognize THIS exact spot '
    #'(a specific object or feature, e.g. "forklift", "green basket", "person at desk"). '
    'Max 5 words, a noun phrase only: no reasoning, no room description. '
    'Use "" if nothing distinctive here, or if you already noted a nearby spot. '
    # landmark = FILTRE de réutilisation (option 1). Seules les notes flaggées true
    # sont mémorisées -> deviennent des POI plus tard.
    'landmark: true ONLY if this spot is worth navigating back to later '
    '(a destination, not passing clutter); false otherwise. '
    'if landmark is true, note MUST be a non-empty noun phrase'
)
# Schéma + sémantique des champs, spécifiques à chaque voie.
PROMPT_HEADING = (  # voie B : cap + distance (nav_mode="heading")
    '{"action": "goto|stop|explore", "heading_deg": ..., "distance_m": ..., "why": "...", "note": "", "landmark": true/false} '
    'heading_deg: 0 = straight ahead, positive = left, negative = right, '
    'range -180 to 180. distance_m: between 0.5 and 3.0.'
    'if the path ahead is blocked within ~1.5 m, choose a clearer heading or action=stop'
)
PROMPT_PIXEL = (  # voie A : pixel (nav_mode="pixel")
    '{"action": "goto|stop|explore", "point": [u, v], "why": "...", "note": "", "landmark": true/false} '
    'where point is the image pixel of the target, or null.'
)
PROMPT_SOM = (  # voie C : Set-of-Mark sur la carte (nav_mode="map_som")
    '{"goal": <marker number, or 0 to stop>, "why": "...", "note": "", "landmark": true} '
    'The image is a top-down map. The blue arrow is the robot (tip = facing). '
    'Numbered dots are the reachable destinations: RED = available, '
    'GREEN = recently visited. Choose the number that best serves the '
    'instruction, or 0 to stop.'
)
# ============================================================================


class Qwen3Adapter(IVisionLanguageModel, IEmbodiedReasoner):

    def __init__(
        self,
        model_id: str,
        device: str = "cuda",
        dtype: str = "auto",
        load_in_4bit: bool = False,
        nav_mode: str = "heading",
    ):
        # charge processor + model UNE fois (poids en VRAM), puis _warmup()
        #
        # nav_mode : choisit COMMENT le but est produit dans plan()
        #   "heading" (défaut) = CAP + DISTANCE (ce qu'il voit) -> _heading_to_world()
        #                   -> point sur la carte. Aucune calibration.
        #   "pixel"   = le modèle pointe un PIXEL [u,v] -> _pixel_to_world()
        #                   (intrinsèques + plan sol, placeholder à finir).
        #   "map_som" = numéro d'un POI sur la CARTE annotée (le node fournit
        #                   carte + table via obs.extra) -> _plan_som().
        self.model_id = model_id
        self.nav_mode = nav_mode
        kwargs = {"torch_dtype": dtype, "device_map": device}
        if load_in_4bit:
            from transformers import BitsAndBytesConfig

            kwargs["quantization_config"] = BitsAndBytesConfig(load_in_4bit=True)
        self.processor = AutoProcessor.from_pretrained(model_id)
        self.model = AutoModelForImageTextToText.from_pretrained(model_id, **kwargs)
        self.last_latency_ms = 0.0
        self._warmup()

    @torch.inference_mode()
    def _generate(self, image_bgr, prompt: str, max_new_tokens: int = 256) -> str:
        # BGR->RGB->PIL, apply_chat_template, model.generate, decode
        # mesure self.last_latency_ms (pour le benchmark §11)
        image = Image.fromarray(cv2.cvtColor(image_bgr,cv2.COLOR_BGR2RGB))
        messages = [{"role": "user", 
                     "content": [{"type": "image", "image": image},
                                {"type":"text", "text":prompt}]
                    }]
        
        inputs = self.processor.apply_chat_template(
            messages, add_generation_prompt=True, tokenize=True,return_dict=True, return_tensors="pt").to(self.model.device)
        t0 = time.perf_counter()
        out = self.model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)
        self.last_latency_ms = (time.perf_counter() - t0) * 1000.0
        gen = out[:,inputs["input_ids"].shape[1]:]
        out = self.processor.batch_decode(gen,skip_special_tokens=True)[0]
        return out

    def _warmup(self):  # brûle la 1re génération (lente)
        import numpy as np
        try:
            self._generate(np.zeros((64,64,3), dtype="uint8"),"warmup done", max_new_tokens=1)
        except Exception as e:
            print(f"Warmup failed: {e}")

    # --- port perception ---
    def describe(self, obs: Observation, question: str) -> str: 
        return self._generate(obs.image_bgr, question)
    
    
    def ground(self, obs: Observation, target: str) -> Grounding | None:
        prompt = (
            f'Locate "{target}" in the image. Respond ONLY with valid JSON, '
            f'ASCII double quotes, no markdown: '
            f'{{"found": true, "point": [u, v], "bbox": [x1, y1, x2, y2]}} '
            f'in image pixels. If missing: {{"found": false}}.'
        )
        data = self._parse_json(self._generate(obs.image_bgr, prompt))
        # garde : JSON illisible, cible absente, ou 'point' manquant -> None
        if not data or not data.get("found") or not data.get("point"):
            return None
        u, v = data["point"]
        bbox = data.get("bbox")
        return Grounding(
            label=target, point_px=(int(u), int(v)),
            bbox_px=tuple(bbox) if bbox else None,
            confidence=1.0,
        )

    # prompt qui force un JSON {"found", "point":[u,v], "bbox":[...]}

    # --- port raisonnement (MÊME modèle, autre prompt) ---
    def plan(self, obs: Observation, instruction: str) -> Decision:
        # voie C (Set-of-Mark) : le node a mis carte annotée + POI dans obs.extra.
        if self.nav_mode == "map_som":
            return self._plan_som(obs, instruction)
        # système commun + instruction + schéma du mode (voie B cap+distance / voie A pixel)
        schema = PROMPT_HEADING if self.nav_mode == "heading" else PROMPT_PIXEL
        prompt = f'{SYSTEM_PROMPT}\nInstruction: "{instruction}".\n{schema}'

        data = self._parse_json(self._generate(obs.image_bgr, prompt))
        
        print (f"DATA = {data}")
        
        # garde : sans JSON exploitable on ne bouge pas (fail-safe)
        if not data:
            return Decision(action="stop", goal_xy=None,
                            rationale="model did not return valid JSON")

        if self.nav_mode == "pixel":
            point = data.get("point")
            goal_xy = _pixel_to_world(point, obs) if point else None
        else:
            goal_xy = _heading_to_world(
                data.get("heading_deg"), data.get("distance_m"), obs)

        return Decision(action=data.get("action", "stop"), goal_xy=goal_xy,
                        rationale=data.get("why", ""),
                        note=data.get("note", ""),            # mémoire spatiale (rempli via TON prompt)
                        landmark=bool(data.get("landmark", False)))

    # prompt JSON {"action", "point":[u,v], "why"} ; point pixels -> _pixel_to_world

    def _plan_som(self, obs: Observation, instruction: str) -> Decision:
        # voie C : montre la CARTE annotée, le modèle renvoie un NUMÉRO de POI,
        # on le résout en (x,y) map via la table fournie par le node.
        pois = obs.extra["pois"]           # {"1": {"xy": [x, y], "label": "..."}, ...}
        table = ", ".join(f'{k}={v.get("label", "?")}' for k, v in pois.items())
        prompt = (f'{SYSTEM_PROMPT}\nInstruction: "{instruction}".\n'
                  f'Markers: {table}\n{PROMPT_SOM}')
        data = self._parse_json(self._generate(obs.extra["map_bgr"], prompt))
        print(f"DATA = {data}")
        if not data:
            return Decision(action="stop", rationale="model did not return valid JSON")
        poi = pois.get(str(data.get("goal")))   # 0 / numéro inconnu -> None -> stop
        return Decision(action="goto" if poi else "stop",
                        goal_xy=tuple(poi["xy"]) if poi else None,
                        rationale=data.get("why", ""), note=data.get("note", ""),
                        landmark=bool(data.get("landmark", False)))

    @staticmethod
    def _parse_json(raw: str) -> dict | None:  # parse défensif (try/except)
        try:
            # les modèles produisent souvent des guillemets typographiques
            # (" " ' ') -> JSON invalide. On les normalise avant de parser.
            raw = raw.translate(str.maketrans({
                "“": '"', "”": '"', "‘": "'", "’": "'"}))
            return json.loads(raw[raw.find("{"): raw.rfind("}")+1])
        except Exception:
            return None


def _heading_to_world(heading_deg, distance_m, obs: Observation):
    """VOIE B : cap (deg, repère robot) + distance (m) -> but (x, y) en repère odom.

    Convention ROS (REP-103) : le yaw croît vers la GAUCHE (anti-horaire), donc
    heading_deg positif = gauche. Aucune calibration caméra nécessaire : on
    compose simplement le cap demandé avec le yaw courant du robot.
    """
    if heading_deg is None or distance_m is None:
        return None
    try:
        # clamp de sécurité : on refuse les valeurs aberrantes du modèle
        heading = math.radians(max(-90.0, min(90.0, float(heading_deg))))
        dist = max(0.0, min(3.0, float(distance_m)))
    except (TypeError, ValueError):
        return None
    x, y, yaw = obs.robot_xy_yaw
    theta = yaw + heading
    return (x + dist * math.cos(theta), y + dist * math.sin(theta))


def _pixel_to_world(point_px, obs: Observation):
    # VOIE A — PLACEHOLDER : pixels -> mètres (intrinsèques caméra + plan sol).
    # Renvoie None tant que non implémenté (cf. §12, pièges). Mini-projet à part.
    # Activée par nav_mode="pixel".
    return None


# ============================================================================
