# Passation — perf Isaac Sim / MuJoCo (à coller dans Claude web/mobile)

> Colle tout ce document dans une nouvelle conversation Claude (claude.ai) pour qu'il
> reprenne le contexte et continue à m'aider, même après fermeture du terminal.

## Contexte machine
- Laptop : **Lenovo Legion Slim 7 16APH8** (product 82Y4), BIOS M1CN43WW
- CPU/iGPU : AMD Ryzen 7040 (Phoenix), iGPU **Radeon 780M**
- dGPU : **NVIDIA RTX 4060 Laptop (Max-Q)**, **8 Go VRAM**, TGP max 140 W
- OS : Ubuntu 24.04.4 LTS, noyau 6.17.0-35-generic
- 16 cœurs, 30 Go RAM, sur secteur, gouverneur CPU `performance`
- Usage : simulation robot quadrupède Unitree Go2 sous **Isaac Sim 4.5 / Isaac Lab 2.1**
  (dans Docker) + **MuJoCo**. Besoin : caméra du Go2 simulé, entraînement RL, et brancher
  un LLM de high-reasoning / un VLM. Ne rien casser de ces trois usages.

## Problème
Isaac Sim (et parfois MuJoCo) tournent **lentement et de façon peu réactive**, alors qu'un
MacBook « moins puissant » d'un collègue s'en sort mieux.

## Ce qui est déjà établi (diagnostic)
- **Pas de bug ni d'incompatibilité.** Config Linux correcte : la dGPU NVIDIA rend bien
  l'OpenGL, gouverneur `performance`, sur secteur.
- **Comparaison MacBook faussée** : MuJoCo est CPU-léger (les Mac Apple Silicon excellent) ;
  Isaac Sim **ne tourne pas nativement sur macOS** → le collègue le **streame** depuis une
  machine/cloud RTX. Mon laptop fait, lui, tout le rendu en local.
- **Contraintes physiques réelles** : 8 Go VRAM = plafond pour Isaac Sim ; GPU laptop Max-Q
  (puissance soutenue limitée, throttling thermique) ; Docker = léger surcoût.
- **Cause majeure de la non-réactivité : affichage « muxless »**. `xrandr --listproviders`
  montre que l'**écran est piloté par l'iGPU AMD** (Sink Output) et que la NVIDIA ne fait que
  rendre (Source Output). Donc chaque image rendue par la RTX est **recopiée vers l'iGPU**
  pour l'affichage → latence/à-coups.

## Prochaines étapes (par impact)
1. **Activer le MUX → mode Discrete/dGPU-only** (gain n°1 de réactivité, réversible, coûte de
   l'autonomie). Le Legion Slim 7 16APH8 a un MUX matériel (« Hybrid Mode » / « GPU Working
   Mode »). Le basculer via :
   - **Lenovo Vantage (Windows)** → Appareil → Affichage/Power → désactiver Hybrid Mode →
     reboot. Le réglage persiste sous Linux. (voie la plus sûre)
   - ou **BIOS** (F2 au démarrage → Configuration → « Hybrid Mode » si présent ; parfois retiré
     du BIOS sur Legion récents).
   - Vérifier après reboot : `xrandr --listproviders` doit montrer la **NVIDIA** en `Sink Output`.
2. **Module Linux `legion-laptop`** (projet LenovoLegionLinux) : **installable** (en-têtes
   noyau, DKMS 3.0.11, gcc, Secure Boot désactivé — tout est OK). MAIS il expose surtout
   ventilos/profils de puissance/batterie ; **probablement pas** le switch MUX sur ce modèle
   AMD. À n'envisager que pour la gestion ventilos/puissance, pas pour le MUX.
3. **Réduire la charge GPU/VRAM d'Isaac Sim** dans `cfg/sim.yaml`, MAIS sous contraintes :
   garder la caméra du Go2, ne rien toucher qui affecte le RL ni le VLM/LLM.
   - ⚠️ Le bloc `sim_app` (hide_ui/width/height/anti_aliasing) de `cfg/sim.yaml` n'est **branché
     à rien** dans le code → le modifier ne fait rien.
   - Les vrais leviers (semantic_segmentation, depth_image, enable_lidar, env_name, freq) ont
     tous un downside fonctionnel → à arbitrer selon le capteur/scène réellement utilisés.
4. **Thermique** : surface dure, ventilation dégagée, profil « performance » constructeur actif
   (relève le TGP vers 140 W).
5. **Alternative** : faire comme le collègue → Isaac Sim **headless + streaming** depuis une
   machine RTX desktop/cloud, le laptop servant de client.

## Astuce MuJoCo
Forcer le rendu sur la dGPU si MuJoCo rame :
```bash
__NV_PRIME_RENDER_OFFLOAD=1 __GLX_VENDOR_LIBRARY_NAME=nvidia python mon_script_mujoco.py
```
