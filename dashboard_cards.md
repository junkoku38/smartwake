# Cartes Dashboard — SmartWAKE

Trois versions, de la plus simple à la plus jolie. Adaptées pour les entités
auto-créées par l'intégration SmartWAKE (remplacez `<nom>` par le nom de votre
réveil, ex: `reveil`, `semaine`, `weekend`).

---

## Option A — 100 % native (aucune installation)

Fonctionne immédiatement, sans HACS.

```yaml
type: vertical-stack
cards:
  - type: entities
    title: ⏰ SmartWAKE
    show_header_toggle: false
    entities:
      - entity: switch.reveil_actif
        name: Activé
      - entity: time.reveil_heure
        name: Heure
      - type: divider
      - entity: select.reveil_jours
        name: Jours
      - type: divider
      - entity: number.reveil_snooze_min
        name: Snooze (min)
      - entity: number.reveil_max_snooze
        name: Max snooze
      - entity: number.reveil_pre_chauffage_min
        name: Chauffage avant (min)
      - entity: number.reveil_aube_min
        name: Simulation aube (min)
      - entity: number.reveil_volume_final
        name: Volume final
      - type: divider
      - entity: binary_sensor.reveil_sonne_aujourd_hui
        name: Sonne aujourd'hui
      - entity: binary_sensor.reveil_weekend
        name: Weekend
      - entity: binary_sensor.reveil_jour_ferie
        name: Jour férié
      - entity: binary_sensor.reveil_vacances_scolaires
        name: Vacances scolaires
      - entity: sensor.reveil_statut
        name: État
  # Boutons d'action
  - type: horizontal-stack
    cards:
      - type: button
        name: Snooze
        icon: mdi:alarm-snooze
        tap_action:
          action: call-service
          service: smartwake.snooze
          target:
            entity_id: switch.reveil_actif
      - type: button
        name: Stop
        icon: mdi:alarm-off
        tap_action:
          action: call-service
          service: smartwake.stop
          target:
            entity_id: switch.reveil_actif
      - type: button
        name: Skip
        icon: mdi:skip-next
        tap_action:
          action: call-service
          service: smartwake.sauter_prochain
          target:
            entity_id: switch.reveil_actif
      - type: button
        name: Reset
        icon: mdi:restart
        tap_action:
          action: call-service
          service: smartwake.reset
          target:
            entity_id: switch.reveil_actif
```

---

## Option B — Mushroom (recommandée : compacte et moderne)

Prérequis HACS : **Mushroom Cards**.

```yaml
type: vertical-stack
cards:
  # En-tête : heure + toggle + statut
  - type: custom:mushroom-template-card
    primary: >-
      SmartWAKE — {{ states('time.reveil_heure')[0:5] }}
    secondary: >-
      {% if is_state('binary_sensor.reveil_reveil_en_cours','on') %} 🔔 En cours
      {% elif is_state('binary_sensor.reveil_sonne_aujourd_hui','on') %} ✅ Sonne aujourd'hui
      {% elif is_state('sensor.reveil_statut','snoozed') %} 😴 Snooze
      {% else %} 💤 Inactif aujourd'hui {% endif %}
    icon: mdi:alarm
    icon_color: >-
      {{ 'red' if is_state('binary_sensor.reveil_reveil_en_cours','on')
         else 'amber' if is_state('switch.reveil_actif','on')
         else 'grey' }}
    tap_action:
      action: more-info
      entity: time.reveil_heure
    entity: switch.reveil_actif

  # Prochain réveil
  - type: custom:mushroom-template-card
    primary: >-
      {% if states('sensor.reveil_prochain_reveil') not in ['unknown','unavailable'] %}
        Prochain : {{ as_datetime(states('sensor.reveil_prochain_reveil')).strftime('%d/%m %H:%M') }}
      {% else %} Aucun réveil programmé {% endif %}
    icon: mdi:calendar-clock
    icon_color: blue
    layout: horizontal

  # Sondes contextuelles
  - type: custom:mushroom-chips-card
    alignment: center
    chips:
      - type: template
        content: >-
          {{ '🏖️' if is_state('binary_sensor.reveil_weekend','on') else '💼' }}
          {{ 'Weekend' if is_state('binary_sensor.reveil_weekend','on') else 'Semaine' }}
        icon: >-
          {{ 'mdi:calendar-weekend' if is_state('binary_sensor.reveil_weekend','on') else 'mdi:calendar' }}
        icon_color: "{{ 'green' if is_state('binary_sensor.reveil_weekend','on') else 'blue' }}"
      - type: template
        content: >-
          {{ '🎉 Férié' if is_state('binary_sensor.reveil_jour_ferie','on') else '📅 Travaillé' }}
        icon: mdi:calendar-remove
        icon_color: "{{ 'red' if is_state('binary_sensor.reveil_jour_ferie','on') else 'grey' }}"
      - type: template
        content: >-
          {{ '🏫 Vacances sco' if is_state('binary_sensor.reveil_vacances_scolaires','on') else '🎓 École' }}
        icon: mdi:school
        icon_color: "{{ 'purple' if is_state('binary_sensor.reveil_vacances_scolaires','on') else 'grey' }}"

  # Réglages rapides
  - type: horizontal-stack
    cards:
      - type: custom:mushroom-entity-card
        entity: select.reveil_jours
        name: Jours
        icon: mdi:calendar-week
      - type: custom:mushroom-entity-card
        entity: number.reveil_snooze_min
        name: Snooze
        icon: mdi:alarm-snooze
      - type: custom:mushroom-entity-card
        entity: number.reveil_volume_final
        name: Volume
        icon: mdi:volume-medium

  # Réglages avancés
  - type: entities
    entities:
      - entity: number.reveil_pre_chauffage_min
        name: Pré-chauffage (min)
      - entity: number.reveil_aube_min
        name: Aube (min)
      - entity: number.reveil_duree_eclairage_min
        name: Durée éclairage (min)
      - entity: number.reveil_luminosite_max
        name: Luminosité max
      - entity: number.reveil_escalade_min
        name: Escalade (min)
      - entity: number.reveil_max_snooze
        name: Max snooze

  # Boutons d'action (toujours visibles)
  - type: horizontal-stack
    cards:
      - type: custom:mushroom-template-card
        primary: Snooze
        icon: mdi:alarm-snooze
        icon_color: orange
        tap_action:
          action: call-service
          service: smartwake.snooze
          target:
            entity_id: switch.reveil_actif
      - type: custom:mushroom-template-card
        primary: Stop
        icon: mdi:alarm-off
        icon_color: red
        tap_action:
          action: call-service
          service: smartwake.stop
          target:
            entity_id: switch.reveil_actif
      - type: custom:mushroom-template-card
        primary: Skip
        icon: mdi:skip-next
        icon_color: blue
        tap_action:
          action: call-service
          service: smartwake.sauter_prochain
          target:
            entity_id: switch.reveil_actif
      - type: custom:mushroom-template-card
        primary: Déclencher
        icon: mdi:bell-ring
        icon_color: amber
        tap_action:
          action: call-service
          service: smartwake.declencher
          target:
            entity_id: switch.reveil_actif

  # Snooze count (visible si > 0)
  - type: conditional
    conditions:
      - entity: sensor.reveil_snooze_utilises
        state_not: "0"
    card:
      type: custom:mushroom-template-card
      primary: "Snooze utilisés : {{ states('sensor.reveil_snooze_utilises') }}"
      icon: mdi:restart
      icon_color: orange
```

---

## Option C — Vue "gros réveil" (custom:button-card)

Prérequis HACS : **button-card**. Style écran de réveil, idéal pour une tablette de chevet.

```yaml
type: custom:button-card
entity: switch.reveil_actif
name: SmartWAKE
show_state: false
tap_action: { action: toggle }
hold_action:
  action: more-info
  entity: time.reveil_heure
custom_fields:
  time: >
    [[[ return states['time.reveil_heure'].state.substring(0,5); ]]]
  status: >
    [[[
      const s = states['sensor.reveil_statut'].state;
      const icons = {
        idle: '💤', prewake: '🌅', ringing: '🔔',
        snoozed: '😴', done: '✅', inactif: '⏹️'
      };
      return icons[s] || s;
    ]]]
  prochain: >
    [[[
      const t = states['sensor.reveil_prochain_reveil'].state;
      if (t && t !== 'unknown' && t !== 'unavailable') {
        const d = new Date(t);
        return 'Prochain : ' + d.toLocaleDateString('fr-FR',{day:'2-digit',month:'2-digit'}) +
               ' à ' + d.toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'});
      }
      return '';
    ]]]
styles:
  card:
    - padding: 20px
    - height: 200px
  grid:
    - grid-template-areas: '"i time" "i status" "i prochain"'
    - grid-template-columns: 60px 1fr
  custom_fields:
    time:
      - font-size: 40px
      - font-weight: 700
      - justify-self: start
    status:
      - font-size: 20px
      - justify-self: start
    prochain:
      - font-size: 14px
      - justify-self: start
      - opacity: 0.7
state:
  - value: "on"
    icon: mdi:alarm
    color: var(--warning-color)
  - value: "off"
    icon: mdi:alarm-off
    color: var(--disabled-text-color)
```

---

## Carte complète avec boutons (tablette de chevet)

Combinaison de la vue "gros réveil" + boutons Snooze/Stop conditionnels :

```yaml
type: vertical-stack
cards:
  # Gros affichage
  - type: custom:button-card
    entity: switch.reveil_actif
    name: SmartWAKE
    # ... (voir Option C ci-dessus)

  # Boutons Snooze / Stop (visibles pendant la sonnerie)
  - type: conditional
    conditions:
      - entity: binary_sensor.reveil_reveil_en_cours
        state: "on"
    card:
      type: horizontal-stack
      cards:
        - type: custom:mushroom-template-card
          primary: Snooze
          icon: mdi:alarm-snooze
          icon_color: orange
          tap_action:
            action: call-service
            service: smartwake.snooze
            target:
              entity_id: switch.reveil_actif
        - type: custom:mushroom-template-card
          primary: Stop
          icon: mdi:alarm-off
          icon_color: red
          tap_action:
            action: call-service
            service: smartwake.stop
            target:
              entity_id: switch.reveil_actif
```

---

## Correspondance entités SmartWAKE

| Carte (ancien helper) | Entité SmartWAKE | Type |
|-----------------------|------------------|------|
| `input_boolean.reveil_1_actif` | `switch.<nom>_actif` | switch |
| `input_datetime.reveil_1_heure` | `time.<nom>_heure` | time |
| `input_boolean.reveil_1_lundi`…`dimanche` | `select.<nom>_jours` | select |
| `input_boolean.reveil_1_ignorer_feries` | config (options flow) | — |
| `input_boolean.reveil_1_skip_prochain` | `button.<nom>_sauter_prochain` | button |
| `input_boolean.mode_vacances` | config (options flow) | — |
| `input_select.reveil_1_source_musique` | config (playlist string) | — |
| `input_number.reveil_1_volume_final` | `number.<nom>_volume_final` | number |
| `input_number.reveil_1_prechauffe_min` | `number.<nom>_pre_chauffage_min` | number |
| `input_number.reveil_1_aube_min` | `number.<nom>_aube_min` | number |
| `input_number.reveil_1_snooze_min` | `number.<nom>_snooze_min` | number |
| `binary_sensor.reveil_1_sonne_aujourd_hui` | `binary_sensor.<nom>_sonne_aujourd_hui` | binary_sensor |
| `input_select.reveil_1_etat` | `sensor.<nom>_statut` | sensor |
| `script.reveil_1_snooze` | `smartwake.snooze` | service |
| `script.reveil_1_stop` | `smartwake.stop` | service |

---

## Conseils

- **Multi-alarmes** : créez plusieurs réveils dans SmartWAKE (Autres appareils & services → SmartWAKE → Ajouter). Chaque réveil a ses propres entités. Dupliquez la carte avec le nom correspondant.
- **Tablette de chevet** : Option C en plein écran + kiosk-mode, avec la carte conditionnelle Snooze/Stop en dessous.
- **Snooze / Stop** : les boutons appellent directement les services `smartwake.snooze` et `smartwake.stop` — pas besoin de scripts intermédiaires.