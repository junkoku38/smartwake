"""Config flow multi-étapes pour l'intégration SmartWAKE."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector

from .const import (
    CONF_AUBE_MIN,
    CONF_BRIGHTNESS_MAX,
    CONF_CAFETIERE,
    CONF_CAFETIERE_MIN,
    CONF_CHAUFFE_EAU,
    CONF_DUREE_PROGRESSIVE,
    CONF_ESCALADE_MIN,
    CONF_HEURE,
    CONF_ADAPTATIF_AGENDA,
    CONF_AGENDA_ENTITY,
    CONF_AGENDA_MARGE_MIN,
    CONF_AI_BILAN_HEBDO,
    CONF_AI_BRIEFING,
    CONF_AI_CAMERA_VERIF,
    CONF_AI_MUSIQUE_ADAPT,
    CONF_AI_SUGGESTION_HEURE,
    CONF_AI_TASK_ENTITY,
    CONF_AI_VERIF_LEVER,
    CONF_BATTERIE_SENSOR,
    CONF_SOMMEIL_PHASE,
    CONF_SOMMEIL_FENETRE_MIN,
    CONF_TRAJET_SENSOR,
    CONF_WEATHER_ENTITY,
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
    DEFAULT_NOTIFY_DEVICE,
    DEFAULT_PLAYLIST,
    DEFAULT_PRECHAUFFE_MIN,
    DEFAULT_SNOOZE_DUREE,
    DEFAULT_SNOOZE_MAX,
    DEFAULT_AGENDA_MARGE_MIN,
    DEFAULT_AI_BILAN_HEBDO,
    DEFAULT_AI_BRIEFING,
    DEFAULT_AI_MUSIQUE_ADAPT,
    DEFAULT_AI_SUGGESTION_HEURE,
    DEFAULT_AI_VERIF_LEVER,
    DEFAULT_SOMMEIL_FENETRE_MIN,
    DEFAULT_VOLUME_DUREE,
    DEFAULT_VOLUME_FINAL,
    DEFAULT_VOLUME_INITIAL,
    DOMAIN,
    JOURS_LIST,
    JOURS_OPTIONS,
)

_LOGGER = logging.getLogger(__name__)


def _entity_selector(domain: str) -> selector.EntitySelector:
    return selector.EntitySelector(selector.EntitySelectorConfig(domain=[domain]))


def _num(minv, maxv, step=1, unit=None, default=None) -> selector.NumberSelector:
    cfg = selector.NumberSelectorConfig(
        min=minv, max=maxv, step=step, mode=selector.NumberSelectorMode.SLIDER
    )
    if unit:
        cfg["unit_of_measurement"] = unit
    return selector.NumberSelector(cfg)


# ── Schéma étape 1 : Base ─────────────────────────────────────
STEP_BASE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME, default="Réveil"): str,
        vol.Required(CONF_HEURE, default="07:00"): selector.TimeSelector(),
        vol.Required(CONF_JOURS, default="semaine"): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    selector.SelectOptionDict(value=k, label=v)
                    for k, v in JOURS_OPTIONS.items()
                ],
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Optional(CONF_JOURS_PERSO): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    selector.SelectOptionDict(value=j, label=j.capitalize())
                    for j in JOURS_LIST
                ],
                mode=selector.SelectSelectorMode.LIST,
                multiple=True,
            )
        ),
        vol.Optional(CONF_PONCTUEL, default=False): bool,
        vol.Optional(CONF_SKIP_PROCHAIN, default=False): bool,
        vol.Optional(CONF_MODE_VACANCES, default=False): bool,
    }
)

# ── Schéma étape 2 : Lumière & aube ───────────────────────────
STEP_LUMIERE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_LUMIERE_ACTIVEE, default=True): bool,
        vol.Optional(CONF_LUMIERE): _entity_selector("light"),
        vol.Optional(CONF_BRIGHTNESS_MAX, default=DEFAULT_BRIGHTNESS_MAX): _num(1, 255, 1),
        vol.Optional(CONF_DUREE_PROGRESSIVE, default=DEFAULT_DUREE_PROGRESSIVE): _num(5, 60, 1, "min"),
        vol.Optional(CONF_AUBE_MIN, default=DEFAULT_AUBE_MIN): _num(0, 60, 5, "min"),
    }
)

# ── Schéma étape 3 : Musique ──────────────────────────────────
STEP_MUSIQUE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_MUSIQUE_ACTIVEE, default=True): bool,
        vol.Optional(CONF_MEDIA_PLAYER): _entity_selector("media_player"),
        vol.Optional(CONF_PLAYLIST, default=DEFAULT_PLAYLIST): str,
        vol.Optional(CONF_VOLUME_INITIAL, default=DEFAULT_VOLUME_INITIAL): _num(0.01, 1, 0.01),
        vol.Optional(CONF_VOLUME_FINAL, default=DEFAULT_VOLUME_FINAL): _num(0.01, 1, 0.01),
        vol.Optional(CONF_VOLUME_DUREE, default=DEFAULT_VOLUME_DUREE): _num(1, 30, 1, "min"),
    }
)

# ── Schéma étape 4 : Confort (chauffage, volets, café) ────────
STEP_CONFORT_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_PRECHAUFFE_MIN, default=DEFAULT_PRECHAUFFE_MIN): _num(0, 120, 5, "min"),
        vol.Optional(CONF_RADIATEUR): _entity_selector("climate"),
        vol.Optional(CONF_CHAUFFE_EAU): _entity_selector("switch"),
        vol.Optional(CONF_CAFETIERE): _entity_selector("switch"),
        vol.Optional(CONF_CAFETIERE_MIN, default=DEFAULT_CAFETIERE_MIN): _num(0, 30, 1, "min"),
        vol.Optional(CONF_VOLETS): _entity_selector("cover"),
        vol.Optional(CONF_VOLETS_SOLEIL, default=True): bool,
    }
)

# ── Schéma étape 5 : Intelligence (présence, workday, sommeil) ─
STEP_INTELL_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_PRESENCE): _entity_selector("person"),
        vol.Optional(CONF_WORKDAY_SENSOR): _entity_selector("binary_sensor"),
        vol.Optional(CONF_IGNORER_FERIES, default=True): bool,
        vol.Optional(CONF_VACANCES_SCOLAIRES_CALENDAR): _entity_selector("calendar"),
        vol.Optional(CONF_IGNORER_VACANCES_SCOLAIRE, default=False): bool,
        vol.Optional(CONF_WITHINGS_BED_1): _entity_selector("binary_sensor"),
        vol.Optional(CONF_WITHINGS_BED_2): _entity_selector("binary_sensor"),
        vol.Optional(CONF_MOUVEMENT_SDB): _entity_selector("binary_sensor"),
        vol.Optional(CONF_MOUVEMENT_STOP, default=False): bool,
        vol.Optional(CONF_LEVER_ANTICIPE, default=False): bool,
        vol.Optional(CONF_MOUVEMENT_CUISINE): _entity_selector("binary_sensor"),
        vol.Optional(CONF_ADAPTATIF_AGENDA, default=False): bool,
        vol.Optional(CONF_AGENDA_ENTITY): _entity_selector("calendar"),
        vol.Optional(CONF_AGENDA_MARGE_MIN, default=DEFAULT_AGENDA_MARGE_MIN): _num(15, 240, 5, "min"),
        vol.Optional(CONF_SOMMEIL_PHASE, default=False): bool,
        vol.Optional(CONF_SOMMEIL_FENETRE_MIN, default=DEFAULT_SOMMEIL_FENETRE_MIN): _num(5, 45, 5, "min"),
    }
)

# ── Schéma étape 6 : Notification, snooze, escalade ───────────
STEP_NOTIF_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NOTIFICATION_ACTIVEE, default=True): bool,
        vol.Optional(CONF_NOTIFY_DEVICE, default=DEFAULT_NOTIFY_DEVICE): str,
        vol.Optional(CONF_NOTIF_TITRE, default=DEFAULT_NOTIF_TITRE): str,
        vol.Optional(CONF_NOTIF_MESSAGE, default=DEFAULT_NOTIF_MESSAGE): str,
        vol.Optional(CONF_TTS_ACTIVEE, default=False): bool,
        vol.Optional(CONF_TTS_ENTITY): _entity_selector("media_player"),
        vol.Optional(CONF_SNOOZE_DUREE, default=DEFAULT_SNOOZE_DUREE): _num(1, 30, 1, "min"),
        vol.Optional(CONF_SNOOZE_MAX, default=DEFAULT_SNOOZE_MAX): _num(0, 5, 1),
        vol.Optional(CONF_ESCALADE_MIN, default=DEFAULT_ESCALADE_MIN): _num(1, 30, 1, "min"),
    }
)

# ── Schéma étape 7 : AI Task (briefing, musique, suggestion, bilan) ─
STEP_AI_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_AI_BRIEFING, default=DEFAULT_AI_BRIEFING): bool,
        vol.Optional(CONF_AI_TASK_ENTITY): _entity_selector("ai_task"),
        vol.Optional(CONF_AI_MUSIQUE_ADAPT, default=DEFAULT_AI_MUSIQUE_ADAPT): bool,
        vol.Optional(CONF_AI_SUGGESTION_HEURE, default=DEFAULT_AI_SUGGESTION_HEURE): bool,
        vol.Optional(CONF_AI_BILAN_HEBDO, default=DEFAULT_AI_BILAN_HEBDO): bool,
        vol.Optional(CONF_AI_VERIF_LEVER, default=DEFAULT_AI_VERIF_LEVER): bool,
        vol.Optional(CONF_AI_CAMERA_VERIF): _entity_selector("camera"),
        vol.Optional(CONF_WEATHER_ENTITY): _entity_selector("weather"),
        vol.Optional(CONF_TRAJET_SENSOR): _entity_selector("sensor"),
        vol.Optional(CONF_BATTERIE_SENSOR): _entity_selector("sensor"),
    }
)


class SmartWAKEConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Gestion du flux de configuration multi-étapes."""

    VERSION = 2
    MINOR_VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Étape 1 : Base."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input.get(CONF_JOURS) == "personnalise" and not user_input.get(CONF_JOURS_PERSO):
                errors[CONF_JOURS_PERSO] = "jours_perso_required"
            if not errors:
                self._data.update(user_input)
                return await self.async_step_lumiere()
        return self.async_show_form(
            step_id="user",
            data_schema=STEP_BASE_SCHEMA,
            errors=errors,
            description_placeholders={"nom": "Réveil"},
        )

    async def async_step_lumiere(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Étape 2 : Lumière & aube."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input.get(CONF_LUMIERE_ACTIVEE) and not user_input.get(CONF_LUMIERE):
                errors[CONF_LUMIERE] = "light_required"
            if not errors:
                self._data.update(user_input)
                return await self.async_step_musique()
        return self.async_show_form(
            step_id="lumiere",
            data_schema=STEP_LUMIERE_SCHEMA,
            errors=errors,
        )

    async def async_step_musique(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Étape 3 : Musique."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input.get(CONF_MUSIQUE_ACTIVEE) and not user_input.get(CONF_MEDIA_PLAYER):
                errors[CONF_MEDIA_PLAYER] = "media_required"
            if not errors:
                self._data.update(user_input)
                return await self.async_step_confort()
        return self.async_show_form(
            step_id="musique",
            data_schema=STEP_MUSIQUE_SCHEMA,
            errors=errors,
        )

    async def async_step_confort(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Étape 4 : Confort."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_intelligence()
        return self.async_show_form(
            step_id="confort",
            data_schema=STEP_CONFORT_SCHEMA,
        )

    async def async_step_intelligence(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Étape 5 : Intelligence contextuelle."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_notification()
        return self.async_show_form(
            step_id="intelligence",
            data_schema=STEP_INTELL_SCHEMA,
        )

    async def async_step_notification(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Étape 6 : Notification, snooze, escalade."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_ai()
        return self.async_show_form(
            step_id="notification",
            data_schema=STEP_NOTIF_SCHEMA,
        )

    async def async_step_ai(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Étape 7 : AI Task (briefing, musique, suggestion, bilan)."""
        if user_input is not None:
            self._data.update(user_input)
            titre = self._data[CONF_NAME]
            await self.async_set_unique_id(f"{DOMAIN}_{titre}")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=titre, data=self._data)
        return self.async_show_form(
            step_id="ai",
            data_schema=STEP_AI_SCHEMA,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "ReveilOptionsFlow":
        return ReveilOptionsFlow(config_entry)


class ReveilOptionsFlow(config_entries.OptionsFlow):
    """Flow d'options — édition directe de toutes les valeurs."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Édition globale en un seul formulaire."""
        if user_input is not None:
            new_data = {**self.config_entry.data, **user_input}
            self.hass.config_entries.async_update_entry(
                self.config_entry, data=new_data
            )
            return self.async_create_entry(title="", data=user_input)

        data = self.config_entry.data
        schema = vol.Schema(
            {
                vol.Required(CONF_HEURE, default=data.get(CONF_HEURE, "07:00")): selector.TimeSelector(),
                vol.Required(CONF_JOURS, default=data.get(CONF_JOURS, "semaine")): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value=k, label=v)
                            for k, v in JOURS_OPTIONS.items()
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(CONF_LUMIERE_ACTIVEE, default=data.get(CONF_LUMIERE_ACTIVEE, True)): bool,
                vol.Optional(CONF_LUMIERE, default=data.get(CONF_LUMIERE)): _entity_selector("light"),
                vol.Required(CONF_MUSIQUE_ACTIVEE, default=data.get(CONF_MUSIQUE_ACTIVEE, True)): bool,
                vol.Optional(CONF_MEDIA_PLAYER, default=data.get(CONF_MEDIA_PLAYER)): _entity_selector("media_player"),
                vol.Optional(CONF_PLAYLIST, default=data.get(CONF_PLAYLIST, DEFAULT_PLAYLIST)): str,
                vol.Optional(CONF_VOLUME_FINAL, default=data.get(CONF_VOLUME_FINAL, DEFAULT_VOLUME_FINAL)): _num(0.01, 1, 0.01),
                vol.Optional(CONF_RADIATEUR, default=data.get(CONF_RADIATEUR)): _entity_selector("climate"),
                vol.Optional(CONF_PRECHAUFFE_MIN, default=data.get(CONF_PRECHAUFFE_MIN, DEFAULT_PRECHAUFFE_MIN)): _num(0, 120, 5, "min"),
                vol.Optional(CONF_CAFETIERE, default=data.get(CONF_CAFETIERE)): _entity_selector("switch"),
                vol.Optional(CONF_VOLETS, default=data.get(CONF_VOLETS)): _entity_selector("cover"),
                vol.Optional(CONF_NOTIFICATION_ACTIVEE, default=data.get(CONF_NOTIFICATION_ACTIVEE, True)): bool,
                vol.Optional(CONF_NOTIFY_DEVICE, default=data.get(CONF_NOTIFY_DEVICE, DEFAULT_NOTIFY_DEVICE)): str,
                vol.Optional(CONF_NOTIF_TITRE, default=data.get(CONF_NOTIF_TITRE, DEFAULT_NOTIF_TITRE)): str,
                vol.Optional(CONF_NOTIF_MESSAGE, default=data.get(CONF_NOTIF_MESSAGE, DEFAULT_NOTIF_MESSAGE)): str,
                vol.Optional(CONF_SNOOZE_DUREE, default=data.get(CONF_SNOOZE_DUREE, DEFAULT_SNOOZE_DUREE)): _num(1, 30, 1, "min"),
                vol.Optional(CONF_SNOOZE_MAX, default=data.get(CONF_SNOOZE_MAX, DEFAULT_SNOOZE_MAX)): _num(0, 5, 1),
                vol.Optional(CONF_ESCALADE_MIN, default=data.get(CONF_ESCALADE_MIN, DEFAULT_ESCALADE_MIN)): _num(1, 30, 1, "min"),
                vol.Optional(CONF_BRIGHTNESS_MAX, default=data.get(CONF_BRIGHTNESS_MAX, DEFAULT_BRIGHTNESS_MAX)): _num(1, 255, 1),
                vol.Optional(CONF_DUREE_PROGRESSIVE, default=data.get(CONF_DUREE_PROGRESSIVE, DEFAULT_DUREE_PROGRESSIVE)): _num(5, 60, 1, "min"),
                vol.Optional(CONF_AUBE_MIN, default=data.get(CONF_AUBE_MIN, DEFAULT_AUBE_MIN)): _num(0, 60, 5, "min"),
                vol.Optional(CONF_PONCTUEL, default=data.get(CONF_PONCTUEL, False)): bool,
                vol.Optional(CONF_SKIP_PROCHAIN, default=data.get(CONF_SKIP_PROCHAIN, False)): bool,
                vol.Optional(CONF_MODE_VACANCES, default=data.get(CONF_MODE_VACANCES, False)): bool,
                vol.Optional(CONF_IGNORER_FERIES, default=data.get(CONF_IGNORER_FERIES, True)): bool,
                vol.Optional(CONF_PRESENCE, default=data.get(CONF_PRESENCE)): _entity_selector("person"),
                vol.Optional(CONF_WORKDAY_SENSOR, default=data.get(CONF_WORKDAY_SENSOR)): _entity_selector("binary_sensor"),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)