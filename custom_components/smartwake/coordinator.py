"""Coordinateur : moteur complet du réveil progressif.

Gère :
  - Planification multi-jours (granulaire, fériés, vacances, skip)
  - Phase pré-réveil (chauffage, aube, café, chauffe-eau)
  - Phase réveil (musique volume progressif, lumière, volets, notification, TTS)
  - Snooze / Stop / Escalade
  - Lever anticipé (mouvement cuisine → annule)
  - Watchdog au démarrage HA
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time, timedelta
from typing import Any, Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, State, callback
from homeassistant.helpers.event import (
    async_track_time_change,
    async_track_point_in_utc_time,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_AUBE_MIN,
    CONF_BRIGHTNESS_MAX,
    CONF_CAFETIERE,
    CONF_CAFETIERE_MIN,
    CONF_CHAUFFE_EAU,
    CONF_DUREE_PROGRESSIVE,
    CONF_ESCALADE_INTELLIGENTE,
    CONF_ESCALADE_MIN,
    CONF_HEURE,
    CONF_HEURE_LUNDI,
    CONF_HEURE_MARDI,
    CONF_HEURE_MERCREDI,
    CONF_HEURE_JEUDI,
    CONF_HEURE_VENDREDI,
    CONF_HEURE_SAMEDI,
    CONF_HEURE_DIMANCHE,
    CONF_MODE_HEURE,
    CONF_IGNORER_FERIES,
    CONF_IGNORER_VACANCES_SCOLAIRE,
    CONF_VACANCES_SCOLAIRES_CALENDAR,
    CONF_AI_BRIEFING,
    CONF_AI_MUSIQUE_ADAPT,
    CONF_AI_SUGGESTION_HEURE,
    CONF_AI_VERIF_LEVER,
    CONF_AI_CUSTOM_ENABLED,
    CONF_AI_CUSTOM_TASKS,
    CONF_ADAPTATIF_AGENDA,
    CONF_AGENDA_ENTITY,
    CONF_AGENDA_MARGE_MIN,
    CONF_SOMMEIL_PHASE,
    CONF_SOMMEIL_FENETRE_MIN,
    CONF_JOURS,
    CONF_JOURS_PERSO,
    CONF_LEVER_ANTICIPE,
    CONF_LUMIERE,
    CONF_LUMIERE_ACTIVEE,
    CONF_MOUVEMENT_CUISINE,
    CONF_MOUVEMENT_SDB,
    CONF_MOUVEMENT_STOP,
    CONF_MEDIA_PLAYER,
    CONF_MODE_VACANCES,
    CONF_MODE_VACANCES_ENTITY,
    CONF_MUSIQUE_ACTIVEE,
    CONF_NOTIF_MESSAGE,
    CONF_NOTIF_TITRE,
    CONF_NOTIFICATION_ACTIVEE,
    CONF_NOTIFY_DEVICE,
    CONF_PLAYLIST,
    CONF_PONCTUEL,
    CONF_PRECHAUFFE_MIN,
    CONF_PRESENCE,
    CONF_RADIATEUR,
    CONF_SCENE_MATIN_ENTITIES,
    CONF_SCENES_MATIN,
    CONF_SKIP_PROCHAIN,
    CONF_SNOOZE_DUREE,
    CONF_SNOOZE_MAX,
    CONF_TTS_ACTIVEE,
    CONF_TTS_ENTITY,
    CONF_TTS_MESSAGE,
    CONF_VOLUME_DUREE,
    CONF_VOLUME_FINAL,
    CONF_VOLUME_INITIAL,
    CONF_VOLETS,
    CONF_VOLETS_POSITION,
    CONF_VOLETS_SOLEIL,
    CONF_WITHINGS_BED_1,
    CONF_WITHINGS_BED_2,
    CONF_WORKDAY_SENSOR,
    DEFAULT_AUBE_MIN,
    DEFAULT_BRIGHTNESS_MAX,
    DEFAULT_CAFETIERE_MIN,
    DEFAULT_DUREE_PROGRESSIVE,
    DEFAULT_ESCALADE_MIN,
    DEFAULT_NOTIF_MESSAGE,
    DEFAULT_NOTIF_TITRE,
    DEFAULT_TTS_MESSAGE,
    DEFAULT_PRECHAUFFE_MIN,
    DEFAULT_SNOOZE_DUREE,
    DEFAULT_SNOOZE_MAX,
    DEFAULT_AGENDA_MARGE_MIN,
    DEFAULT_SOMMEIL_FENETRE_MIN,
    DEFAULT_VOLUME_DUREE,
    DEFAULT_VOLUME_FINAL,
    DEFAULT_VOLUME_INITIAL,
    JOURS_NUM,
    JOURS_OPTIONS,
    slugify,
    STATUT_DONE,
    STATUT_IDLE,
    STATUT_INACTIF,
    STATUT_PREWAKE,
    STATUT_RINGING,
    STATUT_SNOOZED,
)

_LOGGER = logging.getLogger(__name__)


def _jours_actifs(mode: str, jours_perso: list[str] | None = None) -> set[int]:
    """Retourne l'ensemble des numéros de jour (0=lundi) actifs."""
    if mode == "tous":
        return set(range(7))
    if mode == "semaine":
        return {0, 1, 2, 3, 4}
    if mode == "weekend":
        return {5, 6}
    if mode == "personnalise":
        if jours_perso:
            return {JOURS_NUM[j] for j in jours_perso if j in JOURS_NUM}
        return set()  # personnalise vide = aucun jour
    if mode in JOURS_NUM:
        return {JOURS_NUM[mode]}
    return set(range(7))  # fallback pour mode inconnu


def _parse_heure(heure_str: str) -> time:
    """Convertit 'HH:MM' en objet time."""
    parts = heure_str.split(":")
    return time(hour=int(parts[0]), minute=int(parts[1]))


class ReveilCoordinator(DataUpdateCoordinator):
    """Coordinateur du moteur de réveil."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"smartwake_{entry.entry_id}",
            update_interval=timedelta(seconds=60),
        )
        self.entry = entry
        self._actif = False
        self._statut = STATUT_IDLE
        self._prochain: datetime | None = None
        self._cancel_trigger: Callable | None = None
        self._cancel_prewake: Callable | None = None
        self._cancel_cycle: asyncio.Task | None = None
        self._cancel_escalade: asyncio.Task | None = None
        self._reveil_en_cours = False
        self._snooze_count = 0
        self._skip_prochain = False
        self._unsub_listeners: list[Callable] = []
        self._learning: Any = None

    # ── Propriétés ──────────────────────────────────────────────

    @property
    def actif(self) -> bool:
        return self._actif

    @property
    def statut(self) -> str:
        return self._statut

    @property
    def prochain_reveil(self) -> datetime | None:
        return self._prochain

    @property
    def config(self) -> dict[str, Any]:
        return dict(self.entry.data)

    @property
    def snooze_count(self) -> int:
        return self._snooze_count

    @property
    def skip_prochain(self) -> bool:
        return self._skip_prochain

    # ── DataUpdateCoordinator ──────────────────────────────────

    async def _async_update_data(self) -> dict[str, Any]:
        if self._actif and not self._reveil_en_cours:
            self._calculer_prochain()
        return {
            "actif": self._actif,
            "statut": self._statut,
            "prochain": self._prochain,
            "snooze_count": self._snooze_count,
            "skip_prochain": self._skip_prochain,
        }

    async def async_config_entry_first_refresh(self) -> None:
        """Premier rafraîchissement — watchdog + planification + learning."""
        self._calculer_prochain()
        await super().async_config_entry_first_refresh()
        # Watchdog : vérifier l'armement au démarrage HA
        self._watchdog()
        # Écouter les actions de notification mobile (Snooze / Stop)
        self._setup_notification_actions()
        # Initialiser le module d'apprentissage
        from .learning import LearningManager
        self._learning = LearningManager(self.hass, self.entry.entry_id)
        await self._learning.async_load()

    def _watchdog(self) -> None:
        """Vérifie au démarrage HA que l'alarme est cohérente + détecte les anomalies."""
        cfg = self.entry.data
        anomalies = []

        if self._actif and self._prochain is None:
            _LOGGER.warning(
                "Watchdog: réveil '%s' actif mais aucun prochain déclenchement — "
                "vérifiez la configuration des jours",
                self.entry.title,
            )
            anomalies.append("alarme_non_armee")
        elif self._actif:
            _LOGGER.info(
                "Watchdog: réveil '%s' armé, prochain déclenchement %s",
                self.entry.title,
                self._prochain,
            )

        # Détecter si HA a redémarré pendant la nuit (entre 22h et 8h)
        now = dt_util.now()
        if now.hour >= 22 or now.hour < 8:
            _LOGGER.warning(
                "Anomalie: HA a redémarré à %s (période nocturne) — vérifier que '%s' est armé",
                now.strftime("%H:%M"),
                self.entry.title,
            )
            anomalies.append("redemarrage_nocturne")

        if anomalies:
            self._fire_event("smartwake_anomalie", type=anomalies)
            self._log_event(f"Anomalie détectée: {', '.join(anomalies)}")
            # Alerter l'utilisateur si notification configurée
            notify = cfg.get(CONF_NOTIFY_DEVICE)
            if notify and "alarme_non_armee" in anomalies:
                try:
                    self.hass.async_create_task(self._alerter_anomalie(notify, anomalies))
                except Exception:
                    pass

    async def _alerter_anomalie(self, notify_device: str, anomalies: list[str]) -> None:
        """Envoie une alerte si une anomalie est détectée."""
        msg = "⚠️ Anomalie SmartWAKE: " + ", ".join(anomalies)
        try:
            await self.hass.services.async_call(
                "notify", "send_message",
                {"entity_id": notify_device, "title": "⚠️ SmartWAKE Anomalie", "message": msg},
            )
        except Exception as exc:
            _LOGGER.error("Erreur alerte anomalie: %s", exc)

    def _setup_notification_actions(self) -> None:
        """Écoute les actions REVEIL_SNOOZE / REVEIL_STOP depuis l'app mobile."""
        entry_id = self.entry.entry_id

        @callback
        def _handle_notification_action(event):
            action = event.data.get("action")
            if action == "REVEIL_SNOOZE":
                _LOGGER.info("Action Snooze reçue pour '%s'", self.entry.title)
                self.hass.async_create_task(self.snooze())
            elif action == "REVEIL_STOP":
                _LOGGER.info("Action Stop reçue pour '%s'", self.entry.title)
                self.hass.async_create_task(self.stop())
            elif action and action.startswith("REVEIL_ACCEPTER_"):
                # Suggestion IA acceptée — valider et appliquer l'heure
                heure = action.replace("REVEIL_ACCEPTER_", "")
                import re
                m = re.match(r"^(\d{1,2}):(\d{2})$", heure)
                if not m or not (0 <= int(m.group(1)) < 24 and 0 <= int(m.group(2)) < 60):
                    _LOGGER.warning("Heure invalide reçue via notification: %s", heure)
                    return
                _LOGGER.info("Suggestion IA acceptée: %s", heure)
                self._log_event("Suggestion IA acceptée")
                self.hass.async_create_task(self.set_heure(heure))
            elif action == "REVEIL_REFUSER":
                _LOGGER.info("Suggestion IA refusée")
                self._log_event("Suggestion IA refusée")

        self.hass.bus.async_listen(
            "mobile_app_notification_action", _handle_notification_action
        )

        # Planifier la suggestion IA du soir (21:30) si activée
        if self.entry.data.get(CONF_AI_SUGGESTION_HEURE):
            self._setup_ai_suggestion()

    def _setup_ai_suggestion(self) -> None:
        """Planifie une suggestion d'heure IA chaque soir à 21:30."""
        unsub = async_track_time_change(
            self.hass,
            self._ai_suggestion_callback,
            hour=21, minute=30, second=0,
        )
        self._unsub_listeners.append(unsub)

    @callback
    def _ai_suggestion_callback(self, now: datetime) -> None:
        """Callback du soir — génère une suggestion d'heure IA."""
        if not self._actif:
            return
        self.hass.async_create_task(self._run_ai_suggestion())

    async def _run_ai_suggestion(self) -> None:
        """Génère et envoie une suggestion d'heure via IA + notification actionnable."""
        from .ai import suggest_wake_time
        cfg = self.entry.data
        current_time = cfg.get(CONF_HEURE, "07:00")
        suggestion = await suggest_wake_time(self.hass, cfg, current_time)
        if not suggestion or not suggestion.get("decaler"):
            return

        heure_proposee = suggestion.get("heure_proposee", "")
        raison = suggestion.get("raison", "")
        notify_device = cfg.get(CONF_NOTIFY_DEVICE, "")
        if not notify_device:
            return

        try:
            await self.hass.services.async_call(
                "notify", "send_message",
                {
                    "entity_id": notify_device,
                    "title": "⏰ Suggestion réveil",
                    "message": f"Demain : {heure_proposee} ? {raison}",
                    "data": {"actions": [
                        {"action": f"REVEIL_ACCEPTER_{heure_proposee}", "title": "Accepter"},
                        {"action": "REVEIL_REFUSER", "title": f"Garder {current_time}"},
                    ]},
                },
            )
            self._log_event("Suggestion IA envoyée")
        except Exception as exc:
            _LOGGER.error("Erreur envoi suggestion IA: %s", exc)

    async def async_shutdown(self) -> None:
        if self._cancel_trigger:
            self._cancel_trigger()
            self._cancel_trigger = None
        if self._cancel_prewake:
            self._cancel_prewake()
            self._cancel_prewake = None
        for task in (self._cancel_cycle, self._cancel_escalade):
            if task and not task.done():
                task.cancel()
        _LOGGER.info("Réveil '%s' arrêté", self.entry.title)

    def _notify(self) -> None:
        self.async_set_updated_data({
            "actif": self._actif,
            "statut": self._statut,
            "prochain": self._prochain,
            "snooze_count": self._snooze_count,
            "skip_prochain": self._skip_prochain,
        })

    def _log_event(self, message: str, domain: str = "smartwake") -> None:
        """Journalise un événement dans le logbook HA."""
        try:
            self.hass.bus.async_fire(
                "logbook_entry",
                {
                    "name": self.entry.title,
                    "message": message,
                    "domain": domain,
                    "entity_id": f"sensor.{self.entry.entry_id}_sensor_statut",
                },
            )
        except Exception as exc:
            _LOGGER.debug("Erreur logbook: %s", exc)

    def _fire_event(self, event_type: str, **kwargs) -> None:
        """Émet un événement sur le bus HA pour les automatisations externes.

        Events disponibles:
          - smartwake_triggered  (heure, jours, prochain)
          - smartwake_stopped     (raison: manual|snooze_max|mouvement_sdb)
          - smartwake_snoozed     (count, max)
          - smartwake_escalade    (level)
          - smartwake_prewake     (phase: chauffage|aube|cafe)
          - smartwake_skipped     (prochain_reveil)
          - smartwake_activated   (heure, prochain)
          - smartwake_deactivated ()
        """
        try:
            self.hass.bus.async_fire(event_type, {
                "name": self.entry.title,
                "entry_id": self.entry.entry_id,
                "entity_id": f"switch.{slugify(self.entry.title)}_actif",
                **kwargs,
            })
        except Exception as exc:
            _LOGGER.debug("Erreur fire event %s: %s", event_type, exc)

    def _increment_stat(self, key: str) -> None:
        """Incrémente un compteur de statistiques."""
        if not hasattr(self, "_stats") or self._stats is None:
            self._stats = {
                "total_declenchements": 0,
                "total_snoozes": 0,
                "total_stops": 0,
                "dernier_reveil": None,
                "heures_lever": [],
            }
        if key in self._stats:
            self._stats[key] = self._stats.get(key, 0) + 1
        self._notify()

    # ── Activation ──────────────────────────────────────────────

    async def set_actif(self, actif: bool) -> None:
        self._actif = actif
        if actif:
            self._snooze_count = 0
            self._statut = STATUT_IDLE
            self._planifier_trigger()
            self._log_event("Réveil activé")
            self._fire_event("smartwake_activated", heure=self.config.get(CONF_HEURE, "07:00"), prochain=self._prochain.isoformat() if self._prochain else None)
        else:
            self._statut = STATUT_INACTIF
            self._prochain = None
            self._nettoyer_triggers()
            self._reveil_en_cours = False
            self._log_event("Réveil désactivé")
            self._fire_event("smartwake_deactivated")
        self._notify()

    def _nettoyer_triggers(self) -> None:
        if self._cancel_trigger:
            self._cancel_trigger()
            self._cancel_trigger = None
        if self._cancel_prewake:
            self._cancel_prewake()
            self._cancel_prewake = None

    # ── Mise à jour config ─────────────────────────────────────

    async def set_heure(self, heure: str) -> None:
        new_data = {**self.entry.data, CONF_HEURE: heure}
        self.hass.config_entries.async_update_entry(self.entry, data=new_data)
        if self._actif:
            self._planifier_trigger()
        self._notify()

    async def set_jours(self, mode: str) -> None:
        new_data = {**self.entry.data, CONF_JOURS: mode}
        self.hass.config_entries.async_update_entry(self.entry, data=new_data)
        if self._actif:
            self._planifier_trigger()
        self._notify()

    async def set_config_value(self, key: str, value: Any) -> None:
        """Met à jour une clé de configuration numérique et replanifie."""
        new_data = {**self.entry.data, key: value}
        self.hass.config_entries.async_update_entry(self.entry, data=new_data)
        if self._actif:
            self._planifier_trigger()
        self._notify()

    async def set_skip(self, skip: bool) -> None:
        self._skip_prochain = skip
        self._notify()

    # ── Conditions de déclenchement ────────────────────────────

    def _sonne_aujourd_hui(self, now: datetime) -> bool:
        """Vérifie si le réveil doit sonner aujourd'hui."""
        cfg = self.entry.data
        if not self._actif:
            return False
        # Mode vacances : booléen OU entité (calendar/input_boolean/binary_sensor/person)
        if cfg.get(CONF_MODE_VACANCES, False):
            return False
        vac_entity = cfg.get(CONF_MODE_VACANCES_ENTITY)
        if vac_entity:
            state = self.hass.states.get(vac_entity)
            if state and state.state == "on":
                return False
        if self._skip_prochain:
            return False

        mode = cfg.get(CONF_JOURS, "semaine")
        jours_perso = cfg.get(CONF_JOURS_PERSO, [])
        jours = _jours_actifs(mode, jours_perso)
        if now.weekday() not in jours:
            return False

        # Jours fériés
        if cfg.get(CONF_IGNORER_FERIES, True) and cfg.get(CONF_WORKDAY_SENSOR):
            state = self.hass.states.get(cfg[CONF_WORKDAY_SENSOR])
            if state and state.state == "off":
                return False

        # Vacances scolaires
        if cfg.get(CONF_IGNORER_VACANCES_SCOLAIRE, False) and cfg.get(CONF_VACANCES_SCOLAIRES_CALENDAR):
            state = self.hass.states.get(cfg[CONF_VACANCES_SCOLAIRES_CALENDAR])
            if state and state.state == "on":
                return False

        # Présence
        presence = cfg.get(CONF_PRESENCE)
        if presence:
            state = self.hass.states.get(presence)
            if state and state.state not in ("home", "unknown", None):
                return False

        return True

    def _personne_au_lit(self) -> bool:
        """Vérifie Withings — vrai si quelqu'un est au lit."""
        cfg = self.entry.data
        for key in (CONF_WITHINGS_BED_1, CONF_WITHINGS_BED_2):
            entity = cfg.get(key)
            if entity:
                state = self.hass.states.get(entity)
                if state and state.state == "on":
                    return True
        return False

    # ── Planification ─────────────────────────────────────────

    def _calculer_prochain(self) -> None:
        cfg = self.entry.data
        mode_jours = cfg.get(CONF_JOURS, "semaine")
        jours_perso = cfg.get(CONF_JOURS_PERSO, [])
        jours = _jours_actifs(mode_jours, jours_perso)
        now = dt_util.now()

        # Heure par jour ou heure unique ?
        mode_heure = cfg.get(CONF_MODE_HEURE, "unique")
        heures_par_jour = {
            0: cfg.get(CONF_HEURE_LUNDI),
            1: cfg.get(CONF_HEURE_MARDI),
            2: cfg.get(CONF_HEURE_MERCREDI),
            3: cfg.get(CONF_HEURE_JEUDI),
            4: cfg.get(CONF_HEURE_VENDREDI),
            5: cfg.get(CONF_HEURE_SAMEDI),
            6: cfg.get(CONF_HEURE_DIMANCHE),
        }

        heure_defaut = _parse_heure(cfg.get(CONF_HEURE, "07:00"))

        for i in range(8):
            candidate_date = now + timedelta(days=i)
            jour_semaine = candidate_date.weekday()

            if jour_semaine not in jours:
                continue

            # Heure pour ce jour
            if mode_heure == "par_jour" and heures_par_jour.get(jour_semaine):
                heure = _parse_heure(heures_par_jour[jour_semaine])
            else:
                heure = heure_defaut

            # Heure adaptative via agenda ?
            heure_adapt = heure
            if cfg.get(CONF_ADAPTATIF_AGENDA, False) and cfg.get(CONF_AGENDA_ENTITY):
                heure_adapt = self._heure_adaptative_agenda(heure, now, jours) or heure

            # Phase de sommeil : fenêtre ±N min autour de l'heure
            if cfg.get(CONF_SOMMEIL_PHASE, False) and cfg.get(CONF_WITHINGS_BED_1):
                heure_adapt = self._heure_phase_sommeil(heure_adapt, cfg)

            candidate = candidate_date.replace(
                hour=heure_adapt.hour, minute=heure_adapt.minute, second=0, microsecond=0
            )
            if candidate > now:
                # Vérifier férié si applicable
                if cfg.get(CONF_IGNORER_FERIES, True) and cfg.get(CONF_WORKDAY_SENSOR):
                    self._prochain = candidate
                    if self._statut not in (STATUT_RINGING, STATUT_SNOOZED, STATUT_PREWAKE):
                        self._statut = STATUT_IDLE if self._actif else STATUT_INACTIF
                    return
                self._prochain = candidate
                if self._statut not in (STATUT_RINGING, STATUT_SNOOZED, STATUT_PREWAKE):
                    self._statut = STATUT_IDLE if self._actif else STATUT_INACTIF
                return

        self._prochain = None
        if self._statut not in (STATUT_RINGING, STATUT_SNOOZED, STATUT_PREWAKE):
            self._statut = STATUT_INACTIF

    def _heure_adaptative_agenda(self, heure_defaut: time, now: datetime, jours: set[int]) -> time | None:
        """Calcule l'heure de réveil basée sur le 1er RDV de l'agenda du prochain jour actif."""
        cfg = self.entry.data
        calendar = cfg.get(CONF_AGENDA_ENTITY)
        marge = cfg.get(CONF_AGENDA_MARGE_MIN, DEFAULT_AGENDA_MARGE_MIN)

        try:
            # Récupérer les événements du jour suivant actif
            for i in range(1, 8):
                demain = now + timedelta(days=i)
                if demain.weekday() not in jours:
                    continue
                debut_jour = demain.replace(hour=0, minute=0, second=0, microsecond=0)
                fin_jour = debut_jour + timedelta(days=1)
                events = self.hass.states.get(calendar)
                if events is None:
                    return None
                # Les calendar entities exposent les attributs start_time / end_time
                # du prochain événement
                start = events.attributes.get("start_time")
                if start:
                    from datetime import datetime as dt
                    debut_rdv = dt.fromisoformat(start)
                    reveil = debut_rdv - timedelta(minutes=marge)
                    if reveil.time() != heure_defaut:
                        _LOGGER.info(
                            "Réveil adaptatif: %s (RDV %s − %dmin)",
                            reveil.strftime("%H:%M"), start, marge,
                        )
                        self._log_event("Réveil adaptatif déclenché")
                    return reveil.time()
                break
        except Exception as exc:
            _LOGGER.error("Erreur agenda adaptatif: %s", exc)
        return None

    def _heure_phase_sommeil(self, heure_defaut: time, cfg: dict) -> time:
        """Ajuste l'heure dans une fenêtre ±N min selon la phase de sommeil Withings.

        Si le capteur Withings indique une phase de sommeil léger dans la fenêtre,
        on réveille à ce moment-là. Sinon, on garde l'heure par défaut.
        """
        fenetre = cfg.get(CONF_SOMMEIL_FENETRE_MIN, DEFAULT_SOMMEIL_FENETRE_MIN)
        # Withings expose parfois un attribut "sleep_state" ou similaire
        # Ici on vérifie juste l'état du capteur : si "on" = au lit, on garde l'heure
        # Une implémentation complète nécessiterait l'API Withings détaillée
        bed_1 = cfg.get(CONF_WITHINGS_BED_1)
        if not bed_1:
            return heure_defaut
        state = self.hass.states.get(bed_1)
        if state is None:
            return heure_defaut
        # Logique simplifiée : si le capteur indique "light" (sommeil léger) dans la fenêtre
        # on avance le réveil. Sinon heure par défaut.
        sleep_state = state.attributes.get("sleep_state", state.state)
        if sleep_state in ("light", "awake"):
            heure_avancee = (datetime.combine(datetime.today(), heure_defaut) - timedelta(minutes=fenetre)).time()
            _LOGGER.info("Phase sommeil léger détectée — réveil avancé à %s", heure_avancee)
            self._log_event("Phase sommeil léger — réveil avancé")
            return heure_avancee
        return heure_defaut

    def _planifier_trigger(self) -> None:
        """Programme les déclencheurs pour le pré-réveil et le réveil."""
        self._nettoyer_triggers()
        self._calculer_prochain()
        if self._prochain is None:
            return

        cfg = self.entry.data
        mode_heure = cfg.get(CONF_MODE_HEURE, "unique")

        # Collecter toutes les heures distinctes à déclencher
        heures_distinctes = set()
        if mode_heure == "par_jour":
            for key in (CONF_HEURE_LUNDI, CONF_HEURE_MARDI, CONF_HEURE_MERCREDI,
                        CONF_HEURE_JEUDI, CONF_HEURE_VENDREDI, CONF_HEURE_SAMEDI,
                        CONF_HEURE_DIMANCHE):
                h = cfg.get(key)
                if h:
                    try:
                        heures_distinctes.add(_parse_heure(h))
                    except (ValueError, IndexError):
                        pass
        if not heures_distinctes:
            heures_distinctes = {_parse_heure(cfg.get(CONF_HEURE, "07:00"))}

        # Trigger principal du réveil — un trigger par heure distincte
        triggers = []
        for heure in heures_distinctes:
            triggers.append(async_track_time_change(
                self.hass,
                self._trigger_callback,
                hour=heure.hour,
                minute=heure.minute,
                second=0,
            ))
        self._cancel_trigger = lambda: [t() for t in triggers] if triggers else None

        # Trigger pré-réveil
        prechauffe = self.entry.data.get(CONF_PRECHAUFFE_MIN, DEFAULT_PRECHAUFFE_MIN)
        aube = self.entry.data.get(CONF_AUBE_MIN, DEFAULT_AUBE_MIN)
        pre_delai = max(prechauffe, aube)

        if pre_delai > 0:
            heure_pre = (datetime.combine(datetime.today(), heure) - timedelta(minutes=pre_delai)).time()
            self._cancel_prewake = async_track_time_change(
                self.hass,
                self._trigger_prewake,
                hour=heure_pre.hour,
                minute=heure_pre.minute,
                second=0,
            )

        _LOGGER.info(
            "Réveil '%s' programmé à %s (pré-réveil à H-%dmin, prochain: %s)",
            self.entry.title, heure.strftime("%H:%M"), pre_delai, self._prochain,
        )

    # ── Callbacks triggers ─────────────────────────────────────

    @callback
    def _trigger_prewake(self, now: datetime) -> None:
        """Phase de pré-réveil : chauffage, aube, café."""
        if not self._sonne_aujourd_hui(now):
            return
        if self._personne_au_lit() is False and self.entry.data.get(CONF_WITHINGS_BED_1):
            _LOGGER.info("Pré-réveil annulé — personne au lit (Withings)")
            return

        self._statut = STATUT_PREWAKE
        self._fire_event("smartwake_prewake", phase="demarrage")
        self._notify()
        self.hass.async_create_task(self._executer_prewake())

    @callback
    def _trigger_callback(self, now: datetime) -> None:
        """Phase de réveil principal."""
        if self._reveil_en_cours:
            return
        if not self._sonne_aujourd_hui(now):
            return

        # Lever anticipé : si mouvement cuisine détecté récemment
        if self.entry.data.get(CONF_LEVER_ANTICIPE, False):
            cuisine = self.entry.data.get(CONF_MOUVEMENT_CUISINE)
            if cuisine:
                state = self.hass.states.get(cuisine)
                if state and state.state == "on":
                    _LOGGER.info("Réveil '%s' annulé — lever anticipé détecté", self.entry.title)
                    self._skip_prochain = True
                    self._notify()
                    return

        # Withings : si personne au lit
        if self.entry.data.get(CONF_WITHINGS_BED_1) and not self._personne_au_lit():
            _LOGGER.info("Réveil '%s' annulé — personne n'est au lit", self.entry.title)
            return

        self._cancel_cycle = self.hass.async_create_task(self._executer_cycle())

    # ── Phase pré-réveil ───────────────────────────────────────

    async def _executer_prewake(self) -> None:
        """Pré-chauffage, simulation d'aube, café, chauffe-eau."""
        cfg = self.entry.data
        _LOGGER.info("Pré-réveil démarré pour '%s'", self.entry.title)

        # Chauffage
        radiateur = cfg.get(CONF_RADIATEUR)
        if radiateur:
            try:
                await self.hass.services.async_call(
                    "climate", "set_preset_mode",
                    {"entity_id": radiateur, "preset_mode": "comfort"},
                )
                _LOGGER.info("Radiateur confort: %s", radiateur)
            except Exception as exc:
                _LOGGER.error("Erreur radiateur: %s", exc)

        # Chauffe-eau / sèche-serviettes
        chauffe_eau = cfg.get(CONF_CHAUFFE_EAU)
        if chauffe_eau:
            try:
                await self.hass.services.async_call("switch", "turn_on", {"entity_id": chauffe_eau})
            except Exception as exc:
                _LOGGER.error("Erreur chauffe-eau: %s", exc)

        # Simulation d'aube (lumière progressive)
        if cfg.get(CONF_LUMIERE_ACTIVEE) and cfg.get(CONF_LUMIERE):
            await self._cycle_lumiere_progressive()

        # Café / bouilloire
        cafetiere = cfg.get(CONF_CAFETIERE)
        cafetiere_min = cfg.get(CONF_CAFETIERE_MIN, DEFAULT_CAFETIERE_MIN)
        if cafetiere and cafetiere_min > 0:
            await asyncio.sleep(max(0, cafetiere_min * 60 - DEFAULT_AUBE_MIN * 60))
            try:
                await self.hass.services.async_call("switch", "turn_on", {"entity_id": cafetiere})
                _LOGGER.info("Cafetière allumée: %s", cafetiere)
            except Exception as exc:
                _LOGGER.error("Erreur cafetière: %s", exc)

    # ── Phase réveil ────────────────────────────────────────────

    async def _executer_cycle(self) -> None:
        """Cycle de réveil complet avec contrôle d'erreurs."""
        cfg = self.entry.data
        erreurs = []

        self._reveil_en_cours = True
        self._snooze_count = 0
        self._statut = STATUT_RINGING
        self._log_event("Réveil déclenché")
        self._fire_event("smartwake_triggered", heure=cfg.get(CONF_HEURE, "07:00"), prochain=self._prochain.isoformat() if self._prochain else None)
        self._increment_stat("total_declenchements")
        self._notify()

        # Musique + volume progressif (avec IA adaptative si activée)
        if cfg.get(CONF_MUSIQUE_ACTIVEE) and cfg.get(CONF_MEDIA_PLAYER):
            try:
                await self._demarrer_musique()
            except Exception as exc:
                erreurs.append("musique")
                _LOGGER.error("Erreur critique musique: %s", exc)

        # Volets si soleil levé
        if cfg.get(CONF_VOLETS):
            try:
                await self._ouvrir_volets()
            except Exception as exc:
                erreurs.append("volets")
                _LOGGER.error("Erreur critique volets: %s", exc)

        # Lumière si pas déjà allumée par aube
        if cfg.get(CONF_LUMIERE_ACTIVEE) and cfg.get(CONF_LUMIERE):
            if self._statut != STATUT_PREWAKE:
                try:
                    await self._cycle_lumiere_progressive()
                except Exception as exc:
                    erreurs.append("lumière")
                    _LOGGER.error("Erreur critique lumière: %s", exc)

        # Notification actionnable
        if cfg.get(CONF_NOTIFICATION_ACTIVEE):
            try:
                await self._envoyer_notification()
            except Exception as exc:
                erreurs.append("notification")
                _LOGGER.error("Erreur notification: %s", exc)

        # Alerte si tout a échoué
        if erreurs and not cfg.get(CONF_MUSIQUE_ACTIVEE):
            self._log_event(f"Sonnerie échouée: {', '.join(erreurs)}")
            # Notifier l'utilisateur de l'échec
            notify = cfg.get(CONF_NOTIFY_DEVICE)
            if notify:
                try:
                    await self.hass.services.async_call(
                        "notify", "send_message",
                        {"entity_id": notify, "title": "⚠️ SmartWAKE", "message": "Le réveil a échoué — vérifiez la configuration"},
                    )
                except Exception:
                    pass

        # Escalade programmée
        escalade_min = cfg.get(CONF_ESCALADE_MIN, DEFAULT_ESCALADE_MIN)
        self._cancel_escalade = self.hass.async_create_task(self._escalade(escalade_min))

        # Arrêt par mouvement salle de bain
        if cfg.get(CONF_MOUVEMENT_STOP, False) and cfg.get(CONF_MOUVEMENT_SDB):
            self._setup_mouvement_stop()

        # Scène matin (éclairage cuisine + couloir + autres pièces)
        if cfg.get(CONF_SCENES_MATIN, False):
            await self._activer_scene_matin()

        # AI task personnalisée (au déclenchement)
        if cfg.get(CONF_AI_CUSTOM_ENABLED) or cfg.get(CONF_AI_CUSTOM_TASKS):
            self.hass.async_create_task(self._run_custom_ai("on_wake"))

        # Escalade intelligente (progressive au lieu de tout à 100%)
        if cfg.get(CONF_ESCALADE_INTELLIGENTE, False):
            self._cancel_escalade = self.hass.async_create_task(self._escalade_intelligente())
        else:
            escalade_min = cfg.get(CONF_ESCALADE_MIN, DEFAULT_ESCALADE_MIN)
            self._cancel_escalade = self.hass.async_create_task(self._escalade(escalade_min))

    async def _demarrer_musique(self) -> None:
        """Démarre la musique avec volume progressif. Retry + fallback TTS si échec."""
        cfg = self.entry.data
        media = cfg[CONF_MEDIA_PLAYER]
        playlist_raw = cfg.get(CONF_PLAYLIST, "")
        vol_initial = cfg.get(CONF_VOLUME_INITIAL, DEFAULT_VOLUME_INITIAL)
        vol_final = cfg.get(CONF_VOLUME_FINAL, DEFAULT_VOLUME_FINAL)
        duree = cfg.get(CONF_VOLUME_DUREE, DEFAULT_VOLUME_DUREE)

        # MediaSelector retourne un dict {content_id, content_type} ou un string
        content_id = ""
        content_type = "music"
        if isinstance(playlist_raw, dict):
            content_id = playlist_raw.get("content_id", "")
            content_type = playlist_raw.get("content_type", "music")
        elif isinstance(playlist_raw, str):
            content_id = playlist_raw
        elif playlist_raw and hasattr(playlist_raw, "get"):
            content_id = playlist_raw.get("content_id", "")
            content_type = playlist_raw.get("content_type", "music")

        # Musique adaptative IA : choisir la playlist selon le contexte
        if cfg.get(CONF_AI_MUSIQUE_ADAPT):
            from .ai import choose_adaptive_music
            playlist_options = [content_id, "France Inter", "Radio Nova", "Jazz doux"]
            chosen = await choose_adaptive_music(self.hass, cfg, playlist_options)
            if chosen:
                content_id = chosen
                content_type = "music"
                self._log_event("Musique adaptative IA")

        musique_ok = False
        for attempt in range(3):
            try:
                await self.hass.services.async_call(
                    "media_player", "volume_set",
                    {"entity_id": media, "volume_level": vol_initial},
                )
                await self.hass.services.async_call(
                    "media_player", "play_media",
                    {"entity_id": media, "media_content_id": content_id, "media_content_type": content_type},
                )
                musique_ok = True
                _LOGGER.info("Musique lancée sur %s (tentative %d)", media, attempt + 1)
                break
            except Exception as exc:
                _LOGGER.warning("Tentative musique %d/3 échouée: %s", attempt + 1, exc)
                if attempt < 2:
                    await asyncio.sleep(5)

        if not musique_ok:
            _LOGGER.error("Musique échouée après 3 tentatives — fallback TTS")
            self._log_event("Musique échouée — fallback")
            # Fallback : notification + TTS d'alarme si configuré
            if cfg.get(CONF_TTS_ENTITY):
                try:
                    await self.hass.services.async_call(
                        "tts", "speak",
                        {"entity_id": cfg[CONF_TTS_ENTITY], "message": "Il est l'heure de se lever !"},
                    )
                except Exception as exc:
                    _LOGGER.error("Fallback TTS échoué: %s", exc)
            return

        # Montée progressive du volume
        steps = max(duree, 1)
        increment = (vol_final - vol_initial) / steps
        for i in range(steps):
            await asyncio.sleep(60)
            vol = min(vol_initial + increment * (i + 1), vol_final)
            try:
                await self.hass.services.async_call(
                    "media_player", "volume_set",
                    {"entity_id": media, "volume_level": vol},
                )
            except Exception as exc:
                _LOGGER.error("Erreur volume musique: %s", exc)

    async def _ouvrir_volets(self) -> None:
        """Ouvre les volets si le soleil est levé."""
        cfg = self.entry.data
        volets = cfg[CONF_VOLETS]
        soleil_seulement = cfg.get(CONF_VOLETS_SOLEIL, True)

        if soleil_seulement:
            sun = self.hass.states.get("sun.sun")
            if sun and sun.state != "above_horizon":
                _LOGGER.info("Volets fermés — soleil pas encore levé")
                # Fallback : programmer l'ouverture au lever du soleil
                self.hass.async_create_task(self._ouvrir_volets_au_lever(volets))
                return

        for attempt in range(2):
            try:
                position = cfg.get(CONF_VOLETS_POSITION, 100)
                if position >= 100:
                    await self.hass.services.async_call("cover", "open_cover", {"entity_id": volets})
                else:
                    await self.hass.services.async_call("cover", "set_cover_position", {"entity_id": volets, "position": position})
                _LOGGER.info("Volets ouverts (%d%%): %s", position, volets)
                return
            except Exception as exc:
                _LOGGER.warning("Tentative volets %d/2 échouée: %s", attempt + 1, exc)
                if attempt < 1:
                    await asyncio.sleep(3)
        _LOGGER.error("Ouverture volets échouée après 2 tentatives")

    async def _ouvrir_volets_au_lever(self, volets: str) -> None:
        """Ouvre les volets au lever du soleil (fallback)."""
        from homeassistant.helpers.event import async_track_state_change
        opened = False

        def _try_open(*args):
            nonlocal opened
            if opened:
                return
            sun = self.hass.states.get("sun.sun")
            if sun and sun.state == "above_horizon":
                opened = True
                self.hass.async_create_task(self._open_volets_now(volets))

        unsub = async_track_state_change(self.hass, "sun.sun", _try_open)
        # Timeout de 2h max
        await asyncio.sleep(2 * 3600)
        unsub()

    async def _open_volets_now(self, volets: str) -> None:
        try:
            await self.hass.services.async_call("cover", "open_cover", {"entity_id": volets})
            _LOGGER.info("Volets ouverts au lever du soleil: %s", volets)
        except Exception as exc:
            _LOGGER.error("Erreur ouverture volets au lever: %s", exc)

    async def _activer_scene_matin(self) -> None:
        """Active la scène matin : éclairage cuisine + couloir + autres pièces."""
        cfg = self.entry.data
        entities = cfg.get(CONF_SCENE_MATIN_ENTITIES, [])
        if not entities:
            return
        for entity in entities:
            try:
                domain = entity.split(".")[0]
                if domain == "light":
                    await self.hass.services.async_call(
                        "light", "turn_on",
                        {"entity_id": entity, "brightness_pct": 80, "transition": 30},
                    )
                elif domain == "switch":
                    await self.hass.services.async_call("switch", "turn_on", {"entity_id": entity})
                elif domain == "scene":
                    await self.hass.services.async_call("scene", "turn_on", {"entity_id": entity})
                _LOGGER.info("Scène matin: %s activé", entity)
            except Exception as exc:
                _LOGGER.error("Erreur scène matin %s: %s", entity, exc)

    async def _escalade_intelligente(self) -> None:
        """Escalade progressive : 3 niveaux (doux → moyen → max)."""
        cfg = self.entry.data
        # Niveau 1 (5 min) : volume 60%
        await asyncio.sleep(5 * 60)
        if not self._reveil_en_cours:
            return
        await self._escalade_niveau(0.6, 60, "doux")
        # Niveau 2 (10 min) : volume 80%
        await asyncio.sleep(5 * 60)
        if not self._reveil_en_cours:
            return
        await self._escalade_niveau(0.8, 80, "moyen")
        # Niveau 3 (15 min) : volume 100% + toutes lumières
        await asyncio.sleep(5 * 60)
        if not self._reveil_en_cours:
            return
        await self._escalade_niveau(1.0, 100, "max")
        self._log_event("Escalade intelligente : niveau max")
        self._fire_event("smartwake_escalade", level="max")

    async def _escalade_niveau(self, volume: float, brightness_pct: int, niveau: str) -> None:
        """Applique un niveau d'escalade."""
        cfg = self.entry.data
        _LOGGER.info("Escalade niveau %s pour '%s'", niveau, self.entry.title)
        self._fire_event("smartwake_escalade", level=niveau)
        if cfg.get(CONF_MUSIQUE_ACTIVEE) and cfg.get(CONF_MEDIA_PLAYER):
            try:
                await self.hass.services.async_call(
                    "media_player", "volume_set",
                    {"entity_id": cfg[CONF_MEDIA_PLAYER], "volume_level": volume},
                )
            except Exception as exc:
                _LOGGER.error("Erreur escalade volume: %s", exc)
        if cfg.get(CONF_LUMIERE_ACTIVEE) and cfg.get(CONF_LUMIERE):
            try:
                await self.hass.services.async_call(
                    "light", "turn_on",
                    {"entity_id": cfg[CONF_LUMIERE], "brightness_pct": brightness_pct},
                )
            except Exception as exc:
                _LOGGER.error("Erreur escalade lumière: %s", exc)

    async def _cycle_lumiere_progressive(self) -> None:
        """Augmentation progressive de la luminosité."""
        cfg = self.entry.data
        lumiere = cfg[CONF_LUMIERE]
        brightness_max = cfg.get(CONF_BRIGHTNESS_MAX, DEFAULT_BRIGHTNESS_MAX)
        duree = cfg.get(CONF_DUREE_PROGRESSIVE, DEFAULT_DUREE_PROGRESSIVE)
        steps = min(20, brightness_max)
        intervalle = (duree * 60) / steps

        try:
            await self.hass.services.async_call(
                "light", "turn_on",
                {"entity_id": lumiere, "brightness_step_pct": 1},
            )
            for _ in range(steps - 1):
                await asyncio.sleep(intervalle)
                etat = self.hass.states.get(lumiere)
                if etat is None or etat.state != "on":
                    break
                brightness = etat.attributes.get("brightness", 0)
                if brightness >= brightness_max:
                    break
                await self.hass.services.async_call(
                    "light", "turn_on",
                    {"entity_id": lumiere, "brightness_step_pct": 1},
                )
            _LOGGER.info("Lumière progressive terminée pour '%s'", self.entry.title)
        except Exception as exc:
            _LOGGER.error("Erreur lumière: %s", exc)

    async def _envoyer_notification(self) -> None:
        """Notification actionnable avec boutons Snooze / Stop."""
        cfg = self.entry.data
        device = cfg.get(CONF_NOTIFY_DEVICE)
        if not device:
            return
        titre = cfg.get(CONF_NOTIF_TITRE, DEFAULT_NOTIF_TITRE)
        message = cfg.get(CONF_NOTIF_MESSAGE, DEFAULT_NOTIF_MESSAGE)
        try:
            data = {"title": titre, "message": message, "data": {"actions": [
                {"action": "REVEIL_SNOOZE", "title": "Snooze"},
                {"action": "REVEIL_STOP", "title": "Stop"},
            ]}}
            await self.hass.services.async_call("notify", "send_message", {"entity_id": device, **data})
            _LOGGER.info("Notification envoyée pour '%s'", self.entry.title)
        except Exception as exc:
            _LOGGER.error("Erreur notification: %s", exc)

    async def _escalade(self, delai_min: int) -> None:
        """Escalade : volume max + toutes lumières si pas de stop."""
        await asyncio.sleep(delai_min * 60)
        if not self._reveil_en_cours:
            return

        cfg = self.entry.data
        _LOGGER.info("Escalade déclenchée pour '%s'", self.entry.title)
        self._log_event("Escalade : volume max + lumières 100%")
        self._fire_event("smartwake_escalade", level="max")

        # Volume max
        if cfg.get(CONF_MUSIQUE_ACTIVEE) and cfg.get(CONF_MEDIA_PLAYER):
            try:
                await self.hass.services.async_call(
                    "media_player", "volume_set",
                    {"entity_id": cfg[CONF_MEDIA_PLAYER], "volume_level": 1.0},
                )
            except Exception as exc:
                _LOGGER.error("Erreur escalade volume: %s", exc)

        # Toutes lumières à 100%
        if cfg.get(CONF_LUMIERE_ACTIVEE) and cfg.get(CONF_LUMIERE):
            try:
                await self.hass.services.async_call(
                    "light", "turn_on",
                    {"entity_id": cfg[CONF_LUMIERE], "brightness_pct": 100},
                )
            except Exception as exc:
                _LOGGER.error("Erreur escalade lumière: %s", exc)

    def _setup_mouvement_stop(self) -> None:
        """Configure l'arrêt par détection de mouvement salle de bain."""
        sdb = self.entry.data.get(CONF_MOUVEMENT_SDB)
        if not sdb:
            return

        @callback
        def _on_mouvement(event):
            if self._reveil_en_cours:
                _LOGGER.info("Mouvement SdB détecté — arrêt du réveil")
                self.hass.async_create_task(self.stop())

        self.hass.bus.async_listen(f"state_changed.{sdb}", _on_mouvement)

    # ── Snooze / Stop / Skip ────────────────────────────────────

    async def snooze(self) -> None:
        if not self._reveil_en_cours:
            return
        max_snooze = self.entry.data.get(CONF_SNOOZE_MAX, DEFAULT_SNOOZE_MAX)
        if self._snooze_count >= max_snooze:
            _LOGGER.info("Snooze max atteint pour '%s'", self.entry.title)
            return

        self._snooze_count += 1
        self._statut = STATUT_SNOOZED
        self._log_event(f"Snooze ({self._snooze_count}/{max_snooze})")
        self._fire_event("smartwake_snoozed", count=self._snooze_count, max=max_snooze)
        self._increment_stat("total_snoozes")
        self._notify()

        cfg = self.entry.data
        duree = cfg.get(CONF_SNOOZE_DUREE, DEFAULT_SNOOZE_DUREE)

        if cfg.get(CONF_MUSIQUE_ACTIVEE) and cfg.get(CONF_MEDIA_PLAYER):
            try:
                await self.hass.services.async_call(
                    "media_player", "media_pause",
                    {"entity_id": cfg[CONF_MEDIA_PLAYER]},
                )
            except Exception as exc:
                _LOGGER.error("Erreur pause snooze: %s", exc)

        if cfg.get(CONF_LUMIERE_ACTIVEE) and cfg.get(CONF_LUMIERE):
            try:
                await self.hass.services.async_call(
                    "light", "turn_off", {"entity_id": cfg[CONF_LUMIERE]}
                )
            except Exception as exc:
                _LOGGER.error("Erreur extinction snooze: %s", exc)

        await asyncio.sleep(duree * 60)

        if not self._reveil_en_cours:
            return
        self._statut = STATUT_RINGING
        self._notify()

        if cfg.get(CONF_MUSIQUE_ACTIVEE) and cfg.get(CONF_MEDIA_PLAYER):
            try:
                await self.hass.services.async_call(
                    "media_player", "media_play",
                    {"entity_id": cfg[CONF_MEDIA_PLAYER]},
                )
            except Exception as exc:
                _LOGGER.error("Erreur reprise snooze: %s", exc)

    async def stop(self, raison: str = "manual") -> None:
        """Arrête le cycle de réveil."""
        if not self._reveil_en_cours:
            return

        for task in (self._cancel_cycle, self._cancel_escalade):
            if task and not task.done():
                task.cancel()
        self._cancel_cycle = None
        self._cancel_escalade = None

        cfg = self.entry.data
        if cfg.get(CONF_MUSIQUE_ACTIVEE) and cfg.get(CONF_MEDIA_PLAYER):
            try:
                await self.hass.services.async_call(
                    "media_player", "media_stop",
                    {"entity_id": cfg[CONF_MEDIA_PLAYER]},
                )
            except Exception as exc:
                _LOGGER.error("Erreur stop musique: %s", exc)

        if cfg.get(CONF_LUMIERE_ACTIVEE) and cfg.get(CONF_LUMIERE):
            try:
                await self.hass.services.async_call(
                    "light", "turn_off", {"entity_id": cfg[CONF_LUMIERE]}
                )
            except Exception as exc:
                _LOGGER.error("Erreur extinction: %s", exc)

        # Briefing : IA si activée, sinon TTS basique
        briefing_msg = None
        if cfg.get(CONF_AI_BRIEFING):
            from .ai import generate_briefing
            briefing_msg = await generate_briefing(self.hass, cfg, self.entry.title)

        if briefing_msg and cfg.get(CONF_TTS_ENTITY):
            await self._tts_speak(briefing_msg)
        elif cfg.get(CONF_TTS_ACTIVEE) and cfg.get(CONF_TTS_ENTITY):
            await self._tts_briefing()

        # Vérif lever par IA (caméra) si activée
        if cfg.get(CONF_AI_VERIF_LEVER):
            self.hass.async_create_task(self._verif_lever_ia())

        # AI task personnalisée (au stop)
        if cfg.get(CONF_AI_CUSTOM_ENABLED) or cfg.get(CONF_AI_CUSTOM_TASKS):
            self.hass.async_create_task(self._run_custom_ai("on_stop"))

        self._reveil_en_cours = False
        self._skip_prochain = False
        self._statut = STATUT_DONE
        self._calculer_prochain()
        self._log_event("Réveil arrêté")
        self._fire_event("smartwake_stopped", raison=raison)
        self._increment_stat("total_stops")
        if hasattr(self, "_stats") and self._stats is not None:
            self._stats["dernier_reveil"] = datetime.now().isoformat()
        # Enregistrer le lever réel pour l'apprentissage
        if self._learning is not None:
            try:
                heure_pgm = self.config.get(CONF_HEURE, "07:00")
                await self._learning.record_lever(heure_pgm, datetime.now(), self._snooze_count)
            except Exception as exc:
                _LOGGER.debug("Erreur enregistrement learning: %s", exc)
        self._notify()
        _LOGGER.info("Réveil '%s' arrêté", self.entry.title)

    async def _tts_briefing(self) -> None:
        """Briefing vocal basique (fallback) : utilise le message configuré + météo."""
        cfg = self.entry.data
        tts_entity = cfg[CONF_TTS_ENTITY]
        try:
            tts_msg = cfg.get(CONF_TTS_MESSAGE, DEFAULT_TTS_MESSAGE)
            meteo = self.hass.states.get(cfg.get(CONF_WEATHER_ENTITY, "weather.home"))
            meteo_str = ""
            if meteo:
                meteo_str = f"Météo: {meteo.state}, {meteo.attributes.get('temperature', '?')}°C. "
            message = f"{tts_msg} {meteo_str}"
            await self._tts_speak(message)
        except Exception as exc:
            _LOGGER.error("Erreur TTS: %s", exc)

    async def _tts_speak(self, message: str) -> None:
        """Parle via TTS."""
        cfg = self.entry.data
        tts_entity = cfg[CONF_TTS_ENTITY]
        try:
            await self.hass.services.async_call(
                "tts", "speak",
                {"entity_id": tts_entity, "message": message},
            )
            _LOGGER.info("TTS envoyé: %s...", message[:50])
        except Exception as exc:
            _LOGGER.error("Erreur TTS: %s", exc)

    async def _verif_lever_ia(self) -> None:
        """Vérifie 10 min après le Stop si la personne est encore au lit (caméra+IA)."""
        await asyncio.sleep(10 * 60)
        if self._reveil_en_cours:
            return  # pas encore stoppé définitivement
        from .ai import verify_person_in_bed
        encore_au_lit = await verify_person_in_bed(self.hass, self.entry.data)
        if encore_au_lit:
            _LOGGER.info("Vérif IA: personne encore au lit — escalade")
            self._log_event("Vérif IA: personne encore au lit — escalade")
            await self._escalade(0)  # escalade immédiate

    async def _run_custom_ai(self, trigger: str) -> None:
        """Exécute les AI tasks personnalisées et notifie les résultats."""
        from .ai import run_custom_ai_task
        cfg = self.entry.data
        results = await run_custom_ai_task(self.hass, cfg, trigger)
        if not results:
            return
        _LOGGER.info("AI tasks custom (%s): %d résultat(s)", trigger, len(results))
        self._log_event(f"AI custom ({trigger}): {len(results)} tâche(s) exécutée(s)")
        # Notifier chaque résultat
        notify = cfg.get(CONF_NOTIFY_DEVICE)
        for msg in results:
            if notify:
                try:
                    await self.hass.services.async_call(
                        "notify", "send_message",
                        {"entity_id": notify, "title": "🤖 SmartWAKE IA", "message": msg},
                    )
                except Exception as exc:
                    _LOGGER.error("Erreur notification AI custom: %s", exc)

    async def sauter_prochain(self) -> None:
        """Saute le prochain réveil sans toucher la planification."""
        self._skip_prochain = True
        self._notify()
        _LOGGER.info("Prochain réveil sauté pour '%s'", self.entry.title)

    async def reset(self) -> None:
        """Remet à zéro l'état (watchdog nocturne)."""
        self._snooze_count = 0
        self._skip_prochain = False
        self._reveil_en_cours = False
        self._statut = STATUT_IDLE if self._actif else STATUT_INACTIF
        self._calculer_prochain()
        self._notify()
        _LOGGER.info("Reset du réveil '%s'", self.entry.title)

    async def declencher_manuel(self) -> None:
        """Déclenche manuellement le cycle de réveil."""
        if self._reveil_en_cours:
            return
        self._cancel_cycle = self.hass.async_create_task(self._executer_cycle())

    async def bilan_hebdo_ia(self) -> None:
        """Génère et envoie un bilan de sommeil hebdomadaire via IA."""
        from .ai import generate_weekly_report
        cfg = self.entry.data
        if not cfg.get("ai_bilan_hebdo", False):
            return
        bilan = await generate_weekly_report(
            self.hass, cfg, self._snooze_count, "historique non disponible"
        )
        if bilan:
            notify_device = cfg.get(CONF_NOTIFY_DEVICE, "")
            if notify_device:
                try:
                    await self.hass.services.async_call(
                        "notify", "send_message",
                        {"entity_id": notify_device, "title": "🛏️ Bilan sommeil", "message": bilan},
                    )
                    self._log_event("Bilan hebdo IA envoyé")
                except Exception as exc:
                    _LOGGER.error("Erreur envoi bilan hebdo: %s", exc)