# Réveil progressif — Intégration Home Assistant

Intégration custom (`custom_components/reveil_progressif/`) qui crée des réveils
progressifs avec lumière, musique, radiateur et notification. Chaque réveil est
une entrée de configuration distincte, avec entités auto-créées — **zéro YAML à
maintenir par réveil**.

## Installation

1. Copier le dossier `reveil_progressif/` dans `custom_components/` de votre
   configuration HA (typiquement `/config/custom_components/reveil_progressif/`).
2. Redémarrer Home Assistant.
3. **Paramètres → Appareils & services → Ajouter une intégration** → chercher
   "Réveil progressif".
4. Configurer le réveil (nom, heure, jours, lumière, musique, etc.).

## Entités créées par réveil

| Entité | Type | Rôle |
|--------|------|------|
| `switch.<nom>_actif` | `switch` | Activer / désactiver le réveil |
| `time.<nom>_heure` | `time` | Heure du réveil (éditable) |
| `select.<nom>_jours` | `select` | Jours actifs (tous / semaine / weekend / jour précis) |
| `sensor.<nom>_statut` | `sensor` | Statut (Inactif / Programmé / En cours / Terminé) |
| `sensor.<nom>_prochain` | `sensor` | Date/heure du prochain réveil |

## Ajouter un réveil

Paramètres → Appareils & services → Réveil progressif → **Configurer** →
**Ajouter un réveil**. Chaque réveil est indépendant ; on peut en créer autant
que souhaité.

## Modifier un réveil

Paramètres → Appareils & services → Réveil progressif → **Configurer** sur
l'instance → éditer les options.

## Fonctionnement du cycle

À l'heure programmée (si le réveil est actif et le jour correspond) :

1. **Musique** (si activée) — `media_player.play_media` + `volume_set`
2. **Radiateur** (si configuré) — `switch.turn_on`
3. **Lumière progressive** (si activée) — incréments `brightness_step_pct` sur la
   durée configurée (5 à 60 min)
4. **Délai final** de 15 minutes
5. **Extinction de la lumière**
6. **Notification mobile** si toujours au lit (capteurs Withings)

## Fichiers

```
custom_components/reveil_progressif/
├── manifest.json          # Métadonnées de l'intégration
├── const.py               # Constantes et clés de config
├── __init__.py             # Setup / unload entry
├── config_flow.py          # UI d'ajout et d'édition
├── coordinator.py          # Planification + cycle de réveil
├── switch.py               # Entité switch (actif)
├── time.py                 # Entité time (heure)
├── select.py               # Entité select (jours)
├── sensor.py               # Entités sensor (statut + prochain)
├── strings.json            # Traductions (fr par défaut)
├── services.yaml           # Services exposés
└── translations/
    ├── en.json             # Traductions EN
    └── fr.json             # Traductions FR
```