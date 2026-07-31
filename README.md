# SmartWAKE — Intégration Home Assistant

<p align="center">
  <img src="https://img.shields.io/badge/Home%20Assistant-2024.1%2B-41BDF5?logo=home-assistant&logoColor=white" />
  <img src="https://img.shields.io/badge/HACS-Custom-41BDF5?logo=home-assistant-community-store&logoColor=white" />
  <img src="https://img.shields.io/badge/version-2.6.0-blue" />
  <img src="https://img.shields.io/badge/python-3.12%2B-yellow" />
  <img src="https://img.shields.io/badge/security-bandit%200%20finding-green" />
  <img src="https://img.shields.io/badge/security-semgrep%200%20finding-green" />
  <img src="https://img.shields.io/badge/tests-40%20passed-green" />
</p>

Un réveil domotique complet qui ne se contente pas de sonner : il **prépare la maison** au réveil (chauffage, lumière progressive, musique, volets, café), s'adapte au **calendrier** (jours fériés, vacances scolaires, vacances) et à la **présence réelle** des occupants. Optionnellement enrichi par l'**IA** (briefing, musique adaptative, suggestion d'heure, bilan de sommeil).

## Configuration simplifiée

**1 étape pour créer un réveil** (30 secondes) :
- Nom (accents acceptés : Réveil, Élève...)
- Heure
- Jours actifs
- **Preset** : 🎵 Simple, 🌅 Confort, 🏠 Complet

**Menu Configurer** (7 sections, modifiable après) :
- **Base** — heure, heure par jour, jours, ponctuel, skip, vacances
- **🎵 Musique** — MediaSelector (playlist/radio/favoris), volume progressif
- **💡 Lumière** — aube progressive, luminosité, durée
- **🏠 Confort** — chauffage, cafetière, volets (position %), scène matin
- **🧠 Intelligence** — présence, jours fériés, Withings, mouvement, escalade
- **📱 Notification** — notify (EntitySelector), TTS (message séparé), snooze
- **🤖 AI Task** — briefing, musique adaptative, suggestion, **tasks personnalisées**

Chaque champ a une **description** expliquant ce qu'il fait et pourquoi.

## Fonctionnalités

### Planification
- **Multi-alarmes** : plusieurs réveils indépendants (semaine, week-end, sport, enfants…)
- **Heure unique** ou **heure par jour** : lundi 8h, mardi 9h, weekend 10h — un seul réveil suffit
- **Jours** : tous / semaine / weekend / personnalisé (cases indépendantes)
- **Jours fériés** : désactivation via capteur `workday` (calendrier officiel français)
- **Vacances scolaires** : désactivation via `calendar` entity (ICS Éducation nationale)
- **Mode vacances** : booléen OU entité (calendar, input_boolean, person) — automatique
- **Skip une fois** : sauter le prochain réveil sans toucher à la planification
- **Alarme ponctuelle** : réveil unique auto-désactivé après déclenchement

### Pré-réveil (la maison se prépare avant vous)
- **Chauffage** : radiateur/thermostat en mode confort **X minutes avant**
- **Chauffe-eau / sèche-serviettes** : anticipation salle de bain
- **Simulation d'aube** : montée progressive de la luminosité sur 5–60 min
- **Cafetière / bouilloire** : prise connectée ON à H−X min

### Réveil (à l'heure H)
- **Musique** via MediaSelector (Spotify, radio, favoris) avec volume progressif
- **Volets** : ouverture à position configurable (0-100%) si soleil levé
- **Scène matin** : multi-sélection de lumières/scènes (couloir, cuisine, sdb)
- **Notification mobile** actionnable avec boutons **Snooze** / **Stop**
- **Briefing vocal (TTS)** : message personnalisable, séparé de la notification.
  Nécessite une enceinte (`media_player`) **et** un moteur de synthèse
  (`tts.*`) ; le moteur est détecté automatiquement s'il n'est pas précisé.

### Contrôles pendant la sonnerie
- **Snooze** : durée configurable, nombre max de répétitions
- **Stop** : notification actionnable, bouton, ou détection de mouvement salle de bain
- **Escalade** : progressive (3 niveaux : 60% → 80% → 100%) ou classique (tout à 100%)

### Intelligence contextuelle
- **Présence** : ne sonne pas si la personne n'est pas à la maison
- **Lever anticipé** : mouvement cuisine avant l'heure → annule la sonnerie
- **Withings** : ne sonne pas si personne au lit
- **Escalade intelligente** : 3 niveaux progressifs au lieu de tout à 100% d'un coup

### AI Task (HA ≥ 2025.8, optionnel)
- **Briefing matinal IA** : briefing naturel (météo, agenda, trajet, batterie)
- **Musique adaptative** : l'IA choisit la playlist selon la météo
- **Suggestion d'heure du soir** : notification Accepter/Refuser (l'IA propose, vous validez)
- **Bilan de sommeil hebdomadaire** : synthèse + recommandations (service `smartwake.bilan_hebdo`).
  Désignez vos capteurs de sommeil dans *Options → AI Task → Capteurs de sommeil* :
  score, durées de sommeil profond/léger/paradoxal, réveils nocturnes,
  endormissement, ronflement. Compatible Withings, Fitbit, Oura ou tout autre
  capteur. Les moyennes sur 7 jours sont calculées via le recorder, avec repli
  sur la dernière nuit s'il est indisponible, et les durées en secondes sont
  converties en heures et minutes.
- **Vérification lever caméra** : 10 min après le Stop, escalade si encore au lit
- **AI tasks personnalisées** : votre propre prompt + déclencheur + entités + notification

> Les prompts utilisés sont **visibles** dans la description de chaque champ.
> L'IA ne déclenche **jamais** la sonnerie. Fallback automatique si indisponible.

## Entités créées

Les `entity_id` sont dérivés du **nom du réveil** et du nom convivial de chaque
entité. Pour un réveil nommé `reveil` :

### Contrôles
| Entité | Description |
|--------|-------------|
| `switch.reveil_actif` | Activation du réveil (état restauré au redémarrage) |
| `switch.reveil_mode_vacances` | Suspend le réveil sans le désactiver |
| `switch.reveil_saut_du_prochain` | Saute la prochaine occurrence — et permet de l'annuler |
| `time.reveil_heure` | Heure de référence |
| `time.reveil_heure_lundi` … `_dimanche` | Heure propre à chaque jour (mode `par_jour`) |
| `select.reveil_jours` | `tous` / `semaine` / `weekend` / `personnalise` |
| `select.reveil_mode_heure` | `unique` ou `par_jour` |
| `button.reveil_declencher` / `_stop` / `_sauter_prochain` / `_reset` | Actions immédiates |

### Sondes supervisables (binary_sensor)
| Entité | Description |
|--------|-------------|
| `binary_sensor.reveil_sonne_aujourd_hui` | Le réveil doit sonner aujourd'hui (toutes conditions combinées) |
| `binary_sensor.reveil_reveil_en_cours` | Le cycle est actif (ringing / prewake / snoozed) |
| `binary_sensor.reveil_jour_ferie` | Jour férié (via capteur workday) |
| `binary_sensor.reveil_weekend` | Samedi ou dimanche |
| `binary_sensor.reveil_vacances_scolaires` | Vacances scolaires en cours (via calendar entity) |

### État et statistiques (sensors)
| Entité | Description |
|--------|-------------|
| `sensor.reveil_statut` | `idle` / `prewake` / `ringing` / `snoozed` / `done` / `inactif` |
| `sensor.reveil_prochain_reveil` | Date/heure du prochain réveil (`timestamp`) |
| `sensor.reveil_snooze_utilises` | Snoozes utilisés sur le cycle en cours |
| `sensor.reveil_declenchements_total` | Déclenchements cumulés (`total_increasing`) |
| `sensor.reveil_snoozes_total` | Snoozes cumulés (`total_increasing`) |
| `sensor.reveil_stops_total` | Stops cumulés (`total_increasing`) |
| `sensor.reveil_dernier_reveil` | Horodatage du dernier réveil |

### Réglages (number)
`snooze_min`, `max_snooze`, `pre_chauffage_min`, `aube_min`,
`duree_eclairage_min`, `luminosite_max`, `escalade_min`, `volume_initial`,
`volume_final`, `cafe_avant_min`.

> `sensor.<nom>_prochain_reveil` est la **seule source fiable** de l'heure qui
> sonnera : `time.<nom>_heure` n'est que l'heure de référence, et peut être
> décalée par le mode `par_jour`, l'agenda adaptatif ou la phase de sommeil.

### Events HA (pour automatisations externes)
| Event | Déclencheur |
|-------|------------|
| `smartwake_triggered` | Réveil déclenché |
| `smartwake_stopped` | Réveil arrêté (raison : manual/snooze_max/mouvement_sdb) |
| `smartwake_snoozed` | Snooze activé |
| `smartwake_escalade` | Escalade (level : doux/moyen/max) |
| `smartwake_prewake` | Phase pré-réveil |
| `smartwake_activated` | Réveil activé |
| `smartwake_deactivated` | Réveil désactivé |
| `smartwake_anomalie` | Anomalie détectée (type) |

### Robustesse
- **Watchdog** : vérifie l'armement au démarrage HA + détecte les redémarrages nocturnes
- **Logbook** : journalise les événements (sans données sensibles)
- **Détection d'anomalie** : HA redémarré la nuit, alarme non armée → alerte
- **Notification actions** : capte `REVEIL_SNOOZE` / `REVEIL_STOP` / `REVEIL_ACCEPTER_HH:MM` depuis l'app mobile
- **Retry** : musique (3 tentatives + fallback TTS), volets (2 tentatives + ouverture au lever du soleil)
- **Apprentissage** : suit les habitudes (heure lever réelle, snooze moyen, régularité) + suggestions d'ajustement

### Assist / commande vocale (LLM Tool Calling)
- « Réveille-moi à 6h45 demain » → `smartwake_set_time`
- « Active le réveil semaine » → `smartwake_activate`
- « Pas de réveil demain » → `smartwake_skip`
- « Quand sonne le prochain réveil ? » → `smartwake_status`

## Installation

### Via HACS (recommandé)

1. Ajoutez ce dépôt dans HACS :
   - *HACS → Integrations → ⋮ → Custom repositories*
   - URL : `https://github.com/junkoku38/smartwake`
   - Category : **Integration**
2. Cliquez **Install** sur "SmartWAKE"
3. **Redémarrez** Home Assistant
4. *Paramètres → Appareils & Services → Ajouter une intégration* → cherchez **"SmartWAKE"**

### Custom card (dashboard)

Installez aussi la carte dédiée via HACS Frontend :
- URL : `https://github.com/junkoku38/smartwake-card`
- Category : **Dashboard (Lovelace)**

```yaml
type: custom:smartwake-card
entity: switch.reveil_actif
name: Mon réveil
show_stats: true
show_context: true
```

## Entités créées (par réveil)

| Entité | Type | Rôle |
|--------|------|------|
| `switch.<nom>_actif` | switch | Activer / désactiver le réveil |
| `time.<nom>_heure` | time | Heure du réveil (éditable) |
| `select.<nom>_jours` | select | Jours actifs |
| `sensor.<nom>_statut` | sensor | Statut (enum : idle/prewake/ringing/snoozed/done) |
| `sensor.<nom>_prochain_reveil` | sensor | Date/heure du prochain réveil (timestamp) |
| `sensor.<nom>_snooze_count` | sensor | Snoozes utilisés (cycle en cours) |
| `sensor.<nom>_total_declenchements` | sensor | Déclenchements totaux (diagnostic) |
| `sensor.<nom>_total_snoozes` | sensor | Snoozes totaux (diagnostic) |
| `sensor.<nom>_total_stops` | sensor | Stops totaux (diagnostic) |
| `sensor.<nom>_dernier_reveil` | sensor | Dernier réveil (diagnostic) |
| `button.<nom>_stop` | button | Arrêter le réveil |
| `button.<nom>_sauter_prochain` | button | Sauter le prochain réveil (config) |
| `button.<nom>_reset` | button | Reset de l'état (diagnostic) |
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
| Carte dashboard | [smartwake-card](https://github.com/junkoku38/smartwake-card) |
| Interface | Carte Mushroom, custom:alarm-clock-card |

## Sécurité

Le composant a été audité (revue de code défensive + SAST).

### Scanners
- **Bandit** : 0 finding
- **Semgrep** : 0 finding
- **Secrets** : 0 finding

### Mesures de sécurité
- **Contrôle d'accès strict** : `entity_registry` (match par `config_entry_id`)
- **Validation des entrées** : slugify (accents), regex heure `^\d{1,2}:\d{2}$` + bornes
- **Anti-injection de prompt IA** : séparation instructions / données contextuelles
- **Principe de moindre privilège** : AI Task sans accès aux services HA
- **Logbook sans fuite** : pas de détails sensibles (RDV, heures exactes)
- **L'IA ne déclenche jamais la sonnerie** : `time` trigger déterministe

### Signaler une vulnérabilité
Ouvrez une issue sur https://github.com/junkoku38/smartwake/issues

## Tests

34 tests unitaires (pytest) couvrant :
- `_jours_actifs` (tous, semaine, weekend, jour unique, personnalisé vide/plein)
- `_parse_heure` (valide, minuit, invalide)
- Coordinator (activation, désactivation, set_heure, set_jours, snooze max, skip, reset)
- `_sonne_aujourd_hui` (semaine, weekend, mode vacances, skip)
- Validation nom (slugify, accents)
- Validation heure notification (valide, invalide, injection)
- AI module (désactivé, fallback)

## Licence

MIT