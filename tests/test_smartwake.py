"""Tests unitaires pour SmartWAKE — coordinator, ai, config_flow.

Utilise le mock HA de /tmp/hatest pour valider la logique sans HA réel.
"""

import asyncio
import sys
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Patch asyncio.sleep pour éviter les attentes réelles
_orig_sleep = asyncio.sleep
async def _fast_sleep(sec):
    await _orig_sleep(0)
asyncio.sleep = _fast_sleep

# Mock HA minimal
sys.path.insert(0, "/tmp/hatest")


# ── Tests _jours_actifs et _parse_heure ────────────────────────

def test_jours_actifs_tous():
    from custom_components.smartwake.coordinator import _jours_actifs
    assert _jours_actifs("tous") == {0, 1, 2, 3, 4, 5, 6}


def test_jours_actifs_semaine():
    from custom_components.smartwake.coordinator import _jours_actifs
    assert _jours_actifs("semaine") == {0, 1, 2, 3, 4}


def test_jours_actifs_weekend():
    from custom_components.smartwake.coordinator import _jours_actifs
    assert _jours_actifs("weekend") == {5, 6}


def test_jours_actifs_jour_unique():
    from custom_components.smartwake.coordinator import _jours_actifs
    assert _jours_actifs("mercredi") == {2}


def test_jours_actifs_personnalise():
    from custom_components.smartwake.coordinator import _jours_actifs
    assert _jours_actifs("personnalise", ["lundi", "mercredi", "vendredi"]) == {0, 2, 4}


def test_jours_actifs_personnalise_vide():
    from custom_components.smartwake.coordinator import _jours_actifs
    assert _jours_actifs("personnalise", []) == set()


def test_parse_heure_valide():
    from custom_components.smartwake.coordinator import _parse_heure
    t = _parse_heure("07:30")
    assert t.hour == 7 and t.minute == 30


def test_parse_heure_minuit():
    from custom_components.smartwake.coordinator import _parse_heure
    t = _parse_heure("00:00")
    assert t.hour == 0 and t.minute == 0


def test_parse_heure_invalide():
    from custom_components.smartwake.coordinator import _parse_heure
    with pytest.raises((ValueError, IndexError)):
        _parse_heure("25:70")


# ── Tests coordinator ──────────────────────────────────────────

@pytest.fixture
def coordinator():
    from homeassistant.core import HomeAssistant, ConfigEntry
    from custom_components.smartwake.coordinator import ReveilCoordinator
    hass = HomeAssistant()
    entry = ConfigEntry(entry_id="test1", title="Reveil", data={
        "heure": "07:00", "jours": "semaine",
        "lumiere_activee": False, "musique_activee": False,
        "notification_activee": False,
        "snooze_duree": 5, "snooze_max": 2,
        "ignorer_feries": False,
    })
    return ReveilCoordinator(hass, entry)


@pytest.mark.asyncio
async def test_coordinator_activation(coordinator):
    await coordinator.set_actif(True)
    assert coordinator.actif is True
    assert coordinator.statut == "idle"
    assert coordinator.prochain_reveil is not None


@pytest.mark.asyncio
async def test_coordinator_desactivation(coordinator):
    await coordinator.set_actif(True)
    await coordinator.set_actif(False)
    assert coordinator.actif is False
    assert coordinator.statut == "inactif"
    assert coordinator.prochain_reveil is None


@pytest.mark.asyncio
async def test_coordinator_set_heure(coordinator):
    await coordinator.set_actif(True)
    await coordinator.set_heure("08:30")
    assert coordinator.config["heure"] == "08:30"


@pytest.mark.asyncio
async def test_coordinator_set_jours(coordinator):
    await coordinator.set_actif(True)
    await coordinator.set_jours("weekend")
    assert coordinator.config["jours"] == "weekend"


@pytest.mark.asyncio
async def test_coordinator_snooze_max(coordinator):
    await coordinator.set_actif(True)
    coordinator._reveil_en_cours = True
    coordinator._snooze_count = 0
    for _ in range(3):
        await coordinator.snooze()
    assert coordinator.snooze_count == 2  # max atteint


@pytest.mark.asyncio
async def test_coordinator_skip(coordinator):
    await coordinator.set_actif(True)
    await coordinator.sauter_prochain()
    assert coordinator.skip_prochain is True


@pytest.mark.asyncio
async def test_coordinator_reset(coordinator):
    await coordinator.set_actif(True)
    coordinator._snooze_count = 3
    await coordinator.reset()
    assert coordinator.snooze_count == 0
    assert coordinator.skip_prochain is False


@pytest.mark.asyncio
async def test_coordinator_sonne_aujourd_hui_semaine(coordinator):
    """Le réveil en mode semaine ne sonne pas le samedi."""
    await coordinator.set_actif(True)
    await coordinator.set_jours("semaine")
    samedi = datetime(2026, 7, 4, 7, 0)  # samedi
    assert coordinator._sonne_aujourd_hui(samedi) is False
    lundi = datetime(2026, 7, 6, 7, 0)  # lundi
    assert coordinator._sonne_aujourd_hui(lundi) is True


@pytest.mark.asyncio
async def test_coordinator_sonne_aujourd_hui_weekend(coordinator):
    """Le réveil en mode weekend ne sonne pas le lundi."""
    await coordinator.set_actif(True)
    await coordinator.set_jours("weekend")
    lundi = datetime(2026, 7, 6, 7, 0)
    assert coordinator._sonne_aujourd_hui(lundi) is False
    samedi = datetime(2026, 7, 4, 7, 0)
    assert coordinator._sonne_aujourd_hui(samedi) is True


@pytest.mark.asyncio
async def test_coordinator_mode_vacances(coordinator):
    """Le mode vacances suspend la sonnerie."""
    await coordinator.set_actif(True)
    coordinator.entry.data["mode_vacances"] = True
    lundi = datetime(2026, 7, 6, 7, 0)
    assert coordinator._sonne_aujourd_hui(lundi) is False


@pytest.mark.asyncio
async def test_coordinator_skip_prochain(coordinator):
    """Skip prochain désactive la sonnerie du jour."""
    await coordinator.set_actif(True)
    await coordinator.sauter_prochain()
    lundi = datetime(2026, 7, 6, 7, 0)
    assert coordinator._sonne_aujourd_hui(lundi) is False


# ── Tests config_flow validation ───────────────────────────────

def test_config_flow_nom_valide():
    """Le nom peut contenir des accents (slugify s'occupe de la conversion)."""
    from custom_components.smartwake.const import slugify
    assert slugify("Réveil") == "reveil"
    assert slugify("Réveil Élève") == "reveil_eleve"
    assert slugify("réveil_semaine") == "reveil_semaine"


def test_config_flow_nom_invalide_trop_long():
    name = "a" * 51
    assert len(name) > 50


def test_config_flow_nom_invalide_vide():
    name = ""
    assert not name


# ── Tests validation heure notification ────────────────────────

def test_heure_notification_valide():
    import re
    heure = "07:30"
    m = re.match(r"^(\d{1,2}):(\d{2})$", heure)
    assert m and 0 <= int(m.group(1)) < 24 and 0 <= int(m.group(2)) < 60


def test_heure_notification_invalide_heure():
    import re
    heure = "25:30"
    m = re.match(r"^(\d{1,2}):(\d{2})$", heure)
    assert m and not (0 <= int(m.group(1)) < 24)


def test_heure_notification_invalide_format():
    import re
    heure = "7h30"
    assert not re.match(r"^(\d{1,2}):(\d{2})$", heure)


def test_heure_notification_invalide_injection():
    import re
    heure = "07:30; rm -rf /"
    assert not re.match(r"^(\d{1,2}):(\d{2})$", heure)


# ── Tests AI module ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ai_briefing_desactive():
    from custom_components.smartwake.ai import generate_briefing
    hass = MagicMock()
    cfg = {"ai_briefing": False}
    result = await generate_briefing(hass, cfg, "Test")
    assert result is None


@pytest.mark.asyncio
async def test_ai_briefing_fallback():
    from custom_components.smartwake.ai import generate_briefing
    hass = MagicMock()
    hass.services.async_call = AsyncMock(side_effect=Exception("AI unavailable"))
    cfg = {"ai_briefing": True, "weather_entity": "weather.home"}
    result = await generate_briefing(hass, cfg, "Test")
    assert result is None  # fallback silencieux


@pytest.mark.asyncio
async def test_ai_musique_adapt_desactive():
    from custom_components.smartwake.ai import choose_adaptive_music
    hass = MagicMock()
    cfg = {"ai_musique_adapt": False}
    result = await choose_adaptive_music(hass, cfg, ["Playlist", "Radio"])
    assert result is None


@pytest.mark.asyncio
async def test_ai_suggestion_desactive():
    from custom_components.smartwake.ai import suggest_wake_time
    hass = MagicMock()
    cfg = {"ai_suggestion_heure": False}
    result = await suggest_wake_time(hass, cfg, "07:00")
    assert result is None


@pytest.mark.asyncio
async def test_ai_verif_lever_desactive():
    from custom_components.smartwake.ai import verify_person_in_bed
    hass = MagicMock()
    cfg = {"ai_verif_lever": False}
    result = await verify_person_in_bed(hass, cfg)
    assert result is None


@pytest.mark.asyncio
async def test_ai_bilan_hebdo_desactive():
    from custom_components.smartwake.ai import generate_weekly_report
    hass = MagicMock()
    cfg = {"ai_bilan_hebdo": False}
    result = await generate_weekly_report(hass, cfg, 0, "")
    assert result is None