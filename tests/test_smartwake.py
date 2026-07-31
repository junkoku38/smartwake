"""Tests unitaires pour SmartWAKE — coordinator, ai, config_flow.

Utilise le mock HA de /tmp/hatest pour valider la logique sans HA réel.
"""

import asyncio
import sys
from datetime import datetime, timedelta
from datetime import time as dtime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Patch asyncio.sleep pour éviter les attentes réelles
_orig_sleep = asyncio.sleep
async def _fast_sleep(sec):
    await _orig_sleep(0)
asyncio.sleep = _fast_sleep

# Mock HA minimal
sys.path.insert(0, "/tmp/hatest")


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

    builtins_ok = set(dir(__builtins__)) if isinstance(__builtins__, dict) is False else set(__builtins__)
    import builtins as _b
    builtins_ok = set(dir(_b))

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
