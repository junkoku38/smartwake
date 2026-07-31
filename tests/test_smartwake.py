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
    phase de sommeil était également ignoré.
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
    coordinator.hass.services.has_service = lambda d, s: True

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
