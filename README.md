# SmartWAKE — Intégration Home Assistant

<p align="center">
  <img src="https://img.shields.io/badge/Home%20Assistant-2024.1%2B-41BDF5?logo=home-assistant&logoColor=white" />
  <img src="https://img.shields.io/badge/HACS-Custom-41BDF5?logo=home-assistant-community-store&logoColor=white" />
  <img src="https://img.shields.io/badge/version-2.2.0-blue" />
  <img src="https://img.shields.io/badge/python-3.12%2B-yellow" />
  <img src="https://img.shields.io/badge/security-bandit%200%20finding-green" />
  <img src="https://img.shields.io/badge/security-semgrep%200%20finding-green" />
</p>

Un réveil domotique complet qui ne se contente pas de sonner : il **prépare la maison** au réveil (chauffage, lumière progressive, musique, volets, café), s'adapte au **calendrier** (jours fériés, vacances scolaires, vacances) et à la **présence réelle** des occupants.

## Fonctionnalités

### Planification
- **Multi-alarmes** : plusieurs réveils indépendants (semaine, week-end, sport, enfants…)
- **Heure configurable** par alarme
- **Sélection des jours** : lundi → dimanche, cases indépendantes, ou modes prédéfinis (tous / semaine / weekend / personnalisé)
- **Jours fériés** : désactivation automatique via capteur `workday` (calendrier officiel français, option Alsace-Moselle)
- **Vacances scolaires** : désactivation via un `calendar` entity (ICS de l'Éducation nationale)
- **Mode vacances** global qui suspend le réveil
- **Skip une fois** : sauter le prochain réveil sans toucher à la planification
- **Alarme ponctuelle** : réveil unique auto-désactivé après déclenchement

### Pré-réveil (la maison se prépare avant vous)
- **Chauffage** : passage des radiateurs / thermostat en mode confort **X minutes avant**
- **Chauffe-eau / sèche-serviettes** : anticipation salle de bain
- **Simulation d'aube** : montée progressive de la luminosité sur 15–30 min
- **Cafetière / bouilloire** : prise connectée ON à H−10 min

### Réveil (à l'heure H)
- **Musique** avec volume progressif (10 % → 40 % sur 5 min)
- **Volets roulants** : ouverture (totale ou partielle selon saison/lever du soleil)
- **Lumière** : autres pièces allumées en scène "matin"
- **Notification mobile** actionnable avec boutons **Snooze** / **Stop**
- **Briefing vocal (TTS)** : météo du jour (optionnel)

### Contrôles pendant la sonnerie
- **Snooze** : durée configurable, nombre max de répétitions
- **Stop** : notification actionnable, bouton physique, ou détection de mouvement salle de bain
- **Escalade** : si pas de Stop après N minutes → volume max + toutes lumières à 100 %

### Intelligence contextuelle
- **Présence** : ne pas sonner si personne à la maison
- **Lever anticipé** : si mouvement détecté dans la cuisine avant l'heure → annuler la sonnerie
- **Sommeil** : intégration capteurs Withings (au lit / pas au lit)
- **Saison** : ouvrir les volets seulement si le soleil est levé

### Sondes supervisables (binary_sensor)
| Entité | Description |
|--------|-------------|
| `sonne_aujourd_hui` | Le réveil doit sonner aujourd'hui (toutes conditions combinées) |
| `reveil_en_cours` | Le cycle est actif (ringing / prewake / snoozed) |
| `jour_ferie` | Jour férié (via capteur workday) |
| `weekend` | Samedi ou dimanche |
| `vacances_scolaires` | Vacances scolaires en cours (via calendar entity) |

### AI Task (HA ≥ 2025.8, optionnel)
- **Briefing matinal IA** : rédige un briefing naturel (météo, agenda, trajet, batterie) au lieu d'un TTS robotique
- **Musique adaptative** : l'IA choisit la playlist selon la météo et le contexte
- **Suggestion d'heure du soir** : notification actionnable Accepter/Refuser (l'IA propose, l'utilisateur valide)
- **Bilan de sommeil hebdomadaire** : synthèse de la semaine + recommandations (service `smartwake.bilan_hebdo`)
- **Vérification lever caméra** : 10 min après le Stop, l'IA vérifie si vous êtes levé → escalade si encore au lit

> ⚠️ L'IA ne déclenche **jamais** la sonnerie. Fallback automatique si indisponible.

### Robustesse
- **Watchdog** : vérifie l'armement au démarrage HA
- **Logbook** : journalise les événements (activation, déclenchement, snooze, stop, escalade)
- **Notification actions** : capte `REVEIL_SNOOZE` / `REVEIL_STOP` depuis l'app mobile
- **Dashboard auto** : carte Lovelace injectée automatiquement dans Overview

## Installation

### Via HACS (recommandé)

1. Ajoutez ce dépôt dans HACS :
   - *HACS → Integrations → ⋮ → Custom repositories*
   - URL : `https://github.com/junkoku38/smartwake`
   - Category : **Integration**
2. Cliquez **Install** sur "SmartWAKE"
3. **Redémarrez** Home Assistant
4. *Paramètres → Appareils & Services → Ajouter une intégration* → cherchez **"SmartWAKE"**

### Manuellement

1. Copiez le dossier `custom_components/smartwake/` dans votre dossier `/config/custom_components/`
2. Redémarrez Home Assistant
3. *Paramètres → Appareils & Services → Ajouter une intégration* → "SmartWAKE"

## Configuration

Le config flow se déroule en **6 étapes** :

| Étape | Description |
|-------|-------------|
| **Base** | Nom, heure, jours actifs, ponctuel, skip, mode vacances |
| **Lumière & aube** | Lumière progressive, luminosité max, durée, simulation d'aube |
| **Musique** | Media player, playlist/radio, volume initial/final, durée de montée |
| **Confort** | Pré-chauffage, radiateur, chauffe-eau, cafetière, volets |
| **Intelligence** | Présence, workday, Withings, mouvement salle de bain, lever anticipé |
| **Notification** | Notification mobile, TTS, snooze, escalade |

Tous les paramètres sont éditables ensuite via *Configurer* sur l'intégration.

## Entités créées (par réveil)

| Entité | Type | Rôle |
|--------|------|------|
| `switch.<nom>_actif` | switch | Activer / désactiver le réveil |
| `time.<nom>_heure` | time | Heure du réveil (éditable) |
| `select.<nom>_jours` | select | Jours actifs |
| `sensor.<nom>_statut` | sensor | Statut (idle / prewake / ringing / snoozed / done) |
| `sensor.<nom>_prochain_reveil` | sensor | Date/heure du prochain réveil |
| `sensor.<nom>_snooze_count` | sensor | Nombre de snooze utilisés |
| `button.<nom>_stop` | button | Arrêter le réveil |
| `button.<nom>_sauter_prochain` | button | Sauter le prochain réveil |
| `button.<nom>_reset` | button | Reset de l'état |
| `button.<nom>_declencher` | button | Déclencher manuellement |
| `number.<nom>_snooze_min` | number | Durée du snooze |
| `number.<nom>_max_snooze` | number | Nombre max de snooze |
| `number.<nom>_pre_chauffage_min` | number | Pré-chauffage avant (min) |
| `number.<nom>_aube_min` | number | Durée simulation aube (min) |
| `number.<nom>_duree_eclairage_min` | number | Durée éclairage progressif (min) |
| `number.<nom>_luminosite_max` | number | Luminosité maximale |
| `number.<nom>_escalade_min` | number | Escalade après (min) |
| `number.<nom>_volume_initial` | number | Volume initial musique |
| `number.<nom>_volume_final` | number | Volume final musique |
| `number.<nom>_cafe_avant_min` | number | Café avant (min) |
| `binary_sensor.<nom>_sonne_aujourd_hui` | binary_sensor | Sonne aujourd'hui |
| `binary_sensor.<nom>_reveil_en_cours` | binary_sensor | Réveil en cours |
| `binary_sensor.<nom>_jour_ferie` | binary_sensor | Jour férié |
| `binary_sensor.<nom>_weekend` | binary_sensor | Weekend |
| `binary_sensor.<nom>_vacances_scolaires` | binary_sensor | Vacances scolaires |

## Services

| Service | Description |
|---------|-------------|
| `smartwake.declencher` | Déclenche manuellement le cycle de réveil |
| `smartwake.snooze` | Active le snooze |
| `smartwake.stop` | Arrête immédiatement le cycle |
| `smartwake.sauter_prochain` | Saute le prochain réveil |
| `smartwake.reset` | Remet à zéro l'état |
| `smartwake.bilan_hebdo` | Génère et envoie un bilan de sommeil hebdomadaire via AI Task |

## Intégrations recommandées

| Besoin | Intégration HA |
|--------|----------------|
| Jours fériés FR | **Workday** (natif) |
| Vacances scolaires FR | Calendrier ICS (intégration *Calendar*) |
| Musique | Spotify, Music Assistant, Radio Browser, Sonos/Cast |
| TTS briefing | Piper (local), Google TTS, Assist |
| Capteur de sommeil | Withings, Sleep as Android (MQTT) |
| Boutons physiques | Zigbee (IKEA/Aqara), tag NFC |
| AI Task | Ollama (local), Anthropic, Google, OpenAI |
| Interface | Carte Mushroom, custom:alarm-clock-card |

## Sécurité

Le composant a été audité (revue de code défensive + SAST).

### Scanners
- **Bandit** : 0 finding
- **Semgrep** : 0 finding
- **Secrets** : 0 finding (aucun token/credential dans le code)

### Mesures de sécurité implémentées
- **Contrôle d'accès strict** : les services utilisent `entity_registry` (match par `config_entry_id`, pas par sous-chaîne)
- **Validation des entrées** : nom du réveil validé par regex `^[A-Za-z0-9_-]{1,30}$`, heure validée par regex `^\d{1,2}:\d{2}$` + bornes
- **Anti-injection de prompt IA** : séparation des instructions et des données contextuelles dans les prompts
- **Principe de moindre privilège** : l'entité AI Task ne doit pas avoir accès aux services HA (documenté dans le config flow)
- **Logbook sans fuite** : les événements journalisés ne contiennent pas de données sensibles (pas de détails de RDV, pas d'heures exactes)
- **L'IA ne déclenche jamais la sonnerie** : la sonnerie reste un `time` trigger déterministe

### Signaler une vulnérabilité
Ouvrez une issue sur https://github.com/junkoku38/smartwake/issues ou contactez le codeowner.

## Licence

MIT