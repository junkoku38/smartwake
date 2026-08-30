"""Diagnostics pour SmartWAKE.

Fournit un instantané exploitable pour le débogage — configuration, état
d'exécution, entités liées — sans exposer d'information personnelle. Les
entités désignées et les messages libres sont expurgés.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

# Clés dont la valeur peut identifier une personne ou une pièce, ou contenir un
# message libre. On conserve le fait qu'elles sont renseignées, pas leur contenu.
A_EXPURGER = {
    "nom",
    "notify_device",
    "presence",
    "mode_travail_entity",
    "agenda_entity",
    "vacances_scolaires_calendar",
    "mode_vacances_entity",
    "tts_message",
    "notif_titre",
    "notif_message",
    "ai_custom_prompt",
    "ai_custom_tasks",
    "presence_lit_sensors",
    "sommeil_sensors",
    "scene_matin_entities",
    "ai_custom_entities",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Instantané de diagnostic d'un réveil."""
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)

    diag: dict[str, Any] = {
        "entry": {
            "version": entry.version,
            "minor_version": entry.minor_version,
            "source": entry.source,
        },
        "config": async_redact_data(dict(entry.data), A_EXPURGER),
    }

    if coordinator is None:
        diag["coordinator"] = "non chargé"
        return diag

    prochain = coordinator.prochain_reveil
    snooze_fin = coordinator.snooze_fin
    diag["coordinator"] = {
        "actif": coordinator.actif,
        "statut": coordinator.statut,
        "prochain_reveil": prochain.isoformat() if prochain else None,
        "reveil_en_cours": coordinator._reveil_en_cours,
        "snooze_count": coordinator.snooze_count,
        "snooze_fin": snooze_fin.isoformat() if snooze_fin else None,
        "skip_prochain": coordinator.skip_prochain,
        "skip_date": coordinator._skip_date.isoformat() if coordinator._skip_date else None,
        "aube_niveau": coordinator._aube_niveau,
        "etats_initiaux": bool(coordinator._etats_initiaux),
        "pending_ringing": coordinator._pending_ringing,
        # Déclencheurs armés : le plus souvent en cause quand le réveil ne sonne pas
        "trigger_arme": coordinator._cancel_trigger is not None,
        "prewake_arme": coordinator._cancel_prewake is not None,
        "taches_en_cours": {
            "cycle": coordinator._cancel_cycle is not None,
            "escalade": coordinator._cancel_escalade is not None,
            "snooze": coordinator._cancel_snooze is not None,
            "rampes": len(coordinator._cancel_rampes),
        },
    }

    # État des entités référencées, pour repérer un capteur indisponible sans
    # divulguer son identifiant
    refs = {
        "media_player": entry.data.get("media_player"),
        "lumiere": entry.data.get("lumiere"),
        "radiateur": entry.data.get("radiateur"),
        "volets": entry.data.get("volets"),
        "weather": entry.data.get("weather"),
        "workday_sensor": entry.data.get("workday_sensor"),
        "ai_task_entity": entry.data.get("ai_task_entity"),
    }
    etats = {}
    for role, entity_id in refs.items():
        if not entity_id:
            continue
        st = hass.states.get(entity_id)
        etats[role] = {
            "domaine": entity_id.split(".")[0],
            "etat": st.state if st else "introuvable",
            "disponible": st is not None and st.state not in ("unknown", "unavailable"),
        }
    diag["entites_referencees"] = etats

    return diag
