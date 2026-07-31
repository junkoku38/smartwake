"""Config flow simplifié — 1 étape pour créer, options pour affiner.

Étape 1 : nom + heure + jours + preset (30 secondes)
Options : tout le reste, modifiable après via "Configurer"
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector

from .const import (
    CONF_AI_BILAN_HEBDO,
    CONF_AI_BRIEFING,
    CONF_AI_CAMERA_VERIF,
    CONF_AI_CUSTOM_ENABLED,
    CONF_AI_CUSTOM_PROMPT,
    CONF_AI_CUSTOM_TRIGGER,
    CONF_AI_CUSTOM_ENTITIES,
    CONF_AI_MUSIQUE_ADAPT,
    CONF_AI_SUGGESTION_HEURE,
    CONF_AI_TASK_ENTITY,
    CONF_AI_VERIF_LEVER,
    CONF_AUBE_MIN,
    CONF_BATTERIE_SENSOR,
    CONF_BRIGHTNESS_MAX,
    CONF_CAFETIERE,
    CONF_CAFETIERE_MIN,
    CONF_CHAUFFE_EAU,
    CONF_DUREE_PROGRESSIVE,
    CONF_ESCALADE_INTELLIGENTE,
    CONF_ESCALADE_MIN,
    CONF_HEURE,
    CONF_HEURE_DIMANCHE,
    CONF_HEURE_JEUDI,
    CONF_HEURE_LUNDI,
    CONF_HEURE_MARDI,
    CONF_HEURE_MERCREDI,
    CONF_HEURE_SAMEDI,
    CONF_HEURE_VENDREDI,
    CONF_IGNORER_FERIES,
    CONF_IGNORER_VACANCES_SCOLAIRE,
    CONF_JOURS,
    CONF_JOURS_PERSO,
    CONF_LEVER_ANTICIPE,
    CONF_LUMIERE,
    CONF_LUMIERE_ACTIVEE,
    CONF_MOUVEMENT_CUISINE,
    CONF_MOUVEMENT_SDB,
    CONF_MOUVEMENT_STOP,
    CONF_MEDIA_PLAYER,
    CONF_MODE_HEURE,
    CONF_MODE_VACANCES,
    CONF_MODE_VACANCES_ENTITY,
    CONF_MUSIQUE_ACTIVEE,
    CONF_NOTIF_MESSAGE,
    CONF_TTS_MESSAGE,
    CONF_NOTIF_TITRE,
    CONF_NOTIFICATION_ACTIVEE,
    CONF_NOTIFY_DEVICE,
    CONF_PLAYLIST,
    CONF_PONCTUEL,
    CONF_PRECHAUFFE_MIN,
    CONF_PRESENCE,
    CONF_RADIATEUR,
    CONF_SCENE_MATIN_ENTITIES,
    CONF_VOLETS_POSITION,
    CONF_SCENES_MATIN,
    CONF_SKIP_PROCHAIN,
    CONF_SNOOZE_DUREE,
    CONF_SNOOZE_MAX,
    CONF_SOMMEIL_PHASE,
    CONF_SOMMEIL_FENETRE_MIN,
    CONF_TRAJET_SENSOR,
    CONF_TTS_ACTIVEE,
    CONF_TTS_ENGINE,
    CONF_TTS_ENTITY,
    CONF_VOLUME_DUREE,
    CONF_VOLUME_FINAL,
    CONF_VOLUME_INITIAL,
    CONF_VOLETS,
    CONF_VOLETS_SOLEIL,
    CONF_VACANCES_SCOLAIRES_CALENDAR,
    CONF_WITHINGS_BED_1,
    CONF_WITHINGS_BED_2,
    CONF_WEATHER_ENTITY,
    CONF_WORKDAY_SENSOR,
    CONF_BRIEFING_MULTI_CAPTEURS,
    CONF_CAPTEUR_QUALITE_AIR,
    CONF_CAPTEUR_CO2,
    DEFAULT_AUBE_MIN,
    DEFAULT_BRIGHTNESS_MAX,
    DEFAULT_CAFETIERE_MIN,
    DEFAULT_DUREE_PROGRESSIVE,
    DEFAULT_ESCALADE_MIN,
    DEFAULT_NOTIF_MESSAGE,
    DEFAULT_NOTIF_TITRE,
    DEFAULT_TTS_MESSAGE,
    DEFAULT_NOTIFY_DEVICE,
    DEFAULT_PLAYLIST,
    DEFAULT_PRECHAUFFE_MIN,
    DEFAULT_SNOOZE_DUREE,
    DEFAULT_SNOOZE_MAX,
    DEFAULT_VOLUME_DUREE,
    DEFAULT_VOLUME_FINAL,
    DEFAULT_VOLUME_INITIAL,
    DEFAULT_AGENDA_MARGE_MIN,
    DEFAULT_SOMMEIL_FENETRE_MIN,
    DOMAIN,
    JOURS_LIST,
    JOURS_OPTIONS,
    slugify,
)

_LOGGER = logging.getLogger(__name__)


def _entity(domain: str) -> selector.EntitySelector:
    return selector.EntitySelector(selector.EntitySelectorConfig(domain=[domain]))


def _num(minv, maxv, step=1, unit=None) -> selector.NumberSelector:
    cfg = selector.NumberSelectorConfig(
        min=minv, max=maxv, step=step, mode=selector.NumberSelectorMode.SLIDER
    )
    if unit:
        cfg["unit_of_measurement"] = unit
    return selector.NumberSelector(cfg)


# ── Presets ───────────────────────────────────────────────────
PRESET_SIMPLE = "simple"
PRESET_CONFORT = "confort"
PRESET_COMPLET = "complet"

PRESETS = {
    PRESET_SIMPLE: {
        "lumiere_activee": False,
        "musique_activee": True,
        "notification_activee": True,
    },
    PRESET_CONFORT: {
        "lumiere_activee": True,
        "musique_activee": True,
        "notification_activee": True,
        "prechauffe_min": 30,
        "aube_min": 20,
    },
    PRESET_COMPLET: {
        "lumiere_activee": True,
        "musique_activee": True,
        "notification_activee": True,
        "prechauffe_min": 45,
        "aube_min": 20,
        "cafetiere_min": 10,
        "volets_soleil": True,
        "ignorer_feries": True,
        "mouvement_stop": True,
        "lever_anticippe": True,
        "escalade_intelligente": True,
    },
}


# ── Étape unique : création rapide ─────────────────────────────
STEP_USER_SCHEMA = vol.Schema(
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
        vol.Required("preset", default=PRESET_CONFORT): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    selector.SelectOptionDict(value=PRESET_SIMPLE, label="🎵 Simple — musique + notification"),
                    selector.SelectOptionDict(value=PRESET_CONFORT, label="🌅 Confort — musique + lumière + notification"),
                    selector.SelectOptionDict(value=PRESET_COMPLET, label="🏠 Complet — tout (chauffage, volets, IA, etc.)"),
                ],
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
    }
)


async def _auto_detect_entities(hass: HomeAssistant) -> dict[str, str | None]:
    """Détecte automatiquement les entités pertinentes dans HA."""
    detected = {}

    def _entities(domain: str) -> list[str]:
        try:
            return list(hass.states.async_entity_ids(domain))
        except Exception:
            try:
                return [s.entity_id for s in hass.states.async_all() if s.entity_id.startswith(domain + ".")]
            except Exception:
                return []

    # Première lumière de la chambre
    lights = [e for e in _entities("light") if "chambre" in e or "bedroom" in e]
    all_lights = _entities("light")
    detected[CONF_LUMIERE] = lights[0] if lights else (all_lights[0] if all_lights else None)

    # Premier media player
    players = _entities("media_player")
    detected[CONF_MEDIA_PLAYER] = players[0] if players else None

    # Premier climate
    climates = _entities("climate")
    detected[CONF_RADIATEUR] = climates[0] if climates else None

    # Premier cover
    covers = [e for e in _entities("cover") if "volet" in e or "shutter" in e or "blind" in e]
    all_covers = _entities("cover")
    detected[CONF_VOLETS] = covers[0] if covers else (all_covers[0] if all_covers else None)

    # Workday sensor
    workdays = [e for e in _entities("binary_sensor") if "workday" in e]
    detected[CONF_WORKDAY_SENSOR] = workdays[0] if workdays else None

    # Person
    persons = _entities("person")
    detected[CONF_PRESENCE] = persons[0] if persons else None

    # Weather
    weathers = _entities("weather")
    detected[CONF_WEATHER_ENTITY] = weathers[0] if weathers else None

    # Notify
    notifies = [e for e in _entities("notify") if "mobile_app" in e]
    detected[CONF_NOTIFY_DEVICE] = notifies[0] if notifies else DEFAULT_NOTIFY_DEVICE

    return detected


class SmartWAKEConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow simplifié : 1 étape."""

    VERSION = 3
    MINOR_VERSION = 0

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Étape unique : nom + heure + jours + preset."""
        import re
        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input.get(CONF_NAME, "")
            if not name or len(name) > 50:
                errors[CONF_NAME] = "invalid_name"
            if user_input.get(CONF_JOURS) == "personnalise" and not user_input.get(CONF_JOURS_PERSO):
                errors[CONF_JOURS_PERSO] = "jours_perso_required"
            if not errors:
                # Appliquer le preset
                preset = user_input.pop("preset", PRESET_CONFORT)
                self._data = {**PRESETS.get(preset, PRESETS[PRESET_CONFORT])}
                self._data.update(user_input)

                # Auto-détection des entités
                detected = await _auto_detect_entities(self.hass)
                self._data.update({k: v for k, v in detected.items() if v is not None})

                # Valeurs par défaut
                self._data.setdefault(CONF_SNOOZE_DUREE, DEFAULT_SNOOZE_DUREE)
                self._data.setdefault(CONF_SNOOZE_MAX, DEFAULT_SNOOZE_MAX)
                self._data.setdefault(CONF_ESCALADE_MIN, DEFAULT_ESCALADE_MIN)
                self._data.setdefault(CONF_BRIGHTNESS_MAX, DEFAULT_BRIGHTNESS_MAX)
                self._data.setdefault(CONF_DUREE_PROGRESSIVE, DEFAULT_DUREE_PROGRESSIVE)
                self._data.setdefault(CONF_AUBE_MIN, DEFAULT_AUBE_MIN)
                self._data.setdefault(CONF_VOLUME_INITIAL, DEFAULT_VOLUME_INITIAL)
                self._data.setdefault(CONF_VOLUME_FINAL, DEFAULT_VOLUME_FINAL)
                self._data.setdefault(CONF_VOLUME_DUREE, DEFAULT_VOLUME_DUREE)
                self._data.setdefault(CONF_PLAYLIST, DEFAULT_PLAYLIST)
                self._data.setdefault(CONF_NOTIF_TITRE, DEFAULT_NOTIF_TITRE)
                self._data.setdefault(CONF_NOTIF_MESSAGE, DEFAULT_NOTIF_MESSAGE)
                self._data.setdefault(CONF_PRECHAUFFE_MIN, DEFAULT_PRECHAUFFE_MIN)
                self._data.setdefault(CONF_CAFETIERE_MIN, DEFAULT_CAFETIERE_MIN)
                self._data.setdefault(CONF_PONCTUEL, False)
                self._data.setdefault(CONF_SKIP_PROCHAIN, False)
                self._data.setdefault(CONF_MODE_VACANCES, False)

                titre = self._data[CONF_NAME]
                await self.async_set_unique_id(f"{DOMAIN}_{titre}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=titre, data=self._data)
        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
            description_placeholders={"nom": "Réveil"},
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "SmartWAKEOptionsFlow":
        return SmartWAKEOptionsFlow(config_entry)


class SmartWAKEOptionsFlow(config_entries.OptionsFlow):
    """Flow d'options — tout est modifiable après création, par section."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry
        self._section: str | None = None

    @property
    def _data(self) -> dict[str, Any]:
        return dict(self._config_entry.data)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Menu de sélection des sections à modifier."""
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "base",
                "musique",
                "lumiere",
                "confort",
                "intelligence",
                "notification",
                "ai",
            ],
        )

    async def async_step_base(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        data = self._config_entry.data
        if user_input is not None:
            new_data = {**data, **user_input}
            self.hass.config_entries.async_update_entry(self._config_entry, data=new_data)
            return await self.async_step_init()
        return self.async_show_form(
            step_id="base",
            data_schema=vol.Schema({
                vol.Required(CONF_MODE_HEURE, default=data.get(CONF_MODE_HEURE, "unique")): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value="unique", label="Heure unique (même heure tous les jours)"),
                            selector.SelectOptionDict(value="par_jour", label="Heure par jour (différente selon le jour)"),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(CONF_HEURE, default=data.get(CONF_HEURE, "07:00")): selector.TimeSelector(),
                vol.Optional(CONF_HEURE_LUNDI, default=data.get(CONF_HEURE_LUNDI, "07:00")): selector.TimeSelector(),
                vol.Optional(CONF_HEURE_MARDI, default=data.get(CONF_HEURE_MARDI, "07:00")): selector.TimeSelector(),
                vol.Optional(CONF_HEURE_MERCREDI, default=data.get(CONF_HEURE_MERCREDI, "07:00")): selector.TimeSelector(),
                vol.Optional(CONF_HEURE_JEUDI, default=data.get(CONF_HEURE_JEUDI, "07:00")): selector.TimeSelector(),
                vol.Optional(CONF_HEURE_VENDREDI, default=data.get(CONF_HEURE_VENDREDI, "07:00")): selector.TimeSelector(),
                vol.Optional(CONF_HEURE_SAMEDI, default=data.get(CONF_HEURE_SAMEDI, "08:00")): selector.TimeSelector(),
                vol.Optional(CONF_HEURE_DIMANCHE, default=data.get(CONF_HEURE_DIMANCHE, "08:00")): selector.TimeSelector(),
                vol.Required(CONF_JOURS, default=data.get(CONF_JOURS, "semaine")): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[selector.SelectOptionDict(value=k, label=v) for k, v in JOURS_OPTIONS.items()],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(CONF_JOURS_PERSO, default=data.get(CONF_JOURS_PERSO, [])): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[selector.SelectOptionDict(value=j, label=j.capitalize()) for j in JOURS_LIST],
                        mode=selector.SelectSelectorMode.LIST,
                        multiple=True,
                    )
                ),
                vol.Optional(CONF_PONCTUEL, default=data.get(CONF_PONCTUEL, False)): bool,
                vol.Optional(CONF_SKIP_PROCHAIN, default=data.get(CONF_SKIP_PROCHAIN, False)): bool,
                vol.Optional(CONF_MODE_VACANCES, default=data.get(CONF_MODE_VACANCES, False)): bool,
                vol.Optional(CONF_MODE_VACANCES_ENTITY, default=data.get(CONF_MODE_VACANCES_ENTITY) or ""): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["calendar", "input_boolean", "binary_sensor", "person"])
                ),
            }),
        )

    async def async_step_musique(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        data = self._config_entry.data
        if user_input is not None:
            new_data = {**data, **user_input}
            self.hass.config_entries.async_update_entry(self._config_entry, data=new_data)
            return await self.async_step_init()
        return self.async_show_form(
            step_id="musique",
            data_schema=vol.Schema({
                vol.Required(CONF_MUSIQUE_ACTIVEE, default=data.get(CONF_MUSIQUE_ACTIVEE, True)): bool,
                vol.Optional(CONF_MEDIA_PLAYER, default=data.get(CONF_MEDIA_PLAYER) or ""): _entity("media_player"),
                vol.Optional(CONF_PLAYLIST, default=data.get(CONF_PLAYLIST)): selector.MediaSelector(),
                vol.Optional(CONF_VOLUME_INITIAL, default=data.get(CONF_VOLUME_INITIAL, DEFAULT_VOLUME_INITIAL)): _num(0.01, 1, 0.01),
                vol.Optional(CONF_VOLUME_FINAL, default=data.get(CONF_VOLUME_FINAL, DEFAULT_VOLUME_FINAL)): _num(0.01, 1, 0.01),
                vol.Optional(CONF_VOLUME_DUREE, default=data.get(CONF_VOLUME_DUREE, DEFAULT_VOLUME_DUREE)): _num(1, 30, 1, "min"),
            }),
        )

    async def async_step_lumiere(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        data = self._config_entry.data
        if user_input is not None:
            new_data = {**data, **user_input}
            self.hass.config_entries.async_update_entry(self._config_entry, data=new_data)
            return await self.async_step_init()
        return self.async_show_form(
            step_id="lumiere",
            data_schema=vol.Schema({
                vol.Required(CONF_LUMIERE_ACTIVEE, default=data.get(CONF_LUMIERE_ACTIVEE, True)): bool,
                vol.Optional(CONF_LUMIERE, default=data.get(CONF_LUMIERE) or ""): _entity("light"),
                vol.Optional(CONF_BRIGHTNESS_MAX, default=data.get(CONF_BRIGHTNESS_MAX, DEFAULT_BRIGHTNESS_MAX)): _num(1, 255, 1),
                vol.Optional(CONF_DUREE_PROGRESSIVE, default=data.get(CONF_DUREE_PROGRESSIVE, DEFAULT_DUREE_PROGRESSIVE)): _num(5, 60, 1, "min"),
                vol.Optional(CONF_AUBE_MIN, default=data.get(CONF_AUBE_MIN, DEFAULT_AUBE_MIN)): _num(0, 60, 5, "min"),
            }),
        )

    async def async_step_confort(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        data = self._config_entry.data
        if user_input is not None:
            new_data = {**data, **user_input}
            self.hass.config_entries.async_update_entry(self._config_entry, data=new_data)
            return await self.async_step_init()
        return self.async_show_form(
            step_id="confort",
            data_schema=vol.Schema({
                vol.Optional(CONF_PRECHAUFFE_MIN, default=data.get(CONF_PRECHAUFFE_MIN, DEFAULT_PRECHAUFFE_MIN)): _num(0, 120, 5, "min"),
                vol.Optional(CONF_RADIATEUR, default=data.get(CONF_RADIATEUR) or ""): _entity("climate"),
                vol.Optional(CONF_CHAUFFE_EAU, default=data.get(CONF_CHAUFFE_EAU) or ""): _entity("switch"),
                vol.Optional(CONF_CAFETIERE, default=data.get(CONF_CAFETIERE) or ""): _entity("switch"),
                vol.Optional(CONF_CAFETIERE_MIN, default=data.get(CONF_CAFETIERE_MIN, DEFAULT_CAFETIERE_MIN)): _num(0, 30, 1, "min"),
                vol.Optional(CONF_VOLETS, default=data.get(CONF_VOLETS) or ""): _entity("cover"),
                vol.Optional(CONF_VOLETS_POSITION, default=data.get(CONF_VOLETS_POSITION, 100)): _num(0, 100, 5, "%"),
                vol.Optional(CONF_VOLETS_SOLEIL, default=data.get(CONF_VOLETS_SOLEIL, True)): bool,
                vol.Optional(CONF_SCENE_MATIN_ENTITIES, default=data.get(CONF_SCENE_MATIN_ENTITIES, [])): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["light", "scene"], multiple=True)
                ),
            }),
        )

    async def async_step_intelligence(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        data = self._config_entry.data
        if user_input is not None:
            new_data = {**data, **user_input}
            self.hass.config_entries.async_update_entry(self._config_entry, data=new_data)
            return await self.async_step_init()
        return self.async_show_form(
            step_id="intelligence",
            data_schema=vol.Schema({
                vol.Optional(CONF_PRESENCE, default=data.get(CONF_PRESENCE) or ""): _entity("person"),
                vol.Optional(CONF_WORKDAY_SENSOR, default=data.get(CONF_WORKDAY_SENSOR) or ""): _entity("binary_sensor"),
                vol.Optional(CONF_IGNORER_FERIES, default=data.get(CONF_IGNORER_FERIES, True)): bool,
                vol.Optional(CONF_VACANCES_SCOLAIRES_CALENDAR, default=data.get(CONF_VACANCES_SCOLAIRES_CALENDAR) or ""): _entity("calendar"),
                vol.Optional(CONF_IGNORER_VACANCES_SCOLAIRE, default=data.get(CONF_IGNORER_VACANCES_SCOLAIRE, False)): bool,
                vol.Optional(CONF_WITHINGS_BED_1, default=data.get(CONF_WITHINGS_BED_1) or ""): _entity("binary_sensor"),
                vol.Optional(CONF_WITHINGS_BED_2, default=data.get(CONF_WITHINGS_BED_2) or ""): _entity("binary_sensor"),
                vol.Optional(CONF_MOUVEMENT_SDB, default=data.get(CONF_MOUVEMENT_SDB) or ""): _entity("binary_sensor"),
                vol.Optional(CONF_MOUVEMENT_STOP, default=data.get(CONF_MOUVEMENT_STOP, False)): bool,
                vol.Optional(CONF_LEVER_ANTICIPE, default=data.get(CONF_LEVER_ANTICIPE, False)): bool,
                vol.Optional(CONF_MOUVEMENT_CUISINE, default=data.get(CONF_MOUVEMENT_CUISINE) or ""): _entity("binary_sensor"),
                vol.Optional(CONF_ESCALADE_INTELLIGENTE, default=data.get(CONF_ESCALADE_INTELLIGENTE, False)): bool,
            }),
        )

    async def async_step_notification(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        data = self._config_entry.data
        if user_input is not None:
            new_data = {**data, **user_input}
            self.hass.config_entries.async_update_entry(self._config_entry, data=new_data)
            return await self.async_step_init()
        return self.async_show_form(
            step_id="notification",
            data_schema=vol.Schema({
                vol.Required(CONF_NOTIFICATION_ACTIVEE, default=data.get(CONF_NOTIFICATION_ACTIVEE, True)): bool,
                vol.Optional(CONF_NOTIFY_DEVICE, default=data.get(CONF_NOTIFY_DEVICE) or ""): _entity("notify"),
                vol.Optional(CONF_NOTIF_TITRE, default=data.get(CONF_NOTIF_TITRE, DEFAULT_NOTIF_TITRE)): str,
                vol.Optional(CONF_NOTIF_MESSAGE, default=data.get(CONF_NOTIF_MESSAGE, DEFAULT_NOTIF_MESSAGE)): str,
                vol.Optional(CONF_TTS_ACTIVEE, default=data.get(CONF_TTS_ACTIVEE, False)): bool,
                vol.Optional(CONF_TTS_ENTITY, default=data.get(CONF_TTS_ENTITY) or ""): _entity("media_player"),
                vol.Optional(CONF_TTS_ENGINE, default=data.get(CONF_TTS_ENGINE) or ""): _entity("tts"),
                vol.Optional(CONF_TTS_MESSAGE, default=data.get(CONF_TTS_MESSAGE, DEFAULT_TTS_MESSAGE)): str,
                vol.Optional(CONF_SNOOZE_DUREE, default=data.get(CONF_SNOOZE_DUREE, DEFAULT_SNOOZE_DUREE)): _num(1, 30, 1, "min"),
                vol.Optional(CONF_SNOOZE_MAX, default=data.get(CONF_SNOOZE_MAX, DEFAULT_SNOOZE_MAX)): _num(0, 5, 1),
                vol.Optional(CONF_ESCALADE_MIN, default=data.get(CONF_ESCALADE_MIN, DEFAULT_ESCALADE_MIN)): _num(1, 30, 1, "min"),
            }),
        )

    async def async_step_ai(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        data = self._config_entry.data
        if user_input is not None:
            new_data = {**data, **user_input}
            self.hass.config_entries.async_update_entry(self._config_entry, data=new_data)
            return await self.async_step_init()
        return self.async_show_form(
            step_id="ai",
            data_schema=vol.Schema({
                vol.Optional(CONF_AI_BRIEFING, default=data.get(CONF_AI_BRIEFING, False)): bool,
                vol.Optional(CONF_AI_TASK_ENTITY, default=data.get(CONF_AI_TASK_ENTITY) or ""): _entity("ai_task"),
                vol.Optional(CONF_AI_MUSIQUE_ADAPT, default=data.get(CONF_AI_MUSIQUE_ADAPT, False)): bool,
                vol.Optional(CONF_AI_SUGGESTION_HEURE, default=data.get(CONF_AI_SUGGESTION_HEURE, False)): bool,
                vol.Optional(CONF_AI_BILAN_HEBDO, default=data.get(CONF_AI_BILAN_HEBDO, False)): bool,
                vol.Optional(CONF_AI_VERIF_LEVER, default=data.get(CONF_AI_VERIF_LEVER, False)): bool,
                vol.Optional(CONF_AI_CAMERA_VERIF, default=data.get(CONF_AI_CAMERA_VERIF) or ""): _entity("camera"),
                vol.Optional(CONF_WEATHER_ENTITY, default=data.get(CONF_WEATHER_ENTITY) or ""): _entity("weather"),
                vol.Optional(CONF_TRAJET_SENSOR, default=data.get(CONF_TRAJET_SENSOR) or ""): _entity("sensor"),
                vol.Optional(CONF_BATTERIE_SENSOR, default=data.get(CONF_BATTERIE_SENSOR) or ""): _entity("sensor"),
                vol.Optional(CONF_AI_CUSTOM_ENABLED, default=data.get(CONF_AI_CUSTOM_ENABLED, False)): bool,
                vol.Optional(CONF_AI_CUSTOM_PROMPT, default=data.get(CONF_AI_CUSTOM_PROMPT, "")): selector.TextSelector(
                    selector.TextSelectorConfig(multiline=True)
                ),
                vol.Optional(CONF_AI_CUSTOM_TRIGGER, default=data.get(CONF_AI_CUSTOM_TRIGGER, "on_stop")): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value="on_wake", label="Au déclenchement du réveil"),
                            selector.SelectOptionDict(value="on_stop", label="Au Stop (quand vous vous levez)"),
                            selector.SelectOptionDict(value="on_evening", label="Le soir (21:30)"),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(CONF_AI_CUSTOM_ENTITIES, default=data.get(CONF_AI_CUSTOM_ENTITIES, [])): selector.EntitySelector(
                    selector.EntitySelectorConfig(multiple=True)
                ),
            }),
        )