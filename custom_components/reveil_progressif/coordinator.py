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
    CONF_ESCALADE_MIN,
    CONF_HEURE,
    CONF_IGNORER_FERIES,
    CONF_IGNORER_VACANCES_SCOLAIRE,
    CONF_VACANCES_SCOLAIRES_CALENDAR,
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
    CONF_SKIP_PROCHAIN,
    CONF_SNOOZE_DUREE,
    CONF_SNOOZE_MAX,
    CONF_TTS_ACTIVEE,
    CONF_TTS_ENTITY,
    CONF_VOLUME_DUREE,
    CONF_VOLUME_FINAL,
    CONF_VOLUME_INITIAL,
    CONF_VOLETS,
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
    DEFAULT_PRECHAUFFE_MIN,
    DEFAULT_SNOOZE_DUREE,
    DEFAULT_SNOOZE_MAX,
    DEFAULT_VOLUME_DUREE,
    DEFAULT_VOLUME_FINAL,
    DEFAULT_VOLUME_INITIAL,
    JOURS_NUM,
    JOURS_OPTIONS,
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
    if mode == "personnalise" and jours_perso:
        return {JOURS_NUM[j] for j in jours_perso if j in JOURS_NUM}
    return set(range(7))


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
            name=f"reveil_progressif_{entry.entry_id}",
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
        self._calculer_prochain()
        await super().async_config_entry_first_refresh()

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

    # ── Activation ──────────────────────────────────────────────

    async def set_actif(self, actif: bool) -> None:
        self._actif = actif
        if actif:
            self._snooze_count = 0
            self._statut = STATUT_IDLE
            self._planifier_trigger()
        else:
            self._statut = STATUT_INACTIF
            self._prochain = None
            self._nettoyer_triggers()
            self._reveil_en_cours = False
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

    async def set_skip(self, skip: bool) -> None:
        self._skip_prochain = skip
        self._notify()

    # ── Conditions de déclenchement ────────────────────────────

    def _sonne_aujourd_hui(self, now: datetime) -> bool:
        """Vérifie si le réveil doit sonner aujourd'hui."""
        cfg = self.entry.data
        if not self._actif:
            return False
        if cfg.get(CONF_MODE_VACANCES, False):
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
        heure = _parse_heure(cfg.get(CONF_HEURE, "07:00"))
        mode = cfg.get(CONF_JOURS, "semaine")
        jours_perso = cfg.get(CONF_JOURS_PERSO, [])
        jours = _jours_actifs(mode, jours_perso)
        now = dt_util.now()

        for i in range(8):
            candidate = now + timedelta(days=i)
            candidate = candidate.replace(
                hour=heure.hour, minute=heure.minute, second=0, microsecond=0
            )
            if candidate.weekday() in jours and candidate > now:
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

    def _planifier_trigger(self) -> None:
        """Programme les déclencheurs pour le pré-réveil et le réveil."""
        self._nettoyer_triggers()
        self._calculer_prochain()
        if self._prochain is None:
            return

        heure = _parse_heure(self.entry.data.get(CONF_HEURE, "07:00"))

        # Trigger principal du réveil (chaque jour à l'heure, filtrage dans le callback)
        self._cancel_trigger = async_track_time_change(
            self.hass,
            self._trigger_callback,
            hour=heure.hour,
            minute=heure.minute,
            second=0,
        )

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
        """Cycle de réveil complet."""
        self._reveil_en_cours = True
        self._snooze_count = 0
        self._statut = STATUT_RINGING
        self._notify()

        cfg = self.entry.data

        # Musique + volume progressif
        if cfg.get(CONF_MUSIQUE_ACTIVEE) and cfg.get(CONF_MEDIA_PLAYER):
            await self._demarrer_musique()

        # Volets si soleil levé
        if cfg.get(CONF_VOLETS):
            await self._ouvrir_volets()

        # Lumière si pas déjà allumée par aube
        if cfg.get(CONF_LUMIERE_ACTIVEE) and cfg.get(CONF_LUMIERE):
            if self._statut != STATUT_PREWAKE:
                await self._cycle_lumiere_progressive()

        # Notification actionnable
        if cfg.get(CONF_NOTIFICATION_ACTIVEE):
            await self._envoyer_notification()

        # Escalade programmée
        escalade_min = cfg.get(CONF_ESCALADE_MIN, DEFAULT_ESCALADE_MIN)
        self._cancel_escalade = self.hass.async_create_task(self._escalade(escalade_min))

        # Arrêt par mouvement salle de bain
        if cfg.get(CONF_MOUVEMENT_STOP, False) and cfg.get(CONF_MOUVEMENT_SDB):
            self._setup_mouvement_stop()

    async def _demarrer_musique(self) -> None:
        """Démarre la musique avec volume progressif."""
        cfg = self.entry.data
        media = cfg[CONF_MEDIA_PLAYER]
        playlist = cfg.get(CONF_PLAYLIST, "")
        vol_initial = cfg.get(CONF_VOLUME_INITIAL, DEFAULT_VOLUME_INITIAL)
        vol_final = cfg.get(CONF_VOLUME_FINAL, DEFAULT_VOLUME_FINAL)
        duree = cfg.get(CONF_VOLUME_DUREE, DEFAULT_VOLUME_DUREE)

        try:
            await self.hass.services.async_call(
                "media_player", "volume_set",
                {"entity_id": media, "volume_level": vol_initial},
            )
            await self.hass.services.async_call(
                "media_player", "play_media",
                {"entity_id": media, "media_content_id": playlist, "media_content_type": "favorite_item_id"},
            )
            _LOGGER.info("Musique lancée sur %s", media)

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
        except Exception as exc:
            _LOGGER.error("Erreur démarrage musique: %s", exc)

    async def _ouvrir_volets(self) -> None:
        """Ouvre les volets si le soleil est levé."""
        cfg = self.entry.data
        volets = cfg[CONF_VOLETS]
        soleil_seulement = cfg.get(CONF_VOLETS_SOLEIL, True)

        if soleil_seulement:
            sun = self.hass.states.get("sun.sun")
            if sun and sun.state != "above_horizon":
                _LOGGER.info("Volets fermés — soleil pas encore levé")
                return

        try:
            await self.hass.services.async_call("cover", "open_cover", {"entity_id": volets})
            _LOGGER.info("Volets ouverts: %s", volets)
        except Exception as exc:
            _LOGGER.error("Erreur volets: %s", exc)

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

    async def stop(self) -> None:
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

        # TTS briefing
        if cfg.get(CONF_TTS_ACTIVEE) and cfg.get(CONF_TTS_ENTITY):
            await self._tts_briefing()

        self._reveil_en_cours = False
        self._skip_prochain = False
        self._statut = STATUT_DONE
        self._calculer_prochain()
        self._notify()
        _LOGGER.info("Réveil '%s' arrêté", self.entry.title)

    async def _tts_briefing(self) -> None:
        """Briefing vocal : météo, agenda."""
        cfg = self.entry.data
        tts_entity = cfg[CONF_TTS_ENTITY]
        try:
            meteo = self.hass.states.get("weather.home")
            meteo_str = ""
            if meteo:
                meteo_str = f"Météo: {meteo.state}, {meteo.attributes.get('temperature', '?')}°C. "
            message = f"Bonjour. {meteo_str}Bonne journée !"
            await self.hass.services.async_call(
                "tts", "speak",
                {"entity_id": tts_entity, "message": message},
            )
            _LOGGER.info("TTS briefing envoyé")
        except Exception as exc:
            _LOGGER.error("Erreur TTS: %s", exc)

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