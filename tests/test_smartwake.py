"""Tests unitaires pour SmartWAKE — coordinator, ai, config_flow.

Utilise le mock Home Assistant de tests/mock_ha/, versionné dans le dépôt,
pour valider la logique sans installation complète de Home Assistant.
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta
from datetime import time as dtime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Patch asyncio.sleep pour éviter les attentes réelles
_orig_sleep = asyncio.sleep
async def _fast_sleep(sec):
    await _orig_sleep(0)
asyncio.sleep = _fast_sleep

# Mock Home Assistant minimal, versionné dans le dépôt.
# Il était auparavant attendu dans /tmp/hatest, chemin absolu propre à une seule
# machine : la suite de tests n'était donc reproductible nulle part ailleurs.
sys.path.insert(0, str(Path(__file__).parent / "mock_ha"))


def _stub_number_module():
    """Le mock HA ne fournit pas homeassistant.components.number.

    On installe un substitut minimal afin de pouvoir tester
    ReveilNumber.async_set_native_value (cf. régression self.entry).
    """
    import types

    if "homeassistant.components.number" in sys.modules:
        return

    mod = types.ModuleType("homeassistant.components.number")

    class NumberMode:
        SLIDER = "slider"
        BOX = "box"

    class NumberEntityDescription:
        def __init__(self, key, name=None, icon=None, native_min_value=None,
                     native_max_value=None, native_step=None, **kw):
            self.key = key
            self.name = name
            self.icon = icon
            self.native_min_value = native_min_value
            self.native_max_value = native_max_value
            self.native_step = native_step

    class NumberEntity:
        entity_description = None
        hass = None

        @property
        def native_step(self):
            return getattr(self.entity_description, "native_step", None)

        def async_write_ha_state(self):
            pass

        def async_on_remove(self, fn):
            pass

    mod.NumberEntity = NumberEntity
    mod.NumberEntityDescription = NumberEntityDescription
    mod.NumberMode = NumberMode
    sys.modules["homeassistant.components.number"] = mod

    if "homeassistant.helpers.entity_platform" not in sys.modules:
        plat = types.ModuleType("homeassistant.helpers.entity_platform")
        plat.AddEntitiesCallback = object
        sys.modules["homeassistant.helpers.entity_platform"] = plat

    # entity.py importe DeviceInfo, absent du mock
    from homeassistant.helpers import device_registry as dr

    if not hasattr(dr, "DeviceInfo"):
        dr.DeviceInfo = dict


def _stub_storage_module():
    """learning.py importe homeassistant.helpers.storage, absent du mock."""
    import types

    if "homeassistant.helpers.storage" in sys.modules:
        return

    mod = types.ModuleType("homeassistant.helpers.storage")

    class Store:
        def __init__(self, hass, version, key):
            self._data = None

        async def async_load(self):
            return self._data

        async def async_save(self, data):
            self._data = data

    mod.Store = Store
    sys.modules["homeassistant.helpers.storage"] = mod


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
    """Régression : une heure malformée levait une exception qui remontait
    jusqu'au rafraîchissement du coordinator, rendant toutes les entités
    indisponibles. Un repli silencieux est préférable à un réveil hors service.
    """
    from datetime import time as _t

    from custom_components.smartwake.coordinator import _parse_heure

    for invalide in ("25:70", "7h00", "", None, "abc", "12"):
        assert _parse_heure(invalide) == _t(7, 0), f"repli manquant pour {invalide!r}"

    # Les valeurs correctes restent interprétées
    assert _parse_heure("06:45") == _t(6, 45)
    assert _parse_heure("6:45") == _t(6, 45)


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
    """Le nombre de snoozes est plafonné par snooze_max.

    Chaque snooze suppose que la sonnerie a reprise entre-temps : la garde
    anti-réentrance refuse un second snooze pendant un snooze en cours.
    """
    await coordinator.set_actif(True)
    coordinator._reveil_en_cours = True
    coordinator._snooze_count = 0
    for _ in range(3):
        coordinator._statut = "ringing"  # la sonnerie a reprise
        await coordinator.snooze()
    assert coordinator.snooze_count == 2  # max atteint


@pytest.mark.asyncio
async def test_snooze_non_reentrant(coordinator):
    """Régression : deux appuis rapprochés (notification + bouton) lançaient
    deux minuteries concurrentes, chacune relançant la musique."""
    await coordinator.set_actif(True)
    coordinator._reveil_en_cours = True
    coordinator._statut = "ringing"

    await coordinator.snooze()
    assert coordinator.snooze_count == 1
    await coordinator.snooze()  # ignoré : snooze déjà en cours
    assert coordinator.snooze_count == 1


@pytest.mark.asyncio
async def test_snooze_ne_bloque_pas_l_appelant(coordinator):
    """Régression : snooze() attendait la durée complète du snooze, bloquant
    le service smartwake.snooze et donc l'automatisation appelante."""
    coordinator.entry.data = {**coordinator.entry.data, "snooze_duree": 5}
    await coordinator.set_actif(True)
    coordinator._reveil_en_cours = True
    coordinator._statut = "ringing"

    debut = asyncio.get_event_loop().time()
    await coordinator.snooze()
    ecoule = asyncio.get_event_loop().time() - debut

    assert ecoule < 1, f"snooze() a bloqué {ecoule:.1f} s"
    assert coordinator._cancel_snooze is not None


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
    """Le saut annule la sonnerie de l'occurrence visée."""
    await coordinator.set_actif(True)
    await coordinator.sauter_prochain()
    assert coordinator._skip_date is not None
    vise = datetime.combine(coordinator._skip_date, dtime(7, 0))
    assert coordinator._sonne_aujourd_hui(vise) is False


@pytest.mark.asyncio
async def test_skip_ne_vaut_que_pour_l_occurrence_visee(coordinator):
    """Régression : le saut n'était jamais consommé, donc le réveil ne
    sonnait plus jamais. stop(), seul à remettre le drapeau à zéro, n'était
    plus atteint puisque le réveil ne sonnait pas."""
    await coordinator.set_actif(True)
    await coordinator.sauter_prochain()
    saute = coordinator._skip_date

    # Une semaine plus tard, un jour ouvré doit de nouveau sonner
    plus_tard = datetime.combine(saute, dtime(7, 0)) + timedelta(days=7)
    while plus_tard.weekday() > 4:
        plus_tard += timedelta(days=1)
    assert coordinator._sonne_aujourd_hui(plus_tard) is True


@pytest.mark.asyncio
async def test_skip_consomme_apres_l_occurrence(coordinator):
    """Le drapeau doit être libéré par la boucle de rafraîchissement une
    fois l'occurrence sautée passée."""
    await coordinator.set_actif(True)
    await coordinator.sauter_prochain()
    assert coordinator.skip_prochain is True

    # Simule le lendemain de l'occurrence sautée
    coordinator._skip_date = (datetime.now() - timedelta(days=1)).date()
    await coordinator._async_update_data()
    assert coordinator.skip_prochain is False
    assert coordinator._skip_date is None


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

# ── Régression : cycle de réveil ───────────────────────────────

@pytest.mark.asyncio
async def test_executer_cycle_ne_leve_pas_unbound_local(coordinator):
    """Régression : cfg était utilisé avant son affectation dans
    _executer_cycle, ce qui levait UnboundLocalError et interrompait le
    réveil juste après le passage au statut ringing."""
    await coordinator.set_actif(True)
    await coordinator._executer_cycle()
    assert coordinator.statut == "ringing"


@pytest.mark.asyncio
async def test_executer_cycle_incremente_les_stats(coordinator):
    """Le compteur de déclenchements doit être incrémenté : il était
    inatteignable à cause de l'UnboundLocalError. _stats est créé
    paresseusement par _increment_stat."""
    await coordinator.set_actif(True)
    await coordinator._executer_cycle()
    assert coordinator._stats["total_declenchements"] == 1


@pytest.mark.asyncio
async def test_executer_cycle_emet_l_evenement(coordinator):
    """L'événement smartwake_triggered n'était jamais émis."""
    await coordinator.set_actif(True)
    with patch.object(coordinator, "_fire_event") as fire:
        await coordinator._executer_cycle()
    types = [c.args[0] for c in fire.call_args_list]
    assert "smartwake_triggered" in types


# ── Régression : écriture des entités number ───────────────────

@pytest.mark.asyncio
async def test_set_config_value(coordinator):
    """set_config_value doit persister la valeur dans la config entry."""
    await coordinator.set_actif(True)
    await coordinator.set_config_value("aube_min", 30)
    assert coordinator.config["aube_min"] == 30


@pytest.mark.asyncio
async def test_number_set_native_value(coordinator):
    """Régression : ReveilNumber.async_set_native_value référençait
    self.entry, jamais assigné, d'où AttributeError. Les 10 sliders
    étaient en lecture seule."""
    _stub_number_module()
    from custom_components.smartwake.number import ReveilNumber, NUMBERS

    desc = next(d for d in NUMBERS if d.key == "aube_min")
    ent = ReveilNumber(coordinator, coordinator.entry, desc)
    ent.hass = coordinator.hass

    await ent.async_set_native_value(25)
    assert coordinator.config["aube_min"] == 25
    assert ent.native_value == 25


@pytest.mark.asyncio
async def test_number_step_entier_stocke_un_int(coordinator):
    """Un step entier ne doit pas produire 25.0 dans la config."""
    _stub_number_module()
    from custom_components.smartwake.number import ReveilNumber, NUMBERS

    desc = next(d for d in NUMBERS if d.key == "aube_min")
    ent = ReveilNumber(coordinator, coordinator.entry, desc)
    ent.hass = coordinator.hass

    await ent.async_set_native_value(25.0)
    assert isinstance(coordinator.config["aube_min"], int)


@pytest.mark.asyncio
async def test_number_volume_reste_flottant(coordinator):
    """Un step fractionnaire (0.01) doit conserver la précision."""
    _stub_number_module()
    from custom_components.smartwake.number import ReveilNumber, NUMBERS

    desc = next(d for d in NUMBERS if d.key == "volume_final")
    ent = ReveilNumber(coordinator, coordinator.entry, desc)
    ent.hass = coordinator.hass

    await ent.async_set_native_value(0.42)
    assert coordinator.config["volume_final"] == pytest.approx(0.42)


# ── Garde-fou : aucun nom non défini dans le composant ─────────

def test_aucun_nom_non_defini():
    """Régression : v2.6.0 utilisait 10 constantes sans les importer
    (CONF_MODE_HEURE, CONF_HEURE_LUNDI…, CONF_MODE_VACANCES_ENTITY,
    CONF_AI_CUSTOM_TASKS, CONF_WEATHER_ENTITY), ce qui faisait planter
    l'écran d'options « Base » par NameError.

    Ce test relit tous les modules et vérifie qu'aucun nom global n'est
    utilisé sans être importé ou défini.
    """
    import ast
    import glob
    import os

    import builtins as _b

    builtins_ok = set(dir(_b))
    # Variables spéciales fournies par l'interpréteur à chaque module
    builtins_ok |= {
        "__file__", "__name__", "__doc__", "__package__", "__spec__",
        "__loader__", "__builtins__", "__debug__",
    }

    erreurs = []
    base = os.path.join("custom_components", "smartwake")
    for path in sorted(glob.glob(os.path.join(base, "*.py"))):
        tree = ast.parse(open(path, encoding="utf-8").read())

        disponibles = set(builtins_ok)
        # imports
        for n in ast.walk(tree):
            if isinstance(n, (ast.Import, ast.ImportFrom)):
                for a in n.names:
                    disponibles.add(a.asname or a.name.split(".")[0])
        # affectations, fonctions, classes, args au niveau module et local
        for n in ast.walk(tree):
            if isinstance(n, ast.Assign):
                for t in n.targets:
                    for sub in ast.walk(t):
                        if isinstance(sub, ast.Name):
                            disponibles.add(sub.id)
            elif isinstance(n, (ast.AnnAssign, ast.AugAssign)):
                if isinstance(n.target, ast.Name):
                    disponibles.add(n.target.id)
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                disponibles.add(n.name)
                for a in list(n.args.args) + list(n.args.kwonlyargs) + list(n.args.posonlyargs):
                    disponibles.add(a.arg)
                if n.args.vararg:
                    disponibles.add(n.args.vararg.arg)
                if n.args.kwarg:
                    disponibles.add(n.args.kwarg.arg)
            elif isinstance(n, ast.ClassDef):
                disponibles.add(n.name)
            elif isinstance(n, ast.ExceptHandler) and n.name:
                disponibles.add(n.name)
            elif isinstance(n, (ast.For, ast.AsyncFor)):
                for sub in ast.walk(n.target):
                    if isinstance(sub, ast.Name):
                        disponibles.add(sub.id)
            elif isinstance(n, ast.comprehension):
                for sub in ast.walk(n.target):
                    if isinstance(sub, ast.Name):
                        disponibles.add(sub.id)
            elif isinstance(n, ast.withitem) and n.optional_vars is not None:
                for sub in ast.walk(n.optional_vars):
                    if isinstance(sub, ast.Name):
                        disponibles.add(sub.id)
            elif isinstance(n, ast.Lambda):
                for a in list(n.args.args) + list(n.args.kwonlyargs):
                    disponibles.add(a.arg)
            elif isinstance(n, ast.NamedExpr) and isinstance(n.target, ast.Name):
                disponibles.add(n.target.id)

        for n in ast.walk(tree):
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
                if n.id not in disponibles:
                    erreurs.append(f"{os.path.basename(path)}:{n.lineno} {n.id}")

    assert not erreurs, "noms non définis :\n" + "\n".join(erreurs)


# ── Garde-fou : traductions du menu d'options ─────────────────

def test_menu_options_traduits():
    """Régression : async_show_menu listait 7 sections mais
    options.step.init.menu_options était absent des traductions, donc le
    menu s'affichait sans aucun libellé."""
    import ast
    import json

    src = open("custom_components/smartwake/config_flow.py", encoding="utf-8").read()
    tree = ast.parse(src)

    attendues = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                and n.func.attr == "async_show_menu":
            for kw in n.keywords:
                if kw.arg == "menu_options" and isinstance(kw.value, ast.List):
                    for elt in kw.value.elts:
                        if isinstance(elt, ast.Constant):
                            attendues.add(elt.value)
    assert attendues, "aucun menu_options trouvé dans config_flow"

    for fichier in ("strings.json", "translations/fr.json"):
        tr = json.load(open(f"custom_components/smartwake/{fichier}", encoding="utf-8"))
        menu = tr["options"]["step"]["init"].get("menu_options", {})
        manquants = sorted(attendues - set(menu))
        assert not manquants, f"{fichier} : sections sans libellé {manquants}"


def test_champs_options_traduits():
    """Chaque champ des formulaires d'options doit avoir un libellé,
    sinon l'utilisateur voit une clé brute ou un champ sans nom."""
    import ast
    import json

    const = {}
    for n in ast.walk(ast.parse(open("custom_components/smartwake/const.py", encoding="utf-8").read())):
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name) and isinstance(n.value, ast.Constant):
                    const[t.id] = n.value.value

    tree = ast.parse(open("custom_components/smartwake/config_flow.py", encoding="utf-8").read())

    for fichier in ("strings.json", "translations/fr.json"):
        tr = json.load(open(f"custom_components/smartwake/{fichier}", encoding="utf-8"))
        steps = tr["options"]["step"]
        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef) or not node.name.startswith("async_step_"):
                continue
            step = node.name[len("async_step_"):]
            if step not in steps:
                continue
            champs = []
            for n in ast.walk(node):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                        and n.func.attr in ("Optional", "Required"):
                    a = n.args[0] if n.args else None
                    if isinstance(a, ast.Name) and a.id in const:
                        champs.append(const[a.id])
                    elif isinstance(a, ast.Constant):
                        champs.append(a.value)
            libelles = set(steps[step].get("data", {}))
            manquants = [c for c in champs if c not in libelles]
            assert not manquants, f"{fichier} étape '{step}' : champs sans libellé {manquants}"


# ── Régression : armement des déclencheurs ─────────────────────

@pytest.mark.asyncio
async def test_triggers_armes_au_demarrage(coordinator):
    """Régression : async_config_entry_first_refresh calculait _prochain mais
    n'appelait jamais _planifier_trigger. Après un redémarrage de HA, aucun
    déclencheur n'était enregistré et le réveil ne sonnait pas."""
    # Le mock HA n'expose ni bus d'événements ni Store
    coordinator.hass.bus = MagicMock()
    coordinator.hass.bus.async_listen = MagicMock(return_value=lambda: None)

    _stub_storage_module()
    from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

    coordinator._actif = True

    # On enregistre l'ordre des appels : l'armement doit précéder le premier
    # rafraîchissement, sinon c'est le filet de sécurité qui le rattrape.
    ordre = []
    plan_reel = coordinator._planifier_trigger
    super_reel = DataUpdateCoordinator.async_config_entry_first_refresh

    def _plan():
        ordre.append("armement")
        plan_reel()

    async def _super(self):
        ordre.append("refresh")
        return await super_reel(self)

    with patch.object(coordinator, "_planifier_trigger", _plan), \
            patch.object(DataUpdateCoordinator, "async_config_entry_first_refresh", _super):
        await coordinator.async_config_entry_first_refresh()

    assert "armement" in ordre, "_planifier_trigger n'est jamais appelé au démarrage"
    assert ordre.index("armement") < ordre.index("refresh"), (
        f"l'armement doit avoir lieu au setup, pas via le filet de sécurité : {ordre}"
    )
    assert coordinator._cancel_trigger is not None


@pytest.mark.asyncio
async def test_planification_calee_sur_prochain(coordinator):
    """Le déclencheur doit viser exactement _prochain.

    Régression : async_track_time_change posait un déclencheur par heure
    configurée, sans vérifier le jour. En mode « heure par jour », l'heure du
    lundi sonnait donc aussi le mardi. Le décalage par agenda adaptatif et par
    par l'agenda adaptatif était également ignoré.
    """
    import custom_components.smartwake.coordinator as coord_mod

    points = []
    original = coord_mod.async_track_point_in_time

    def _spy(hass, cb, point):
        points.append(point)
        return original(hass, cb, point)

    coord_mod.async_track_point_in_time = _spy
    try:
        await coordinator.set_actif(True)
    finally:
        coord_mod.async_track_point_in_time = original

    assert coordinator._prochain in points, (
        f"le déclencheur ne vise pas _prochain ({coordinator._prochain}) : {points}"
    )


@pytest.mark.asyncio
async def test_heure_par_jour_ne_sonne_pas_les_autres_jours(coordinator):
    """En mode par_jour, _prochain doit porter l'heure du bon jour."""
    await coordinator.set_config_value("mode_heure", "par_jour")
    await coordinator.set_config_value("jours", "tous")
    for cle, val in (
        ("heure_lundi", "06:00"), ("heure_mardi", "07:00"),
        ("heure_mercredi", "07:00"), ("heure_jeudi", "07:00"),
        ("heure_vendredi", "07:00"), ("heure_samedi", "08:30"),
        ("heure_dimanche", "08:30"),
    ):
        await coordinator.set_config_value(cle, val)

    await coordinator.set_actif(True)
    prochain = coordinator.prochain_reveil
    assert prochain is not None

    attendu = {
        0: (6, 0), 1: (7, 0), 2: (7, 0), 3: (7, 0),
        4: (7, 0), 5: (8, 30), 6: (8, 30),
    }[prochain.weekday()]
    assert (prochain.hour, prochain.minute) == attendu, (
        f"{prochain} ne correspond pas à l'heure du jour {prochain.weekday()}"
    )


@pytest.mark.asyncio
async def test_trigger_consomme_est_rearme(coordinator):
    """Le déclencheur étant à usage unique, la boucle de rafraîchissement doit
    le réarmer s'il a été consommé sans démarrer de cycle."""
    await coordinator.set_actif(True)
    coordinator._cancel_trigger = None
    await coordinator._async_update_data()
    assert coordinator._cancel_trigger is not None


# ── Régression : écriture de config sans rechargement ──────────

@pytest.mark.asyncio
async def test_ecriture_entite_ne_declenche_pas_de_rechargement(coordinator):
    """Régression : chaque écriture dans entry.data déclenchait l'update
    listener, donc async_reload, donc un nouveau coordinator avec actif=False.
    Bouger un curseur désarmait le réveil.
    """
    await coordinator.set_actif(True)
    await coordinator.set_config_value("aube_min", 30)
    # Le drapeau doit signaler une écriture interne, donc pas de rechargement
    assert coordinator.consume_internal_update() is True
    # et il ne doit être consommé qu'une fois
    assert coordinator.consume_internal_update() is False
    assert coordinator.actif is True


@pytest.mark.asyncio
async def test_reste_actif_apres_modification_de_reglages(coordinator):
    """L'enchaînement complet ne doit pas désarmer le réveil."""
    await coordinator.set_actif(True)
    for cle, val in (("aube_min", 25), ("snooze_duree", 8), ("volume_final", 0.5)):
        await coordinator.set_config_value(cle, val)
    await coordinator.set_heure("06:45")
    await coordinator.set_jours("tous")

    assert coordinator.actif is True
    assert coordinator._cancel_trigger is not None
    assert coordinator.config["aube_min"] == 25
    assert coordinator.config["heure"] == "06:45"


# ── Régression : APIs Home Assistant invalides ─────────────────

def test_aucune_api_de_suivi_supprimee():
    """Régression : _ouvrir_volets_au_lever importait async_track_state_change,
    retirée de Home Assistant. L'ImportError survenait dans une tâche, si bien
    que les volets ne s'ouvraient jamais quand le soleil était sous l'horizon.
    """
    import re

    src = open("custom_components/smartwake/coordinator.py", encoding="utf-8").read()
    # async_track_state_change_event est la forme valide ; la forme sans
    # suffixe _event n'existe plus. On ne cible que les appels et les imports,
    # pas les mentions en commentaire.
    appels = re.findall(r"async_track_state_change(?!_event)\s*\(", src)
    imports = re.findall(r"import[^\n]*\basync_track_state_change(?!_event)\b", src)
    assert not appels and not imports, (
        f"{len(appels)} appel(s) et {len(imports)} import(s) de "
        "async_track_state_change (API supprimée de Home Assistant)"
    )


def test_aucun_event_type_state_changed_suffixe():
    """Régression : le bus écoutait « state_changed.<entité> », un event_type
    qui n'existe pas. L'arrêt par mouvement salle de bain était du code mort."""
    src = open("custom_components/smartwake/coordinator.py", encoding="utf-8").read()
    assert 'async_listen(f"state_changed.' not in src
    assert 'async_listen("state_changed.' not in src


@pytest.mark.asyncio
async def test_mouvement_stop_utilise_le_suivi_d_etat(coordinator):
    """L'arrêt par mouvement doit s'abonner via async_track_state_change_event
    et conserver son désabonnement (il était rappelé à chaque cycle)."""
    import custom_components.smartwake.coordinator as coord_mod

    coordinator.entry.data = {**coordinator.entry.data,
                              "mouvement_sdb": "binary_sensor.mouvement_sdb"}
    appels = []

    def _spy(hass, entities, cb):
        appels.append(entities)
        return lambda: appels.append("unsub")

    original = coord_mod.async_track_state_change_event
    coord_mod.async_track_state_change_event = _spy
    try:
        coordinator._setup_mouvement_stop()
        assert appels == [["binary_sensor.mouvement_sdb"]]
        assert coordinator._cancel_mouvement is not None
        # Un second appel ne doit pas empiler d'écouteur
        coordinator._setup_mouvement_stop()
        assert "unsub" in appels
    finally:
        coord_mod.async_track_state_change_event = original


# ── Régression : ordre des actions du cycle ────────────────────

@pytest.mark.asyncio
async def test_notification_envoyee_avant_les_rampes(coordinator):
    """Régression : la notification actionnable était envoyée après la musique
    et la rampe de lumière, qui bloquent ~5 et ~19 min. Les boutons
    Snooze/Stop n'arrivaient qu'environ 25 min après le début de la sonnerie.
    """
    coordinator.entry.data = {
        **coordinator.entry.data,
        "notification_activee": True,
        "notify_device": "notify.mobile_app_test",
        "musique_activee": True,
        "media_player": "media_player.chambre",
        "lumiere_activee": True,
        "lumiere": "light.chambre",
    }
    ordre = []

    async def _notif():
        ordre.append("notification")

    async def _musique():
        ordre.append("musique")

    async def _lumiere():
        ordre.append("lumiere")

    with patch.object(coordinator, "_envoyer_notification", _notif), \
            patch.object(coordinator, "_demarrer_musique", _musique), \
            patch.object(coordinator, "_cycle_lumiere_progressive", _lumiere), \
            patch.object(coordinator, "_escalade", AsyncMock()), \
            patch.object(coordinator, "_ouvrir_volets", AsyncMock()):
        await coordinator._executer_cycle()
        await asyncio.sleep(0)  # laisse les rampes démarrer

    assert ordre[0] == "notification", f"ordre observé : {ordre}"


@pytest.mark.asyncio
async def test_escalade_programmee_une_seule_fois(coordinator):
    """Régression : l'escalade était programmée deux fois. La première tâche
    devenait orpheline dans _cancel_escalade et n'était donc plus annulable
    par stop(), d'où un doublement du volume et des événements."""
    escalade = AsyncMock()
    with patch.object(coordinator, "_escalade", escalade), \
            patch.object(coordinator, "_envoyer_notification", AsyncMock()):
        await coordinator._executer_cycle()

    assert escalade.call_count == 1, f"escalade lancée {escalade.call_count} fois"


@pytest.mark.asyncio
async def test_stop_annule_les_rampes(coordinator):
    """stop() doit annuler les rampes parallèles, sinon la montée de volume
    continuait après l'arrêt."""
    async def _longue():
        await asyncio.sleep(3600)

    coordinator._reveil_en_cours = True
    tache = asyncio.ensure_future(_longue())
    coordinator._cancel_rampes = [tache]

    await coordinator.stop()
    await asyncio.sleep(0)

    assert tache.cancelled() or tache.done()
    assert coordinator._cancel_rampes == []


# ── Régression : appel TTS ─────────────────────────────────────

@pytest.mark.asyncio
async def test_tts_cible_le_moteur_et_pas_l_enceinte(coordinator):
    """Régression : tts.speak recevait l'enceinte (media_player) comme
    entity_id et omettait media_player_entity_id, pourtant requis. L'appel
    était rejeté et le briefing vocal ne fonctionnait jamais."""
    coordinator.entry.data = {
        **coordinator.entry.data,
        "tts_entity": "media_player.chambre",
        "tts_engine": "tts.piper",
    }
    # Le mock HA n'accepte pas le paramètre blocking
    appels = []

    async def _call(domain, service, data=None, **kw):
        appels.append((domain, service, data or {}, kw))

    coordinator.hass.services.async_call = _call

    await coordinator._tts_speak("Bonjour")

    tts = [a for a in appels if a[0] == "tts"]
    assert len(tts) == 1, f"appels observés : {appels}"
    _, service, data, kw = tts[0]
    assert service == "speak"
    assert data["entity_id"] == "tts.piper", "la cible doit être le moteur tts"
    assert data["media_player_entity_id"] == "media_player.chambre"
    assert data["message"] == "Bonjour"
    assert kw.get("blocking") is True, "l'appel doit être bloquant pour remonter l'échec"


@pytest.mark.asyncio
async def test_tts_sans_moteur_ne_plante_pas(coordinator):
    """Sans moteur configuré ni détectable, l'appel doit être ignoré
    proprement plutôt que d'échouer."""
    coordinator.entry.data = {
        **coordinator.entry.data,
        "tts_entity": "media_player.chambre",
    }
    coordinator.hass.states.async_all = lambda domain=None: []
    appels = []

    async def _call(domain, service, data=None, **kw):
        appels.append(domain)

    coordinator.hass.services.async_call = _call

    await coordinator._tts_speak("Bonjour")

    assert "tts" not in appels


# ── Régression : appels de services Home Assistant ─────────────

def test_tous_les_appels_de_service_sont_bloquants():
    """Régression : aucun appel n'utilisait blocking=True. Un appel non
    bloquant ne remonte pas l'échec du service cible, si bien que les blocs
    except et les boucles de reprise (3 tentatives musique, 2 volets) ne
    pouvaient rien détecter : musique_ok passait à True dès la première
    itération même avec un media_player injoignable.
    """
    import ast

    src = open("custom_components/smartwake/coordinator.py", encoding="utf-8").read()
    manquants = []
    for node in ast.walk(ast.parse(src)):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr != "async_call":
            continue
        if not (isinstance(node.func.value, ast.Attribute)
                and node.func.value.attr == "services"):
            continue
        if not any(k.arg == "blocking" for k in node.keywords):
            manquants.append(node.lineno)

    assert not manquants, f"appels sans blocking=True aux lignes {manquants}"


def test_appels_ia_bloquants_avec_return_response():
    """Régression : return_response=True sans blocking=True lève
    ServiceValidationError côté Home Assistant. L'exception étant capturée,
    toutes les fonctions IA échouaient silencieusement."""
    import ast

    src = open("custom_components/smartwake/ai.py", encoding="utf-8").read()
    for node in ast.walk(ast.parse(src)):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr != "async_call":
            continue
        kw = {k.arg for k in node.keywords}
        if "return_response" in kw:
            assert "blocking" in kw, (
                f"ligne {node.lineno} : return_response exige blocking=True"
            )


def test_notification_avec_actions_passe_par_le_service_historique():
    """Régression : l'entity service notify.send_message n'accepte que
    message et title. Passer une clé data — donc des boutons d'action — fait
    échouer la validation, si bien que la notification actionnable ne partait
    jamais."""
    src = open("custom_components/smartwake/coordinator.py", encoding="utf-8").read()
    # Un seul appel à send_message doit subsister (le repli sans actions)
    assert src.count('"notify", "send_message"') == 1
    # et il ne doit pas transporter de clé data
    bloc = src[src.index('"notify", "send_message"'):]
    bloc = bloc[:bloc.index(")")]
    assert '"data"' not in bloc and "charge" not in bloc


@pytest.mark.asyncio
async def test_notification_actionnable_utilise_le_service_legacy(coordinator):
    """Avec des actions, l'appel doit viser notify.<service>, pas l'entity
    service."""
    coordinator.entry.data = {
        **coordinator.entry.data,
        "notify_device": "notify.mobile_app_test",
    }
    appels = []

    async def _call(domain, service, data=None, **kw):
        appels.append((domain, service, data or {}))

    coordinator.hass.services.async_call = _call
    coordinator.hass.services.has_service = lambda d, s: s == "mobile_app_test"

    await coordinator._envoyer_notification()

    assert len(appels) == 1
    domain, service, data = appels[0]
    assert (domain, service) == ("notify", "mobile_app_test")
    assert "actions" in data["data"], "les boutons doivent être transmis"
    assert "entity_id" not in data


# ── Régression : escalade et snooze ────────────────────────────

@pytest.mark.asyncio
async def test_escalade_ignoree_pendant_un_snooze(coordinator):
    """Régression : l'escalade ne testait que _reveil_en_cours, vrai aussi
    pendant un snooze. Avec les valeurs par défaut (snooze 5 min, escalade
    5 min), les lumières passaient à 100 % en pleine période de snooze."""
    coordinator._reveil_en_cours = True
    coordinator._statut = "snoozed"
    assert coordinator._escalade_pertinente() is False

    coordinator._statut = "ringing"
    assert coordinator._escalade_pertinente() is True


# ── Régression : luminosité progressive ────────────────────────

@pytest.mark.asyncio
async def test_lumiere_atteint_la_luminosite_reglee(coordinator):
    """Régression : la rampe envoyait 20 fois brightness_step_pct: 1, soit
    20 % au total quel que soit le réglage « Luminosité max »."""
    coordinator.entry.data = {
        **coordinator.entry.data,
        "lumiere": "light.chambre",
        "lumiere_activee": True,
        "brightness_max": 200,
        "duree_progressive": 1,
    }
    appels = []

    async def _call(domain, service, data=None, **kw):
        appels.append(data or {})

    coordinator.hass.services.async_call = _call

    await coordinator._cycle_lumiere_progressive()

    assert appels, "aucun appel émis"
    assert all("brightness" in a for a in appels), "doit viser une valeur absolue"
    assert not any("brightness_step_pct" in a for a in appels)
    assert appels[-1]["brightness"] == 200, (
        f"la rampe doit finir à 200, obtenu {appels[-1]['brightness']}"
    )
    # Progression monotone
    valeurs = [a["brightness"] for a in appels]
    assert valeurs == sorted(valeurs)


# ── Régression : passage de minuit ─────────────────────────────

def test_ecart_lever_gere_le_passage_minuit():
    """Régression : un stop à 00:10 pour un réveil programmé à 23:50 donnait
    −1420 min au lieu de +20."""
    _stub_storage_module()
    from custom_components.smartwake.learning import LearningManager

    reel = datetime(2026, 7, 15, 0, 10)
    assert LearningManager._ecart_minutes("23:50", reel) == pytest.approx(20)

    reel2 = datetime(2026, 7, 15, 23, 50)
    assert LearningManager._ecart_minutes("00:10", reel2) == pytest.approx(-20)

    reel3 = datetime(2026, 7, 15, 7, 12)
    assert LearningManager._ecart_minutes("07:00", reel3) == pytest.approx(12)


# ── Régression : migration des config entries ──────────────────

def test_migration_declaree():
    """Régression : le config flow déclare VERSION = 3 depuis la 2.5.0, contre
    2 auparavant. Sans async_migrate_entry, Home Assistant refuse de charger
    toute entrée créée avant cette version (« Migration handler not found ») et
    l'intégration ne démarre pas du tout.
    """
    import custom_components.smartwake as pkg

    assert hasattr(pkg, "async_migrate_entry"), (
        "async_migrate_entry est obligatoire dès que VERSION a été incrémentée"
    )


def test_version_de_schema_unique():
    """La version doit être partagée pour que le config flow et la migration
    ne puissent pas diverger."""
    import ast

    from custom_components.smartwake.const import SCHEMA_VERSION

    src = open("custom_components/smartwake/config_flow.py", encoding="utf-8").read()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "VERSION":
                    assert isinstance(node.value, ast.Name), (
                        "VERSION doit référencer SCHEMA_VERSION, pas un littéral"
                    )
                    assert node.value.id == "SCHEMA_VERSION"
    assert isinstance(SCHEMA_VERSION, int) and SCHEMA_VERSION >= 3


@pytest.mark.asyncio
async def test_migration_releve_la_version(coordinator):
    """Une entrée en schéma 2 doit être relevée sans perte de données."""
    from custom_components.smartwake import async_migrate_entry
    from custom_components.smartwake.const import SCHEMA_VERSION

    entry = coordinator.entry
    entry.version = 2
    entry.minor_version = 1
    donnees = dict(entry.data)

    maj = {}

    def _update(e, **kw):
        maj.update(kw)
        if "version" in kw:
            e.version = kw["version"]
        if "data" in kw:
            e.data = kw["data"]

    coordinator.hass.config_entries.async_update_entry = _update

    assert await async_migrate_entry(coordinator.hass, entry) is True
    assert maj.get("version") == SCHEMA_VERSION
    assert entry.data == donnees, "la migration ne doit rien perdre"


@pytest.mark.asyncio
async def test_migration_refuse_un_schema_plus_recent(coordinator):
    """Une entrée écrite par une version future ne doit pas être chargée."""
    from custom_components.smartwake import async_migrate_entry
    from custom_components.smartwake.const import SCHEMA_VERSION

    coordinator.entry.version = SCHEMA_VERSION + 1
    assert await async_migrate_entry(coordinator.hass, coordinator.entry) is False


# ── Régression : pas de valeur personnelle codée en dur ────────

def test_aucun_destinataire_code_en_dur():
    """Régression : DEFAULT_NOTIFY_DEVICE désignait un téléphone précis
    (notify.mobile_app_sm_g991u1). Une installation sans appareil détecté
    envoyait ses notifications à un service inexistant."""
    import re

    from custom_components.smartwake import const

    assert const.DEFAULT_NOTIFY_DEVICE == ""
    src = open("custom_components/smartwake/const.py", encoding="utf-8").read()
    assert not re.search(r"mobile_app_[a-z0-9_]+", src), (
        "aucun identifiant d'appareil personnel ne doit subsister"
    )


# ── Régression : champs facultatifs laissés vides ──────────────

def test_aucun_selecteur_avec_default_vide():
    """Régression : « Entity is neither a valid entity ID nor a valid UUID ».

    Les champs d'entité étaient déclarés `vol.Optional(KEY, default=... or "")`.
    Les sélecteurs d'entité, de média, d'heure, de nombre et de liste refusent
    tous la chaîne vide, et voluptuous applique le `default` même lorsque
    l'utilisateur laisse le champ vide : impossible de ne pas renseigner un
    équipement. Le pré-remplissage doit passer par `suggested_value`.
    """
    import ast

    src = open("custom_components/smartwake/config_flow.py", encoding="utf-8").read()
    fautifs = []
    for node in ast.walk(ast.parse(src)):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr not in ("Optional", "Required"):
            continue
        for kw in node.keywords:
            if kw.arg != "default":
                continue
            # default="" littéral, ou `data.get(...) or ""`
            v = kw.value
            vide = (isinstance(v, ast.Constant) and v.value == "") or (
                isinstance(v, ast.BoolOp)
                and isinstance(v.op, ast.Or)
                and isinstance(v.values[-1], ast.Constant)
                and v.values[-1].value == ""
            )
            if vide:
                fautifs.append(node.lineno)

    assert not fautifs, (
        f"default vide aux lignes {fautifs} : un sélecteur refusera la chaîne vide"
    )


def test_options_utilisent_suggested_values():
    """Le pré-remplissage doit passer par add_suggested_values_to_schema,
    seule méthode qui n'intervient pas dans la validation."""
    src = open("custom_components/smartwake/config_flow.py", encoding="utf-8").read()
    assert "add_suggested_values_to_schema" in src


def test_fusion_efface_les_champs_vides():
    """Régression : la fusion `{**data, **user_input}` conservait l'ancienne
    valeur d'un champ vidé, rendant impossible le retrait d'un équipement
    une fois renseigné.

    Une clé du schéma sans valeur par défaut, absente de la saisie, doit être
    supprimée de la configuration ; les clés hors de la section doivent rester.
    """
    import voluptuous as vol

    from custom_components.smartwake.config_flow import SmartWAKEOptionsFlow

    class _Entry:
        def __init__(self, data):
            self.data = dict(data)
            self.entry_id = "e1"
            self.title = "Reveil"

    class _CE:
        def async_update_entry(self, entry, data=None, **kw):
            entry.data = dict(data)

    class _Hass:
        def __init__(self):
            self.config_entries = _CE()

    entry = _Entry({"heure": "07:00", "chauffe_eau": "switch.ballon",
                    "cafetiere": "switch.cafe"})
    flow = SmartWAKEOptionsFlow(entry)
    flow.hass = _Hass()

    schema = vol.Schema({
        vol.Optional("chauffe_eau"): str,
        vol.Optional("cafetiere"): str,
        vol.Optional("volets_soleil", default=True): bool,
    })

    # L'utilisateur vide chauffe_eau et conserve cafetiere
    flow._enregistrer({"cafetiere": "switch.cafe", "volets_soleil": True}, schema)

    assert "chauffe_eau" not in entry.data, "le champ vidé doit être effacé"
    assert entry.data["cafetiere"] == "switch.cafe"
    assert entry.data["heure"] == "07:00", "les clés hors section doivent rester"
    assert entry.data["volets_soleil"] is True


# ── Bilan de sommeil : lecture des capteurs configurés ─────────

@pytest.mark.asyncio
async def test_bilan_sans_capteur_configure(coordinator):
    """Sans capteur désigné, le résumé est vide et le bilan reste possible."""
    from custom_components.smartwake.ai import _resume_capteurs_sommeil

    assert await _resume_capteurs_sommeil(coordinator.hass, {}) == ""
    assert await _resume_capteurs_sommeil(
        coordinator.hass, {"sommeil_sensors": []}
    ) == ""


@pytest.mark.asyncio
async def test_bilan_lit_les_capteurs_de_sommeil(coordinator):
    """Régression : le bilan hebdomadaire ne recevait que le compteur de
    snoozes et l'historique des levers. Il commentait donc le sommeil sans
    disposer d'aucune mesure. Les capteurs désignés dans les options doivent
    apparaître dans les instructions envoyées à l'IA."""
    from custom_components.smartwake.ai import _resume_capteurs_sommeil

    coordinator.hass.states.set(
        "sensor.score", "78",
        {"friendly_name": "Sleep score", "unit_of_measurement": "%"},
    )
    coordinator.hass.states.set(
        "sensor.profond", "5400",
        {"friendly_name": "Sommeil profond", "unit_of_measurement": "s"},
    )

    resume = await _resume_capteurs_sommeil(
        coordinator.hass,
        {"sommeil_sensors": ["sensor.score", "sensor.profond"]},
    )

    assert "Sleep score" in resume
    assert "78%" in resume
    # Les durées en secondes doivent être rendues lisibles
    assert "1 h 30" in resume, f"durée non convertie : {resume}"
    assert "5400" not in resume


@pytest.mark.asyncio
async def test_bilan_ignore_les_capteurs_indisponibles(coordinator):
    """Un capteur hors service ne doit pas polluer le prompt."""
    from custom_components.smartwake.ai import _resume_capteurs_sommeil

    coordinator.hass.states.set("sensor.ok", "80", {"friendly_name": "Score"})
    coordinator.hass.states.set("sensor.hs", "unavailable", {"friendly_name": "HS"})

    resume = await _resume_capteurs_sommeil(
        coordinator.hass, {"sommeil_sensors": ["sensor.ok", "sensor.hs"]}
    )
    assert "Score" in resume
    assert "HS" not in resume
    assert "unavailable" not in resume


@pytest.mark.asyncio
async def test_bilan_transmet_les_mesures_a_l_ia(coordinator):
    """Les mesures doivent bien arriver dans les instructions du prompt."""
    from custom_components.smartwake import ai

    coordinator.hass.states.set(
        "sensor.score", "78",
        {"friendly_name": "Sleep score", "unit_of_measurement": "%"},
    )
    captures = {}

    async def _faux_appel(hass, task_name, instructions, *a, **kw):
        captures["instructions"] = instructions
        return {"data": "bilan"}

    with patch.object(ai, "_call_ai_task", _faux_appel):
        res = await ai.generate_weekly_report(
            coordinator.hass,
            {"ai_bilan_hebdo": True, "sommeil_sensors": ["sensor.score"]},
            2, "07:05 en moyenne",
        )

    assert res == "bilan"
    assert "Sleep score" in captures["instructions"]
    assert "78%" in captures["instructions"]


# ── Présence au lit : capteurs multiples au lieu de la caméra ──

def test_plus_de_verification_par_camera():
    """La vérification du lever reposait sur une analyse d'image par l'IA :
    coûteuse, lente, dépendante de la luminosité, et discutable dans une
    chambre. Elle s'appuie désormais sur les capteurs de présence au lit."""
    src = open("custom_components/smartwake/ai.py", encoding="utf-8").read()
    assert "CONF_AI_CAMERA_VERIF" not in src
    assert "media-source://camera" not in src

    flow = open("custom_components/smartwake/config_flow.py", encoding="utf-8").read()
    assert 'CONF_AI_CAMERA_VERIF' not in flow


@pytest.mark.asyncio
async def test_presence_lit_accepte_plusieurs_capteurs(coordinator):
    """Les deux champs Withings figés sont remplacés par une liste ouverte aux
    radars millimétriques et aux capteurs sous matelas."""
    coordinator.entry.data = {
        **coordinator.entry.data,
        "presence_lit_sensors": ["binary_sensor.matelas", "binary_sensor.radar"],
    }
    coordinator.hass.states.set("binary_sensor.matelas", "off")
    coordinator.hass.states.set("binary_sensor.radar", "off")
    assert coordinator._personne_au_lit() is False

    coordinator.hass.states.set("binary_sensor.radar", "on")
    assert coordinator._personne_au_lit() is True


@pytest.mark.asyncio
async def test_presence_lit_capteur_numerique(coordinator):
    """Un capteur de pression ou de poids doit être interprété."""
    coordinator.entry.data = {
        **coordinator.entry.data,
        "presence_lit_sensors": ["sensor.pression"],
    }
    coordinator.hass.states.set("sensor.pression", "0")
    assert coordinator._personne_au_lit() is False
    coordinator.hass.states.set("sensor.pression", "62.5")
    assert coordinator._personne_au_lit() is True


@pytest.mark.asyncio
async def test_presence_lit_ignore_les_indisponibles(coordinator):
    """Un capteur hors service ne doit pas être compris comme une absence."""
    coordinator.entry.data = {
        **coordinator.entry.data,
        "presence_lit_sensors": ["binary_sensor.hs", "binary_sensor.matelas"],
    }
    coordinator.hass.states.set("binary_sensor.hs", "unavailable")
    coordinator.hass.states.set("binary_sensor.matelas", "on")
    assert coordinator._personne_au_lit() is True


@pytest.mark.asyncio
async def test_anciens_champs_withings_toujours_lus(coordinator):
    """Compatibilité : une configuration non encore migrée doit continuer de
    fonctionner."""
    coordinator.entry.data = {
        **coordinator.entry.data,
        "withings_bed_1": "binary_sensor.w1",
    }
    coordinator.hass.states.set("binary_sensor.w1", "on")
    assert "binary_sensor.w1" in coordinator._capteurs_lit()
    assert coordinator._personne_au_lit() is True


@pytest.mark.asyncio
async def test_migration_vers_capteurs_de_presence(coordinator):
    """Les deux champs Withings et la caméra doivent être convertis."""
    from custom_components.smartwake import async_migrate_entry
    from custom_components.smartwake.const import SCHEMA_VERSION

    entry = coordinator.entry
    entry.version = 3
    entry.data = {
        "heure": "07:00",
        "withings_bed_1": "binary_sensor.w1",
        "withings_bed_2": "binary_sensor.w2",
        "ai_camera_verif": "camera.chambre",
    }

    def _update(e, data=None, version=None, **kw):
        if data is not None:
            e.data = dict(data)
        if version is not None:
            e.version = version

    coordinator.hass.config_entries.async_update_entry = _update
    assert await async_migrate_entry(coordinator.hass, entry) is True

    assert entry.data["presence_lit_sensors"] == [
        "binary_sensor.w1", "binary_sensor.w2",
    ]
    assert "withings_bed_1" not in entry.data
    assert "ai_camera_verif" not in entry.data
    assert entry.data["heure"] == "07:00"
    assert entry.version == SCHEMA_VERSION


# ── Suppression de « Phase de sommeil » ────────────────────────

def test_phase_de_sommeil_supprimee():
    """La fonctionnalité est retirée : aucun capteur grand public n'expose la
    phase de sommeil courante.

    Elle lisait un attribut `sleep_state` sur le capteur de présence au lit,
    attribut qu'aucune intégration ne fournit — les capteurs de sommeil
    publient des agrégats au réveil, pas un état pendant la nuit. La condition
    `sleep_state not in ("light", "awake")` était donc toujours vraie et
    l'avance valait systématiquement 0. Le champ n'était de surcroît présent
    dans aucun formulaire : la fonctionnalité était inatteignable.
    """
    import glob
    import os

    for chemin in glob.glob("custom_components/smartwake/*.py"):
        src = open(chemin, encoding="utf-8").read()
        nom = os.path.basename(chemin)
        if nom == "__init__.py":
            continue  # la migration purge légitimement les anciennes clés
        for interdit in ("CONF_SOMMEIL_PHASE", "CONF_SOMMEIL_FENETRE_MIN",
                         "_avance_phase_sommeil", "sleep_state"):
            assert interdit not in src, f"{nom} référence encore {interdit}"


def test_aucun_libelle_orphelin_dans_les_traductions():
    """Un libellé sans champ correspondant encombre les traductions et laisse
    croire que l'option existe encore."""
    import ast
    import glob
    import json

    from custom_components.smartwake import const

    valeurs = {v for k, v in vars(const).items()
               if k.startswith("CONF_") and isinstance(v, str)}

    for chemin in sorted(glob.glob("custom_components/smartwake/strings.json")
                         + glob.glob("custom_components/smartwake/translations/*.json")):
        d = json.load(open(chemin, encoding="utf-8"))

        def _cles(noeud):
            trouve = set()
            if isinstance(noeud, dict):
                for cle, val in noeud.items():
                    if cle in ("data", "data_description") and isinstance(val, dict):
                        trouve |= set(val)
                    trouve |= _cles(val)
            return trouve

        orphelins = sorted(
            c for c in _cles(d)
            # « tache » est un champ transitoire du formulaire de test IA,
            # « name » et « preset » n'existent qu'à la création : aucun n'est
            # une clé de configuration persistée.
            if c not in valeurs and c not in ("name", "preset", "tache")
        )
        assert not orphelins, f"{chemin} : libellés sans champ {orphelins}"


@pytest.mark.asyncio
async def test_migration_purge_la_phase_de_sommeil(coordinator):
    """Les clés stockées doivent disparaître de la configuration."""
    from custom_components.smartwake import async_migrate_entry
    from custom_components.smartwake.const import SCHEMA_VERSION

    entry = coordinator.entry
    entry.version = 4
    entry.data = {"heure": "07:00", "sommeil_phase": True, "sommeil_fenetre_min": 20}

    def _update(e, data=None, version=None, **kw):
        if data is not None:
            e.data = dict(data)
        if version is not None:
            e.version = version

    coordinator.hass.config_entries.async_update_entry = _update
    assert await async_migrate_entry(coordinator.hass, entry) is True

    assert "sommeil_phase" not in entry.data
    assert "sommeil_fenetre_min" not in entry.data
    assert entry.data["heure"] == "07:00"
    assert entry.version == SCHEMA_VERSION


# ── Auto-détection : aucun choix arbitraire ────────────────────

def _faux_hass_avec(etats):
    """Construit un hass minimal exposant les états fournis."""
    class _Etat:
        def __init__(self, entity_id, attributes=None):
            self.entity_id = entity_id
            self.state = "off"
            self.attributes = attributes or {}

    class _States:
        def __init__(self, liste):
            self._liste = liste

        def async_entity_ids(self, domain):
            return [e.entity_id for e in self._liste
                    if e.entity_id.startswith(domain + ".")]

        def async_all(self):
            return self._liste

        def get(self, entity_id):
            return next((e for e in self._liste if e.entity_id == entity_id), None)

    class _Hass:
        def __init__(self, liste):
            self.states = _States(liste)

    return _Hass([_Etat(e, a) for e, a in etats])


@pytest.mark.asyncio
async def test_auto_detection_ignore_garage_et_portail():
    """Régression : l'auto-détection retenait le premier `cover` de la maison à
    défaut de mieux. Une porte de garage ou un portail pouvait donc être
    pré-rempli dans « Volets à ouvrir » et s'ouvrir au réveil."""
    from custom_components.smartwake.config_flow import _auto_detect_entities

    hass = _faux_hass_avec([
        ("cover.porte_garage", {"device_class": "garage"}),
        ("cover.portail", {"device_class": "gate"}),
    ])
    detecte = await _auto_detect_entities(hass)
    assert detecte.get("volets") is None, (
        f"un ouvrant interdit a été proposé : {detecte.get('volets')}"
    )


@pytest.mark.asyncio
async def test_auto_detection_ignore_portail_sans_device_class():
    """Sans device_class, le nom doit suffire à écarter un portail."""
    from custom_components.smartwake.config_flow import _auto_detect_entities

    hass = _faux_hass_avec([("cover.portail_entree", {})])
    assert (await _auto_detect_entities(hass)).get("volets") is None


@pytest.mark.asyncio
async def test_auto_detection_ne_propose_jamais_de_volet():
    """Les volets ne sont jamais pré-remplis, quelle que soit la configuration.

    Même un unique volet peut équiper une autre pièce que la chambre, et une
    ouverture non voulue au réveil se remarque tard. Le coût d'un champ à
    renseigner soi-même est sans commune mesure avec celui d'une erreur ici.
    """
    from custom_components.smartwake.config_flow import _auto_detect_entities

    for etats in (
        [("cover.volet_chambre", {"device_class": "shutter"})],
        [("cover.volet_salon", {"device_class": "shutter"})],
        [("cover.baie", {"device_class": "window"})],
        [("cover.porte_garage", {"device_class": "garage"})],
    ):
        detecte = await _auto_detect_entities(_faux_hass_avec(etats))
        assert detecte.get("volets") is None, (
            f"volet pré-rempli à tort : {detecte.get('volets')} pour {etats}"
        )

    # Les autres domaines restent proposés quand ils sont sans ambiguïté
    hass = _faux_hass_avec([
        ("cover.volet_chambre", {"device_class": "shutter"}),
        ("light.chambre", {}),
        ("light.salon", {}),
    ])
    detecte = await _auto_detect_entities(hass)
    assert detecte.get("volets") is None
    assert detecte["lumiere"] == "light.chambre"


@pytest.mark.asyncio
async def test_auto_detection_s_abstient_si_ambigu():
    """Plusieurs candidats équivalents : le champ doit rester vide plutôt que
    de désigner arbitrairement une pièce."""
    from custom_components.smartwake.config_flow import _auto_detect_entities

    hass = _faux_hass_avec([
        ("cover.volet_salon", {"device_class": "shutter"}),
        ("cover.volet_cuisine", {"device_class": "shutter"}),
        ("light.salon", {}),
        ("light.cuisine", {}),
        ("media_player.tv_salon", {}),
        ("media_player.enceinte_cuisine", {}),
        ("person.paul", {}),
        ("person.marie", {}),
    ])
    detecte = await _auto_detect_entities(hass)
    for cle in ("volets", "lumiere", "media_player", "presence"):
        assert detecte.get(cle) is None, f"{cle} pré-rempli arbitrairement"


@pytest.mark.asyncio
async def test_auto_detection_accepte_un_candidat_unique():
    """Sans ambiguïté possible, la proposition reste utile — hors volets."""
    from custom_components.smartwake.config_flow import _auto_detect_entities

    hass = _faux_hass_avec([
        ("cover.volet", {"device_class": "shutter"}),
        ("light.plafonnier", {}),
        ("person.paul", {}),
    ])
    detecte = await _auto_detect_entities(hass)
    assert detecte["lumiere"] == "light.plafonnier"
    assert detecte["presence"] == "person.paul"
    assert detecte.get("volets") is None


def test_presets_sans_entite_codee_en_dur():
    """Les presets ne doivent contenir aucun identifiant d'entité : ils
    réintroduiraient une valeur que l'auto-détection s'est refusée à choisir."""
    from custom_components.smartwake.config_flow import PRESETS

    for nom, preset in PRESETS.items():
        fautifs = {k: v for k, v in preset.items()
                   if isinstance(v, str) and "." in v and " " not in v}
        assert not fautifs, f"preset '{nom}' contient des entités : {fautifs}"


# ── Mode de travail et planification des tâches IA ─────────────

@pytest.mark.asyncio
async def test_contexte_travail_entite_prime_sur_valeur_fixe(coordinator):
    """Une entité renseignée doit l'emporter, pour les rythmes alternés."""
    from custom_components.smartwake.ai import contexte_travail

    hass = coordinator.hass
    hass.states.set("binary_sensor.workday", "on")
    hass.states.set("input_select.travail", "Télétravail")

    ctx = contexte_travail(hass, {
        "workday_sensor": "binary_sensor.workday",
        "mode_travail": "presentiel",
        "mode_travail_entity": "input_select.travail",
    })
    assert ctx["teletravail"] is True
    assert ctx["jour_travaille"] is True


@pytest.mark.asyncio
async def test_contexte_travail_reconnait_les_libelles_libres(coordinator):
    """Les input_select sont rédigés librement par l'utilisateur."""
    from custom_components.smartwake.ai import contexte_travail

    hass = coordinator.hass
    for valeur, attendu_tele in (
        ("Remote", True), ("À la maison", True), ("Au bureau", False),
        ("Présentiel", False), ("Sur site", False),
    ):
        hass.states.set("input_select.t", valeur)
        ctx = contexte_travail(hass, {"mode_travail_entity": "input_select.t"})
        assert ctx["teletravail"] is attendu_tele, f"{valeur} mal interprété"


@pytest.mark.asyncio
async def test_briefing_omis_les_jours_non_travailles(coordinator):
    """Le briefing agenda et trajet n'a pas d'objet un jour chômé."""
    from custom_components.smartwake import ai

    coordinator.hass.states.set("binary_sensor.workday", "off")
    cfg = {
        "ai_briefing": True,
        "ai_briefing_si_travail": True,
        "workday_sensor": "binary_sensor.workday",
    }
    appel = AsyncMock(return_value={"data": "briefing"})
    with patch.object(ai, "_call_ai_task", appel):
        resultat = await ai.generate_briefing(coordinator.hass, cfg, "Reveil")

    assert resultat is None
    # Sans cette vérification, le test passerait aussi parce que l'appel IA
    # échoue de lui-même en l'absence de service ai_task.
    assert not appel.called, "aucun appel à l'IA ne doit être émis"

    # Et le briefing doit bien être produit un jour travaillé
    coordinator.hass.states.set("binary_sensor.workday", "on")
    with patch.object(ai, "_call_ai_task", appel):
        assert await ai.generate_briefing(coordinator.hass, cfg, "Reveil") == "briefing"
    assert appel.called


@pytest.mark.asyncio
async def test_briefing_teletravail_sans_trajet(coordinator):
    """En télétravail, le temps de trajet ne doit pas être transmis."""
    from custom_components.smartwake import ai

    hass = coordinator.hass
    hass.states.set("input_select.t", "teletravail")
    hass.states.set("sensor.trajet", "35")
    captures = {}

    async def _faux(h, nom, instructions, *a, **kw):
        captures["i"] = instructions
        return {"data": "ok"}

    with patch.object(ai, "_call_ai_task", _faux):
        await ai.generate_briefing(hass, {
            "ai_briefing": True,
            "mode_travail_entity": "input_select.t",
            "trajet_sensor": "sensor.trajet",
        }, "Reveil")

    assert "35 min" not in captures["i"], "le trajet ne doit pas être transmis"
    assert "sans objet" in captures["i"]
    assert "télétravail" in captures["i"]


def test_style_musical_par_famille_meteo():
    """Chaque famille météo doit retrouver le style configuré."""
    from custom_components.smartwake.ai import style_musical_meteo

    cfg = {
        "musique_style_soleil": "pop énergique",
        "musique_style_pluie": "jazz doux",
    }
    assert style_musical_meteo(cfg, "sunny") == "pop énergique"
    assert style_musical_meteo(cfg, "pouring") == "jazz doux"
    assert style_musical_meteo(cfg, "lightning-rainy") == "jazz doux"
    assert style_musical_meteo(cfg, "snowy") == ""  # non configuré


@pytest.mark.asyncio
async def test_style_musical_transmis_a_l_ia(coordinator):
    """Le style configuré doit primer sur la règle générique du prompt."""
    from custom_components.smartwake import ai

    coordinator.hass.states.set("weather.home", "rainy")
    captures = {}

    async def _faux(h, nom, instructions, *a, **kw):
        captures["i"] = instructions
        return {"data": {"source": "x"}}

    with patch.object(ai, "_call_ai_task", _faux):
        await ai.choose_adaptive_music(coordinator.hass, {
            "ai_musique_adapt": True,
            "weather_entity": "weather.home",
            "musique_style_pluie": "jazz doux, piano",
        }, ["a", "b"])

    assert "jazz doux, piano" in captures["i"]
    assert "Beau temps = choix énergique" not in captures["i"]


def test_heure_planifiee_configurable():
    """Régression : l'heure de la suggestion du soir était figée à 21:30 dans
    le code, et le bilan hebdomadaire n'était déclenchable que par service."""
    src = open("custom_components/smartwake/coordinator.py", encoding="utf-8").read()
    assert "hour=21, minute=30" not in src, "heure encore codée en dur"
    assert "_ai_bilan_callback" in src, "le bilan doit être planifié"


@pytest.mark.asyncio
async def test_analyse_heure_planifiee(coordinator):
    """Une heure invalide ne doit pas empêcher la planification."""
    assert coordinator._heure_minute("07:45", "21:30") == (7, 45)
    assert coordinator._heure_minute(None, "21:30") == (21, 30)
    assert coordinator._heure_minute("", "20:00") == (20, 0)
    assert coordinator._heure_minute("nawak", "20:00") == (20, 0)
    assert coordinator._heure_minute("99:99", "20:00") == (20, 0)


# ── Synchronisation carte <-> options ──────────────────────────

@pytest.mark.asyncio
async def test_ecriture_identique_ne_bloque_pas_les_options(coordinator):
    """Régression : async_update_entry n'appelle les écouteurs que si les
    données ont réellement changé. Réécrire une valeur identique depuis la
    carte laissait le drapeau d'écriture interne armé, si bien que la
    modification d'options suivante était prise pour une écriture interne —
    donc ignorée, sans rechargement ni prise en compte.
    """
    await coordinator.set_actif(True)
    await coordinator.set_config_value("aube_min", 20)
    assert coordinator.consume_internal_update() is True

    # Même valeur : rien ne change, aucun écouteur ne sera appelé
    await coordinator.set_config_value("aube_min", 20)
    assert coordinator.consume_internal_update() is False, (
        "le drapeau reste armé et avalera la prochaine modification d'options"
    )


@pytest.mark.asyncio
async def test_modification_options_provoque_un_rechargement(coordinator):
    """Une écriture venant du menu d'options doit recharger l'entrée, seul
    moyen d'appliquer les changements structurels (entités, planification)."""
    from custom_components.smartwake import _async_update_listener
    from custom_components.smartwake.const import DOMAIN

    hass = coordinator.hass
    hass.data = {DOMAIN: {coordinator.entry.entry_id: coordinator}}
    recharges = []

    async def _reload(entry_id):
        recharges.append(entry_id)

    hass.config_entries.async_reload = _reload

    # Écriture typique du menu d'options : le drapeau n'est pas armé
    await _async_update_listener(hass, coordinator.entry)
    assert recharges == [coordinator.entry.entry_id]


@pytest.mark.asyncio
async def test_modification_carte_ne_recharge_pas(coordinator):
    """Une écriture venant d'une entité est déjà appliquée par le coordinator :
    la recharger désarmerait le réveil."""
    from custom_components.smartwake import _async_update_listener
    from custom_components.smartwake.const import DOMAIN

    hass = coordinator.hass
    hass.data = {DOMAIN: {coordinator.entry.entry_id: coordinator}}
    recharges = []

    async def _reload(entry_id):
        recharges.append(entry_id)

    hass.config_entries.async_reload = _reload

    await coordinator.set_actif(True)
    await coordinator.set_config_value("aube_min", 33)
    await _async_update_listener(hass, coordinator.entry)

    assert recharges == [], "une écriture d'entité ne doit pas recharger"
    assert coordinator.actif is True
    assert coordinator.config["aube_min"] == 33


@pytest.mark.asyncio
async def test_valeur_ecrite_par_la_carte_visible_dans_les_options(coordinator):
    """Ce que la carte écrit doit être relu par le formulaire d'options."""
    from custom_components.smartwake.config_flow import SmartWAKEOptionsFlow

    await coordinator.set_actif(True)
    await coordinator.set_config_value("aube_min", 42)
    await coordinator.set_heure("06:15")

    flow = SmartWAKEOptionsFlow(coordinator.entry)
    assert flow._data["aube_min"] == 42
    assert flow._data["heure"] == "06:15"


@pytest.mark.asyncio
async def test_valeur_ecrite_par_les_options_visible_des_entites(coordinator):
    """Et inversement : ce que les options écrivent doit être exposé par les
    entités que lit la carte."""
    import voluptuous as vol

    from custom_components.smartwake.config_flow import SmartWAKEOptionsFlow

    await coordinator.set_actif(True)
    flow = SmartWAKEOptionsFlow(coordinator.entry)
    flow.hass = coordinator.hass

    schema = vol.Schema({vol.Optional("aube_min", default=20): int})
    flow._enregistrer({"aube_min": 55}, schema)

    # Le coordinator lit entry.data : la valeur est immédiatement disponible
    assert coordinator.config["aube_min"] == 55


# ── Régression : plus de prochain réveil ───────────────────────

@pytest.mark.asyncio
async def test_jours_personnalises_vides_signales(coordinator, caplog):
    """Régression : « Prochain réveil » passait à inconnu sans explication.

    Le mode « personnalisé » suppose une liste de jours. Sans elle, aucun jour
    n'est actif : _calculer_prochain ne trouve aucune occurrence sur huit
    jours, le capteur passe à inconnu et le réveil ne sonne plus jamais — sans
    le moindre message.
    """
    import logging

    coordinator.entry.data = {
        **coordinator.entry.data, "jours": "personnalise", "jours_perso": [],
    }
    with caplog.at_level(logging.WARNING):
        await coordinator.set_actif(True)

    assert coordinator.prochain_reveil is None
    assert "aucun jour actif" in caplog.text.lower(), (
        "la cause doit apparaître dans les journaux"
    )


@pytest.mark.asyncio
async def test_jours_personnalises_renseignes(coordinator):
    """Avec des jours cochés, la planification reprend normalement."""
    coordinator.entry.data = {
        **coordinator.entry.data,
        "jours": "personnalise",
        "jours_perso": ["lundi", "mercredi", "vendredi"],
    }
    await coordinator.set_actif(True)
    assert coordinator.prochain_reveil is not None
    assert coordinator.prochain_reveil.weekday() in (0, 2, 4)


@pytest.mark.asyncio
async def test_select_refuse_personnalise_sans_jours(coordinator):
    """Le sélecteur ne doit pas pouvoir désactiver le réveil en silence."""
    _stub_number_module()
    from homeassistant.exceptions import HomeAssistantError

    from custom_components.smartwake.select import SELECT_DESC, ReveilSelect

    ent = ReveilSelect(coordinator, coordinator.entry, SELECT_DESC)
    coordinator.entry.data = {**coordinator.entry.data, "jours_perso": []}

    with pytest.raises(HomeAssistantError):
        await ent.async_select_option("personnalise")
    assert coordinator.config["jours"] != "personnalise"

    # Les autres modes restent acceptés
    await ent.async_select_option("weekend")
    assert coordinator.config["jours"] == "weekend"


@pytest.mark.asyncio
async def test_heure_invalide_ne_casse_pas_la_planification(coordinator):
    """Régression : une heure malformée levait une exception qui remontait
    jusqu'au rafraîchissement, laissant toutes les entités indisponibles."""
    coordinator.entry.data = {**coordinator.entry.data, "heure": "7h00"}
    await coordinator.set_actif(True)
    assert coordinator.prochain_reveil is not None
    assert coordinator.prochain_reveil.hour == 7


# ── Régression : lecture musicale sans playlist ────────────────

@pytest.mark.asyncio
async def test_musique_sans_playlist_ne_tente_pas_la_lecture(coordinator):
    """Régression : « Tentative musique 1/3 échouée: string index out of range ».

    Sans playlist configurée, l'identifiant média valait la chaîne vide et
    play_media était appelé quand même. Côté Home Assistant,
    async_process_play_media_url fait `media_content_id[0] != "/"`, ce qui lève
    IndexError sur une chaîne vide : trois tentatives inutiles, puis repli
    vocal, sans que la cause soit compréhensible.
    """
    coordinator.entry.data = {
        **coordinator.entry.data,
        "media_player": "media_player.chambre",
        "playlist": "",
    }
    appels = []

    async def _call(domain, service, data=None, **kw):
        appels.append((domain, service))

    coordinator.hass.services.async_call = _call
    with patch.object(coordinator, "_tts_speak", AsyncMock()) as tts:
        await coordinator._demarrer_musique()

    assert not [a for a in appels if a == ("media_player", "play_media")], (
        "aucune lecture ne doit être tentée sans playlist"
    )
    assert tts.called, "le repli vocal doit prendre le relais"


@pytest.mark.asyncio
async def test_musique_ia_refuse_une_option_injouable(coordinator):
    """Régression : les options soumises à l'IA étaient des noms inventés
    (« France Inter », « Radio Nova »), que le lecteur ne sait pas jouer. Le
    choix de l'IA remplaçait une playlist valide par une valeur injouable.
    """
    from custom_components.smartwake import ai

    coordinator.entry.data = {
        **coordinator.entry.data,
        "media_player": "media_player.chambre",
        "playlist": "media-source://media_source/local/reveil.mp3",
        "playlist_douce": "media-source://media_source/local/doux.mp3",
        "ai_musique_adapt": True,
    }
    lectures = []

    async def _call(domain, service, data=None, **kw):
        if service == "play_media":
            lectures.append((data or {}).get("media_content_id"))

    coordinator.hass.services.async_call = _call

    # L'IA renvoie une valeur hors des options : elle doit être écartée
    with patch.object(ai, "choose_adaptive_music",
                      AsyncMock(return_value="France Inter")):
        await coordinator._demarrer_musique()
    assert lectures[0] == "media-source://media_source/local/reveil.mp3"

    # Une valeur figurant dans les options est acceptée
    lectures.clear()
    with patch.object(ai, "choose_adaptive_music",
                      AsyncMock(return_value="media-source://media_source/local/doux.mp3")):
        await coordinator._demarrer_musique()
    assert lectures[0] == "media-source://media_source/local/doux.mp3"


@pytest.mark.asyncio
async def test_musique_ia_ignoree_sans_alternative(coordinator):
    """Sans seconde playlist, il n'y a rien à choisir : l'appel à l'IA est
    inutile et doit être évité."""
    from custom_components.smartwake import ai

    coordinator.entry.data = {
        **coordinator.entry.data,
        "media_player": "media_player.chambre",
        "playlist": "media-source://media_source/local/reveil.mp3",
        "ai_musique_adapt": True,
    }

    async def _call(domain, service, data=None, **kw):
        pass

    coordinator.hass.services.async_call = _call
    choix = AsyncMock(return_value=None)
    with patch.object(ai, "choose_adaptive_music", choix):
        await coordinator._demarrer_musique()
    assert not choix.called


def test_media_id_accepte_dict_et_chaine(coordinator=None):
    """Le sélecteur de média renvoie soit un dict, soit une chaîne."""
    from custom_components.smartwake.coordinator import ReveilCoordinator

    f = ReveilCoordinator._media_id
    # Format réel renvoyé par le MediaSelector de Home Assistant : la clé est
    # « media_content_id », pas « content_id ». Chercher la mauvaise faisait
    # passer une playlist configurée pour vide.
    assert f({
        "entity_id": "media_player.chambre",
        "media_content_id": "media-source://media_source/local/reveil.mp3",
        "media_content_type": "audio/mpeg",
    }) == "media-source://media_source/local/reveil.mp3"
    assert f({"media_content_id": "spotify:playlist:37i9dQ"}) == "spotify:playlist:37i9dQ"
    # Rétrocompatibilité avec l'ancien format
    assert f({"content_id": "x", "content_type": "music"}) == "x"
    assert f("y") == "y"
    assert f("  z  ") == "z"
    assert f(None) == ""
    assert f("") == ""
    assert f({}) == ""


@pytest.mark.asyncio
async def test_notify_entite_resolue_vers_le_service_de_plateforme(coordinator):
    """Régression : « Service notify.sm_g991u1 introuvable ».

    Une entité `notify.<objet>` est fournie par une plateforme dont le service
    historique s'appelle `<plateforme>_<objet>`. L'entité `notify.sm_g991u1` de
    l'application mobile correspond ainsi au service
    `notify.mobile_app_sm_g991u1`. Chercher le service `notify.sm_g991u1`
    échouait, et les notifications partaient sans boutons Snooze/Stop.
    """
    coordinator.entry.data = {
        **coordinator.entry.data, "notify_device": "notify.sm_g991u1",
    }
    coordinator.hass.services.has_service = lambda d, s: (
        d == "notify" and s == "mobile_app_sm_g991u1"
    )
    appels = []

    async def _call(domain, service, data=None, **kw):
        appels.append((domain, service, data or {}))

    coordinator.hass.services.async_call = _call

    await coordinator._envoyer_notification()

    assert len(appels) == 1
    domaine, service, data = appels[0]
    assert (domaine, service) == ("notify", "mobile_app_sm_g991u1")
    assert "actions" in data["data"], "les boutons doivent être transmis"


@pytest.mark.asyncio
async def test_notify_repli_sans_service_historique(coordinator):
    """Sans service historique, l'entity service prend le relais — sans
    boutons, ce qui doit être signalé."""
    coordinator.entry.data = {
        **coordinator.entry.data, "notify_device": "notify.inconnu",
    }
    coordinator.hass.services.has_service = lambda d, s: False
    appels = []

    async def _call(domain, service, data=None, **kw):
        appels.append((domain, service, data or {}))

    coordinator.hass.services.async_call = _call

    await coordinator._envoyer_notification()

    assert len(appels) == 1
    domaine, service, data = appels[0]
    assert (domaine, service) == ("notify", "send_message")
    assert data["entity_id"] == "notify.inconnu"
    assert "data" not in data, "l'entity service refuse la clé data"


# ── Régression : modèles sans réponse structurée ───────────────

def test_extraction_json_de_reponses_de_modele():
    """Les modèles encadrent volontiers leur JSON de texte ou de balises."""
    from custom_components.smartwake.ai import _extraire_json

    assert _extraire_json('{"source":"a"}') == {"source": "a"}
    assert _extraire_json('```json\n{"source":"a"}\n```') == {"source": "a"}
    assert _extraire_json('Voici :\n```json\n{"source":"a"}\n```\nBonne écoute')\
        == {"source": "a"}
    assert _extraire_json('Je propose {"source": "a"} ce matin.') == {"source": "a"}
    assert _extraire_json("Je recommande la playlist douce.") is None
    assert _extraire_json("") is None
    assert _extraire_json(None) is None


@pytest.mark.asyncio
async def test_repli_sans_structure_quand_le_modele_refuse(coordinator):
    """Régression : « Error with Ollama structured response ».

    Tous les modèles ne savent pas produire une réponse conforme à un schéma.
    Chaque fonction reposant sur une structure — choix de musique, suggestion
    d'heure, vérification du lever — échouait alors définitivement. On redemande
    désormais la même chose en texte libre, en réclamant du JSON.
    """
    from custom_components.smartwake.ai import _call_ai_task

    appels = []

    async def _call(domain, service, data=None, **kw):
        appels.append("structure" if "structure" in (data or {}) else "libre")
        if "structure" in (data or {}):
            raise Exception("Error with Ollama structured response")
        return {"data": '```json\n{"source":"douce"}\n```'}

    coordinator.hass.services.async_call = _call

    res = await _call_ai_task(
        coordinator.hass, "Choix musique", "choisis", {"source": {}}, cfg={}
    )
    assert appels == ["structure", "libre"], f"séquence inattendue : {appels}"
    assert res == {"data": {"source": "douce"}}


@pytest.mark.asyncio
async def test_repli_refuse_une_reponse_incomplete(coordinator):
    """Une réponse amputée d'une clé attendue ne doit pas être utilisée."""
    from custom_components.smartwake.ai import _call_ai_task

    async def _call(domain, service, data=None, **kw):
        if "structure" in (data or {}):
            raise Exception("Error with Ollama structured response")
        return {"data": '{"heure_proposee":"06:45"}'}

    coordinator.hass.services.async_call = _call
    res = await _call_ai_task(
        coordinator.hass, "Heure", "calcule",
        {"heure_proposee": {}, "decaler": {}, "raison": {}}, cfg={},
    )
    assert res is None


@pytest.mark.asyncio
async def test_pas_de_repli_sans_structure_demandee(coordinator):
    """Un appel sans structure ne doit pas être rejoué inutilement."""
    from custom_components.smartwake.ai import _call_ai_task

    appels = []

    async def _call(domain, service, data=None, **kw):
        appels.append(1)
        raise Exception("modèle indisponible")

    coordinator.hass.services.async_call = _call
    assert await _call_ai_task(coordinator.hass, "Briefing", "x", cfg={}) is None
    assert len(appels) == 1


# ── Compte à rebours du snooze ─────────────────────────────────

@pytest.mark.asyncio
async def test_fin_de_snooze_exposee(coordinator):
    """Régression : seule la durée configurée était exposée, si bien que
    l'interface affichait « Re-sonne dans 5 min » sans jamais décompter.
    L'instant de reprise doit être disponible pour un compte à rebours réel.
    """
    coordinator.entry.data = {**coordinator.entry.data, "snooze_duree": 5}
    await coordinator.set_actif(True)
    coordinator._reveil_en_cours = True
    coordinator._statut = "ringing"

    assert coordinator.snooze_fin is None, "rien à décompter hors snooze"

    avant = datetime.now()
    await coordinator.snooze()
    fin = coordinator.snooze_fin

    assert fin is not None
    reste = (fin.replace(tzinfo=None) - avant).total_seconds() / 60
    assert 4.5 < reste <= 5.5, f"fin de snooze incohérente : {reste:.1f} min"


@pytest.mark.asyncio
async def test_fin_de_snooze_effacee_a_la_reprise(coordinator):
    """L'instant doit disparaître dès que la sonnerie reprend, sinon la carte
    afficherait un décompte négatif."""
    await coordinator.set_actif(True)
    coordinator._reveil_en_cours = True
    coordinator._statut = "ringing"
    await coordinator.snooze()
    assert coordinator.snooze_fin is not None

    coordinator._statut = "ringing"
    assert coordinator.snooze_fin is None, "exposé uniquement pendant le snooze"


@pytest.mark.asyncio
async def test_fin_de_snooze_effacee_au_stop(coordinator):
    await coordinator.set_actif(True)
    coordinator._reveil_en_cours = True
    coordinator._statut = "ringing"
    await coordinator.snooze()

    await coordinator.stop()
    assert coordinator._snooze_fin is None
    assert coordinator.snooze_fin is None


@pytest.mark.asyncio
async def test_capteur_fin_de_snooze(coordinator):
    """Le capteur doit exposer l'instant, avec device_class timestamp."""
    _stub_number_module()
    from custom_components.smartwake.sensor import (
        SENSOR_FIN_SNOOZE, ReveilFinSnoozeSensor,
    )

    ent = ReveilFinSnoozeSensor(coordinator, coordinator.entry, SENSOR_FIN_SNOOZE)
    assert ent._attr_device_class == "timestamp"
    assert ent.native_value is None

    await coordinator.set_actif(True)
    coordinator._reveil_en_cours = True
    coordinator._statut = "ringing"
    await coordinator.snooze()
    assert ent.native_value is not None


# ── Régression : la lumière se rallumait pendant le snooze ──────

@pytest.mark.asyncio
async def test_snooze_suspend_la_rampe_de_lumiere(coordinator):
    """Régression : la lumière se rallumait une trentaine de secondes après le
    snooze et poursuivait sa montée.

    snooze() éteignait la lampe mais n'annulait pas les rampes lancées par le
    cycle. La tâche de lumière progressive continuait donc d'émettre un
    light.turn_on à chaque pas, rallumant la chambre en pleine période de
    snooze — alors que la reprise de la sonnerie, elle, respectait bien les
    5 minutes.
    """
    coordinator.entry.data = {
        **coordinator.entry.data,
        "lumiere": "light.chambre", "lumiere_activee": True,
        "snooze_duree": 5, "snooze_max": 3,
    }
    allumages = []

    async def _call(domain, service, data=None, **kw):
        if service == "turn_on":
            allumages.append((data or {}).get("brightness"))

    coordinator.hass.services.async_call = _call
    coordinator._reveil_en_cours = True
    coordinator._statut = "ringing"

    async def _rampe_sans_fin():
        while True:
            await _call("light", "turn_on", {"brightness": 50})
            await asyncio.sleep(0.01)

    tache = asyncio.ensure_future(_rampe_sans_fin())
    coordinator._cancel_rampes = [tache]
    await asyncio.sleep(0.03)

    with patch.object(coordinator, "_reprendre_apres_snooze", AsyncMock()):
        await coordinator.snooze()

    assert coordinator._cancel_rampes == [], "les rampes doivent être vidées"
    avant = len(allumages)
    await asyncio.sleep(0.1)
    assert len(allumages) == avant, (
        f"{len(allumages) - avant} rallumage(s) pendant le snooze"
    )
    tache.cancel()


@pytest.mark.asyncio
async def test_rampe_reprend_au_niveau_atteint(coordinator):
    """La montée doit reprendre où elle s'était arrêtée, et non repartir de
    zéro : le réveil serait sinon plus sombre après un snooze qu'avant."""
    coordinator.entry.data = {
        **coordinator.entry.data,
        "lumiere": "light.chambre", "lumiere_activee": True,
        "brightness_max": 162, "duree_progressive": 20,
    }
    niveaux = []

    async def _call(domain, service, data=None, **kw):
        if service == "turn_on":
            niveaux.append((data or {}).get("brightness"))

    coordinator.hass.services.async_call = _call

    # Rampe neuve : démarre au premier pas
    coordinator._aube_niveau = 0
    tache = asyncio.ensure_future(coordinator._cycle_lumiere_progressive())
    await asyncio.sleep(0.02)
    tache.cancel()
    premier_neuf = niveaux[0]

    # Reprise : démarre au niveau mémorisé
    niveaux.clear()
    coordinator._aube_niveau = 120
    tache = asyncio.ensure_future(coordinator._cycle_lumiere_progressive())
    await asyncio.sleep(0.02)
    tache.cancel()

    assert premier_neuf < 20, f"une rampe neuve doit démarrer bas : {premier_neuf}"
    assert niveaux[0] >= 116, f"la reprise doit repartir de ~120 : {niveaux[0]}"

    # La progression doit être mémorisée au fil de la montée, sans quoi la
    # reprise repartirait toujours du même point.
    coordinator._aube_niveau = 0
    niveaux.clear()
    tache = asyncio.ensure_future(coordinator._cycle_lumiere_progressive())
    await asyncio.sleep(0.02)
    tache.cancel()
    assert coordinator._aube_niveau == niveaux[-1], (
        f"niveau mémorisé {coordinator._aube_niveau} != dernier envoyé {niveaux[-1]}"
    )


@pytest.mark.asyncio
async def test_niveau_de_rampe_remis_a_zero(coordinator):
    """Un nouveau réveil doit repartir d'une montée complète."""
    coordinator._aube_niveau = 140
    coordinator._reveil_en_cours = True
    await coordinator.stop()
    assert coordinator._aube_niveau == 0

    coordinator._aube_niveau = 140
    await coordinator.reset()
    assert coordinator._aube_niveau == 0


# ── Test des tâches IA depuis les options ──────────────────────

def _flow_options(coordinator):
    from custom_components.smartwake.config_flow import SmartWAKEOptionsFlow
    from custom_components.smartwake.const import DOMAIN

    flow = SmartWAKEOptionsFlow(coordinator.entry)
    flow.hass = coordinator.hass
    coordinator.hass.data = {DOMAIN: {coordinator.entry.entry_id: coordinator}}
    captures = {}
    flow.async_show_form = lambda **kw: captures.update(kw) or {"type": "form"}
    return flow, captures


def test_toutes_les_taches_ia_sont_testables():
    """Chaque tâche IA de ai.py doit être joignable depuis les options.

    Elles ne se déclenchent qu'à des moments précis — au réveil, au stop, le
    soir — ce qui rendait leur mise au point laborieuse : seul le bilan
    hebdomadaire disposait d'un service appelable.
    """
    from custom_components.smartwake.config_flow import TACHES_IA

    attendues = {"briefing", "musique", "suggestion", "bilan", "lever",
                 "personnalisees"}
    assert set(TACHES_IA) == attendues


@pytest.mark.asyncio
async def test_test_ia_signale_un_reveil_non_charge(coordinator):
    from custom_components.smartwake.const import DOMAIN

    flow, captures = _flow_options(coordinator)
    coordinator.hass.data = {DOMAIN: {}}
    await flow.async_step_test_ia({"tache": "briefing"})
    assert "non chargé" in captures["description_placeholders"]["resultat"]


@pytest.mark.asyncio
async def test_test_ia_remonte_les_exceptions(coordinator):
    """Une erreur doit être affichée, non avalée."""
    from custom_components.smartwake import ai

    flow, captures = _flow_options(coordinator)
    with patch.object(ai, "generate_briefing",
                      AsyncMock(side_effect=RuntimeError("boom"))):
        await flow.async_step_test_ia({"tache": "briefing"})
    resultat = captures["description_placeholders"]["resultat"]
    assert "RuntimeError" in resultat and "boom" in resultat


@pytest.mark.asyncio
async def test_test_ia_affiche_le_resultat(coordinator):
    from custom_components.smartwake import ai

    flow, captures = _flow_options(coordinator)
    with patch.object(ai, "generate_briefing",
                      AsyncMock(return_value="Bonjour, il fait beau.")):
        await flow.async_step_test_ia({"tache": "briefing"})
    assert captures["description_placeholders"]["resultat"] == "Bonjour, il fait beau."


@pytest.mark.asyncio
async def test_test_ia_active_la_fonctionnalite_le_temps_du_test(coordinator):
    """Le test doit fonctionner même si l'option est désactivée, sans quoi il
    faudrait l'activer avant chaque essai."""
    from custom_components.smartwake import ai

    coordinator.entry.data = {**coordinator.entry.data, "ai_briefing": False}
    flow, captures = _flow_options(coordinator)
    recu = {}

    async def _briefing(hass, cfg, titre):
        recu["ai_briefing"] = cfg.get("ai_briefing")
        return "ok"

    with patch.object(ai, "generate_briefing", _briefing):
        await flow.async_step_test_ia({"tache": "briefing"})

    assert recu["ai_briefing"] is True
    # sans modifier la configuration enregistrée
    assert coordinator.entry.data["ai_briefing"] is False


@pytest.mark.asyncio
async def test_test_ia_musique_exige_deux_playlists(coordinator):
    """Sans alternative, l'IA n'a rien à choisir : autant le dire."""
    coordinator.entry.data = {
        **coordinator.entry.data, "playlist": "media-source://x",
    }
    flow, captures = _flow_options(coordinator)
    await flow.async_step_test_ia({"tache": "musique"})
    assert "deux playlists" in captures["description_placeholders"]["resultat"]


# ── Couleur, courbe et scène de la lumière de réveil ───────────

def test_couleur_de_lumiere():
    """Régression : la température de couleur était lue par la rampe mais
    aucun champ ne permettait de la renseigner. Aucune couleur n'était donc
    jamais appliquée."""
    from custom_components.smartwake.coordinator import ReveilCoordinator

    f = ReveilCoordinator._couleur_lumiere
    # Home Assistant refuse couleur et température ensemble : la couleur prime
    assert f({"lumiere_couleur": [255, 180, 80], "lumiere_temp_couleur": 2700}) \
        == {"rgb_color": [255, 180, 80]}
    assert f({"lumiere_temp_couleur": 2700}) == {"color_temp_kelvin": 2700}
    assert f({}) == {}
    # Valeurs illisibles : on n'impose rien plutôt que de faire échouer l'appel
    assert f({"lumiere_couleur": "nawak"}) == {}
    assert f({"lumiere_temp_couleur": "abc"}) == {}


@pytest.mark.asyncio
async def test_couleur_appliquee_a_chaque_pas(coordinator):
    coordinator.entry.data = {
        **coordinator.entry.data,
        "lumiere": "light.chambre", "lumiere_activee": True,
        "brightness_max": 200, "duree_progressive": 10,
        "lumiere_couleur": [255, 180, 80],
    }
    charges = []

    async def _call(domain, service, data=None, **kw):
        if service == "turn_on":
            charges.append(data or {})

    coordinator.hass.services.async_call = _call
    tache = asyncio.ensure_future(coordinator._cycle_lumiere_progressive())
    await asyncio.sleep(0.02)
    tache.cancel()

    assert charges, "aucun appel émis"
    assert all(c.get("rgb_color") == [255, 180, 80] for c in charges)
    assert not any("color_temp_kelvin" in c for c in charges)


@pytest.mark.asyncio
async def test_courbe_douce_demarre_plus_bas(coordinator):
    """Une montée quadratique paraît plus naturelle : l'œil perçoit mal les
    écarts dans les niveaux bas."""
    async def premier_pas(courbe):
        coordinator.entry.data = {
            **coordinator.entry.data,
            "lumiere": "light.chambre", "lumiere_activee": True,
            "brightness_max": 200, "duree_progressive": 10,
            "lumiere_courbe": courbe,
        }
        coordinator._aube_niveau = 0
        niveaux = []

        async def _call(domain, service, data=None, **kw):
            if service == "turn_on":
                niveaux.append((data or {}).get("brightness"))

        coordinator.hass.services.async_call = _call
        tache = asyncio.ensure_future(coordinator._cycle_lumiere_progressive())
        await asyncio.sleep(0.02)
        tache.cancel()
        return niveaux[0]

    assert await premier_pas("douce") < await premier_pas("lineaire")


@pytest.mark.asyncio
async def test_scene_appliquee_en_fin_de_montee(coordinator):
    """La scène permet une ambiance sur plusieurs lampes, que la montée d'une
    seule luminosité ne sait pas rendre."""
    coordinator.entry.data = {
        **coordinator.entry.data,
        "lumiere": "light.chambre", "lumiere_activee": True,
        "brightness_max": 10, "duree_progressive": 1,
        "lumiere_scene": "scene.reveil_doux",
    }
    scenes = []

    async def _call(domain, service, data=None, **kw):
        if domain == "scene":
            scenes.append((data or {}).get("entity_id"))

    coordinator.hass.services.async_call = _call
    await coordinator._cycle_lumiere_progressive()
    assert scenes == ["scene.reveil_doux"]


@pytest.mark.asyncio
async def test_scenes_du_matin_declenchees_par_la_liste(coordinator):
    """Régression : l'activation dépendait d'un booléen absent du formulaire.
    Les scènes choisies ne se déclenchaient donc jamais."""
    src = open("custom_components/smartwake/coordinator.py", encoding="utf-8").read()
    assert "cfg.get(CONF_SCENE_MATIN_ENTITIES) or cfg.get(CONF_SCENES_MATIN" in src, (
        "une liste renseignée doit suffire à activer les scènes du matin"
    )


def test_champs_lumiere_presents_dans_le_formulaire():
    """Régression : trois constantes de lumière étaient définies sans champ,
    donc inatteignables — même situation que la phase de sommeil retirée."""
    src = open("custom_components/smartwake/config_flow.py", encoding="utf-8").read()
    for cle in ("CONF_LUMIERE_COULEUR", "CONF_LUMIERE_TEMP_COULEUR",
                "CONF_LUMIERE_COURBE", "CONF_LUMIERE_SCENE"):
        assert f"vol.Optional({cle})" in src or f"vol.Required({cle}," in src, (
            f"{cle} n'a pas de champ dans le formulaire"
        )


# ── Agenda adaptatif configurable ──────────────────────────────

def test_agenda_adaptatif_a_un_champ():
    """Régression : la logique existait (_instant_adaptatif_agenda) et le
    coordinator lisait adaptatif_agenda, agenda_entity et agenda_marge_min,
    mais aucun champ n'existait dans le formulaire. La fonctionnalité était
    donc inatteignable — même situation que la couleur ou les scènes."""
    src = open("custom_components/smartwake/config_flow.py", encoding="utf-8").read()
    for cle in ("CONF_ADAPTATIF_AGENDA", "CONF_AGENDA_ENTITY",
                "CONF_AGENDA_MARGE_MIN"):
        assert (f"vol.Optional({cle}" in src or f"vol.Required({cle}" in src), (
            f"{cle} n'a pas de champ dans le formulaire"
        )


def test_aucune_constante_fantome():
    """Une constante définie mais jamais ni lue par le métier ni proposée en
    champ laisse croire qu'elle fait quelque chose."""
    import ast

    const_src = open("custom_components/smartwake/const.py", encoding="utf-8").read()
    definies = {
        n.id for node in ast.walk(ast.parse(const_src))
        if isinstance(node, ast.Assign)
        for n in node.targets
        if isinstance(n, ast.Name) and n.id.startswith("CONF_")
    }

    utilisees = set()
    for fichier in ("coordinator", "ai", "assist", "config_flow",
                    "number", "select", "switch", "sensor", "binary_sensor",
                    "time", "button", "__init__", "diagnostics"):
        src = open(f"custom_components/smartwake/{fichier}.py", encoding="utf-8").read()
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Name) and node.id.startswith("CONF_"):
                utilisees.add(node.id)

    # Clés conservées uniquement pour migrer d'anciennes configurations
    migration = {"CONF_WITHINGS_BED_1", "CONF_WITHINGS_BED_2", "CONF_AI_CAMERA_VERIF"}
    fantomes = sorted(definies - utilisees - migration)
    assert not fantomes, f"constantes jamais utilisées : {fantomes}"


# ── Diagnostics ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_diagnostics_expurgent_les_donnees_personnelles(coordinator):
    import json

    from custom_components.smartwake.const import DOMAIN
    from custom_components.smartwake.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    coordinator.entry.data = {
        **coordinator.entry.data,
        "nom": "Réveil de Paul",
        "notify_device": "notify.sm_g991u1",
        "presence": "person.paul",
        "tts_message": "Debout Paul",
    }
    coordinator.hass.data = {DOMAIN: {coordinator.entry.entry_id: coordinator}}
    await coordinator.set_actif(True)

    diag = await async_get_config_entry_diagnostics(
        coordinator.hass, coordinator.entry
    )
    brut = json.dumps(diag, ensure_ascii=False)

    for secret in ("Paul", "sm_g991u1", "Debout"):
        assert secret not in brut, f"fuite de « {secret} » dans les diagnostics"

    # mais l'état d'exécution utile est bien présent
    assert diag["coordinator"]["actif"] is True
    assert "prochain_reveil" in diag["coordinator"]
    assert "trigger_arme" in diag["coordinator"]


@pytest.mark.asyncio
async def test_diagnostics_sans_coordinator(coordinator):
    from custom_components.smartwake.const import DOMAIN
    from custom_components.smartwake.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    coordinator.hass.data = {DOMAIN: {}}
    diag = await async_get_config_entry_diagnostics(
        coordinator.hass, coordinator.entry
    )
    assert diag["coordinator"] == "non chargé"
    assert "config" in diag


# ── Rattrapage d'un réveil manqué au redémarrage ───────────────

@pytest.mark.asyncio
async def test_rattrapage_reveil_manque(coordinator):
    """Régression : un redémarrage juste avant le réveil faisait rater
    l'occurrence, considérée comme passée. On la rattrape si le retard reste
    dans la tolérance."""
    from datetime import datetime, timedelta

    from homeassistant.util import dt as dt_util

    now = dt_util.now()

    async def rattrape(delta_min, tolerance):
        heure = (now + timedelta(minutes=delta_min)).strftime("%H:%M")
        coordinator.entry.data = {
            **coordinator.entry.data, "heure": heure, "jours": "tous",
            "rattrapage_min": tolerance,
        }
        coordinator._actif = True
        coordinator._reveil_en_cours = False
        lance = []
        with patch.object(coordinator.hass, "async_create_task",
                          side_effect=lambda c: (lance.append(1), c.close())):
            coordinator._rattraper_reveil_manque()
        return bool(lance)

    assert await rattrape(-5, 15) is True, "retard de 5 min, tolérance 15"
    assert await rattrape(-20, 15) is False, "retard hors tolérance"
    assert await rattrape(5, 15) is False, "heure future"
    assert await rattrape(-5, 0) is False, "tolérance nulle = désactivé"

    # Le rattrapage doit être appelé au démarrage de Home Assistant
    src = open("custom_components/smartwake/coordinator.py", encoding="utf-8").read()
    demarrage = src[src.index("async def async_config_entry_first_refresh"):
                    src.index("def _rattraper_reveil_manque")]
    assert "_rattraper_reveil_manque()" in demarrage, (
        "le rattrapage n'est pas déclenché au démarrage"
    )


# ── Mode de travail exposé en entité ───────────────────────────

@pytest.mark.asyncio
async def test_mode_travail_en_entite(coordinator):
    """Le mode de travail n'était modifiable que dans les options. L'entité
    select permet de le piloter depuis un tableau de bord."""
    _stub_number_module()
    from custom_components.smartwake.select import (
        MODE_TRAVAIL_DESC, ReveilModeTravailSelect,
    )

    ent = ReveilModeTravailSelect(coordinator, coordinator.entry, MODE_TRAVAIL_DESC)
    assert ent.current_option == "indetermine"
    assert set(ent._attr_options) == {"indetermine", "presentiel", "teletravail"}

    await ent.async_select_option("teletravail")
    assert coordinator.config["mode_travail"] == "teletravail"

    # une valeur hors liste est ignorée
    await ent.async_select_option("nawak")
    assert coordinator.config["mode_travail"] == "teletravail"


# ── Service de test IA ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_service_tester_ia(coordinator):
    """La logique de test doit être partagée entre les options et le service,
    et renvoyer un résultat exploitable."""
    from custom_components.smartwake import ai

    coordinator.entry.data = {
        **coordinator.entry.data, "ai_task_entity": "ai_task.ollama",
    }
    with patch.object(ai, "generate_briefing",
                      AsyncMock(return_value="Bonjour, il fait beau.")):
        res = await coordinator.tester_ia("briefing")
    assert res == "Bonjour, il fait beau."

    # l'option est forcée le temps du test
    coordinator.entry.data = {**coordinator.entry.data, "ai_briefing": False}
    recu = {}

    async def _briefing(hass, cfg, titre):
        recu["actif"] = cfg.get("ai_briefing")
        return "ok"

    with patch.object(ai, "generate_briefing", _briefing):
        await coordinator.tester_ia("briefing")
    assert recu["actif"] is True

    # tâche inconnue
    assert "inconnue" in await coordinator.tester_ia("nawak")


def test_service_tester_ia_declare():
    """Le service doit être enregistré et documenté."""
    import json

    from custom_components.smartwake.const import SERVICE_TESTER_IA

    assert SERVICE_TESTER_IA == "tester_ia"
    services = json.load(open("custom_components/smartwake/services.yaml",
                              encoding="utf-8"))
    assert "tester_ia" in services
    assert "tache" in services["tester_ia"]["fields"]
