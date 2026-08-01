"""Constantes pour l'intégration SmartWAKE."""

import unicodedata

from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def integration_version() -> str:
    """Version déclarée dans manifest.json.

    Elle était recopiée en dur à deux endroits, avec trois valeurs divergentes
    (2.0.0 dans __init__.py, 2.4.0 dans entity.py, et celle du manifest).
    """
    import json

    try:
        manifest = Path(__file__).parent / "manifest.json"
        return json.loads(manifest.read_text(encoding="utf-8"))["version"]
    except Exception:  # noqa: BLE001 - ne doit jamais bloquer le setup
        return "0.0.0"


DOMAIN = "smartwake"

# Version du schéma des config entries. Partagée entre le config flow et
# async_migrate_entry pour qu'elles ne puissent pas divergerne.
SCHEMA_VERSION = 6


def slugify(title: str) -> str:
    """Slugify un nom pour générer des entity_ids valides.

    Convertit les accents, espaces et caractères spéciaux en [a-z0-9_].
    Ex: 'Réveil Élève' -> 'reveil_eleve'
    """
    normalized = unicodedata.normalize("NFKD", title)
    ascii_str = normalized.encode("ascii", "ignore").decode("ascii")
    slug = ""
    for c in ascii_str.lower().strip():
        if c.isalnum():
            slug += c
        elif c in (" ", "-", ".", ",", "_"):
            slug += "_"
    slug = "_".join(part for part in slug.split("_") if part)
    return slug[:30] if slug else "reveil"

# ── Clés config flow ──────────────────────────────────────────
CONF_HEURE = "heure"
CONF_HEURE_PAR_JOUR = "heure_par_jour"
CONF_HEURE_LUNDI = "heure_lundi"
CONF_HEURE_MARDI = "heure_mardi"
CONF_HEURE_MERCREDI = "heure_mercredi"
CONF_HEURE_JEUDI = "heure_jeudi"
CONF_HEURE_VENDREDI = "heure_vendredi"
CONF_HEURE_SAMEDI = "heure_samedi"
CONF_HEURE_DIMANCHE = "heure_dimanche"
CONF_MODE_HEURE = "mode_heure"
CONF_JOURS = "jours"
CONF_JOURS_PERSO = "jours_perso"
CONF_LUMIERE = "lumiere"
CONF_LUMIERE_ACTIVEE = "lumiere_activee"
CONF_LUMIERE_TEMP_COULEUR = "lumiere_temp_couleur"
CONF_MUSIQUE_ACTIVEE = "musique_activee"
CONF_MEDIA_PLAYER = "media_player"
CONF_PLAYLIST = "playlist"
# Alternatives réellement jouables, parmi lesquelles l'IA peut choisir selon la
# météo. La version précédente proposait des noms inventés (« France Inter »,
# « Radio Nova »), qui ne sont pas des URI et faisaient échouer la lecture.
CONF_PLAYLIST_DOUCE = "playlist_douce"
CONF_PLAYLIST_ENERGIQUE = "playlist_energique"
CONF_VOLUME_INITIAL = "volume_initial"
CONF_VOLUME_FINAL = "volume_final"
CONF_VOLUME_DUREE = "volume_duree"
CONF_RADIATEUR = "radiateur"
CONF_PRECHAUFFE_MIN = "prechauffe_min"
CONF_CHAUFFE_EAU = "chauffe_eau"
CONF_CAFETIERE = "cafetiere"
CONF_CAFETIERE_MIN = "cafetiere_min"
CONF_AUBE_MIN = "aube_min"
CONF_VOLETS = "volets"
CONF_VOLETS_SOLEIL = "volets_soleil"
CONF_VOLETS_POSITION = "volets_position"
CONF_VOLETS_SOLEIL_LEVER = "volets_soleil_lever"
# Couleur de la lumière de réveil. La température de couleur était déjà lue par
# la rampe, mais aucun champ ne permettait de la renseigner.
CONF_LUMIERE_COULEUR = "lumiere_couleur"
# Scène appliquée lorsque la rampe atteint son maximum
CONF_LUMIERE_SCENE = "lumiere_scene"
# Forme de la montée : linéaire, ou douce au démarrage
CONF_LUMIERE_COURBE = "lumiere_courbe"

COURBE_LINEAIRE = "lineaire"
COURBE_DOUCE = "douce"
COURBES_OPTIONS = {
    COURBE_DOUCE: "Douce — progression lente au début, plus franche ensuite",
    COURBE_LINEAIRE: "Linéaire — progression régulière",
}
CONF_NOTIFICATION_ACTIVEE = "notification_activee"
CONF_NOTIFY_DEVICE = "notify_device"
CONF_NOTIF_TITRE = "notif_titre"
CONF_NOTIF_MESSAGE = "notif_message"
CONF_TTS_ACTIVEE = "tts_activee"
# Enceinte de sortie (media_player)
CONF_TTS_ENTITY = "tts_entity"
# Moteur de synthèse vocale (entité du domaine tts).
# tts.speak cible le moteur et reçoit l'enceinte en paramètre séparé : sans
# lui, l'appel était rejeté et le TTS ne fonctionnait jamais.
CONF_TTS_ENGINE = "tts_engine"
CONF_TTS_MESSAGE = "tts_message"
CONF_PRESENCE = "presence"
CONF_WORKDAY_SENSOR = "workday_sensor"
CONF_IGNORER_FERIES = "ignorer_feries"
CONF_VACANCES_SCOLAIRES_CALENDAR = "vacances_scolaires_calendar"
CONF_IGNORER_VACANCES_SCOLAIRE = "ignorer_vacances_scolaire"
CONF_MODE_VACANCES = "mode_vacances"
CONF_MODE_VACANCES_ENTITY = "mode_vacances_entity"
CONF_SKIP_PROCHAIN = "skip_prochain"
CONF_PONCTUEL = "ponctuel"
CONF_ADAPTATIF_AGENDA = "adaptatif_agenda"
CONF_AGENDA_ENTITY = "agenda_entity"
CONF_AGENDA_MARGE_MIN = "agenda_marge_min"
CONF_SNOOZE_DUREE = "snooze_duree"
CONF_SNOOZE_MAX = "snooze_max"
CONF_ESCALADE_MIN = "escalade_min"
CONF_MOUVEMENT_SDB = "mouvement_sdb"
CONF_MOUVEMENT_STOP = "mouvement_stop"
CONF_LEVER_ANTICIPE = "lever_anticippe"
CONF_MOUVEMENT_CUISINE = "mouvement_cuisine"
# Capteurs indiquant qu'une personne est couchée : tapis/capteur sous matelas
# (Withings Sleep…), radar millimétrique, capteur de présence de lit.
# Un sélecteur multiple remplace les deux champs Withings figés, qui limitaient
# à deux capteurs d'une seule marque.
CONF_PRESENCE_LIT_SENSORS = "presence_lit_sensors"
# Conservées pour la migration des configurations créées avant le schéma 4
CONF_WITHINGS_BED_1 = "withings_bed_1"
CONF_WITHINGS_BED_2 = "withings_bed_2"
CONF_BRIGHTNESS_MAX = "brightness_max"
CONF_DUREE_PROGRESSIVE = "duree_progressive"
CONF_SCENES_MATIN = "scenes_matin"
CONF_SCENE_MATIN_ENTITIES = "scene_matin_entities"
CONF_ESCALADE_INTELLIGENTE = "escalade_intelligente"
CONF_BRIEFING_MULTI_CAPTEURS = "briefing_multi_capteurs"
CONF_CAPTEUR_QUALITE_AIR = "capteur_qualite_air"
CONF_CAPTEUR_CO2 = "capteur_co2"

# ── AI Task ───────────────────────────────────────────────────
CONF_AI_BRIEFING = "ai_briefing"
CONF_AI_TASK_ENTITY = "ai_task_entity"
CONF_AI_MUSIQUE_ADAPT = "ai_musique_adapt"
CONF_AI_SUGGESTION_HEURE = "ai_suggestion_heure"
CONF_AI_BILAN_HEBDO = "ai_bilan_hebdo"
# Capteurs de sommeil à transmettre au bilan hebdomadaire (Withings, Fitbit,
# Oura, Google Fit…). Le bilan ne recevait auparavant que le compteur de
# snoozes : il commentait donc le réveil sans voir aucune mesure de sommeil.
CONF_SOMMEIL_SENSORS = "sommeil_sensors"

# Planification des tâches IA — l'heure de la suggestion du soir était figée à
# 21:30 dans le code, et le bilan hebdomadaire n'était déclenchable que par
# appel de service.
CONF_AI_SUGGESTION_HEURE_PLANIF = "ai_suggestion_heure_planif"
CONF_AI_BILAN_JOUR = "ai_bilan_jour"
CONF_AI_BILAN_HEURE_PLANIF = "ai_bilan_heure_planif"
DEFAULT_AI_SUGGESTION_HEURE = "21:30"
DEFAULT_AI_BILAN_HEURE = "20:00"
DEFAULT_AI_BILAN_JOUR = "dimanche"

# Mode de travail. Deux façons de le renseigner : une valeur fixe, ou une entité
# (input_select, capteur, calendrier) pour un mode qui change d'un jour à l'autre.
CONF_MODE_TRAVAIL = "mode_travail"
CONF_MODE_TRAVAIL_ENTITY = "mode_travail_entity"

# N'énoncer le briefing que les jours travaillés, d'après le capteur workday
CONF_AI_BRIEFING_SI_TRAVAIL = "ai_briefing_si_travail"

# Styles musicaux selon la météo, transmis à l'IA de choix de musique
CONF_MUSIQUE_STYLE_SOLEIL = "musique_style_soleil"
CONF_MUSIQUE_STYLE_NUAGEUX = "musique_style_nuageux"
CONF_MUSIQUE_STYLE_PLUIE = "musique_style_pluie"
CONF_MUSIQUE_STYLE_NEIGE = "musique_style_neige"
CONF_MUSIQUE_STYLE_TEMPETE = "musique_style_tempete"
CONF_AI_VERIF_LEVER = "ai_verif_lever"
CONF_AI_CAMERA_VERIF = "ai_camera_verif"
CONF_AI_CUSTOM_ENABLED = "ai_custom_enabled"
CONF_AI_CUSTOM_PROMPT = "ai_custom_prompt"
CONF_AI_CUSTOM_TRIGGER = "ai_custom_trigger"
CONF_AI_CUSTOM_ENTITIES = "ai_custom_entities"
CONF_AI_CUSTOM_NOTIFY = "ai_custom_notify"
CONF_AI_CUSTOM_TASKS = "ai_custom_tasks"
CONF_WEATHER_ENTITY = "weather_entity"
CONF_TRAJET_SENSOR = "trajet_sensor"
CONF_BATTERIE_SENSOR = "batterie_sensor"

# ── Valeurs par défaut ────────────────────────────────────────
DEFAULT_VOLUME_INITIAL = 0.05
DEFAULT_VOLUME_FINAL = 0.35
DEFAULT_VOLUME_DUREE = 5
DEFAULT_BRIGHTNESS_MAX = 200
DEFAULT_DUREE_PROGRESSIVE = 20
DEFAULT_PLAYLIST = "FV:2/7"
# Aucun destinataire par défaut : la valeur précédente désignait un téléphone
# précis, si bien qu'une installation sans appareil détecté tentait d'envoyer
# ses notifications à un service inexistant.
DEFAULT_NOTIFY_DEVICE = ""
DEFAULT_SNOOZE_DUREE = 5
DEFAULT_SNOOZE_MAX = 2
DEFAULT_ESCALADE_MIN = 5
DEFAULT_PRECHAUFFE_MIN = 45
DEFAULT_CAFETIERE_MIN = 10
DEFAULT_AUBE_MIN = 20
DEFAULT_NOTIF_TITRE = "⏰ Réveil"
DEFAULT_NOTIF_MESSAGE = "Il est l'heure de se lever !"
DEFAULT_TTS_MESSAGE = "Bonjour. Bonne journée !"
DEFAULT_AGENDA_MARGE_MIN = 90
DEFAULT_AI_BRIEFING = False
DEFAULT_AI_MUSIQUE_ADAPT = False
DEFAULT_AI_SUGGESTION_HEURE = False
DEFAULT_AI_BILAN_HEBDO = False
DEFAULT_AI_VERIF_LEVER = False

# ── Jours ─────────────────────────────────────────────────────
JOURS_OPTIONS = {
    "tous": "Tous les jours",
    "semaine": "Lundi au vendredi",
    "weekend": "Samedi et dimanche",
    "personnalise": "Personnalisé",
}

JOURS_LIST = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]

JOURS_NUM = {
    "lundi": 0,
    "mardi": 1,
    "mercredi": 2,
    "jeudi": 3,
    "vendredi": 4,
    "samedi": 5,
    "dimanche": 6,
}

JOURS_LABELS = {
    0: "Lundi",
    1: "Mardi",
    2: "Mercredi",
    3: "Jeudi",
    4: "Vendredi",
    5: "Samedi",
    6: "Dimanche",
}

# ── États ─────────────────────────────────────────────────────
STATUT_IDLE = "idle"
STATUT_PREWAKE = "prewake"
STATUT_RINGING = "ringing"
STATUT_SNOOZED = "snoozed"
STATUT_DONE = "done"
STATUT_INACTIF = "inactif"

ETAT_OPTIONS = [STATUT_IDLE, STATUT_PREWAKE, STATUT_RINGING, STATUT_SNOOZED, STATUT_DONE]

# ── Platforms ─────────────────────────────────────────────────
PLATFORMS = ["switch", "time", "select", "sensor", "button", "number", "binary_sensor"]

# ── Services ─────────────────────────────────────────────────
SERVICE_DECLENCHER = "declencher"
SERVICE_SNOOZE = "snooze"
SERVICE_STOP = "stop"
SERVICE_SKIP = "sauter_prochain"
SERVICE_RESET = "reset"
SERVICE_BILAN_HEBDO = "bilan_hebdo"

# ── Modes de travail ────────────────────────────────────────────

MODE_TRAVAIL_PRESENTIEL = "presentiel"
MODE_TRAVAIL_TELETRAVAIL = "teletravail"
MODE_TRAVAIL_INDETERMINE = "indetermine"

MODE_TRAVAIL_OPTIONS = {
    MODE_TRAVAIL_INDETERMINE: "Non précisé",
    MODE_TRAVAIL_PRESENTIEL: "Présentiel (trajet à prévoir)",
    MODE_TRAVAIL_TELETRAVAIL: "Télétravail (pas de trajet)",
}

# Reconnaissance du mode depuis l'état d'une entité, pour accepter les
# input_select rédigés librement par l'utilisateur.
MOTS_TELETRAVAIL = ("teletravail", "télétravail", "remote", "home", "maison", "distance")
MOTS_PRESENTIEL = ("presentiel", "présentiel", "bureau", "office", "site", "onsite")

# ── Regroupement des conditions météo ───────────────────────────
# Les états publiés par les intégrations météo de Home Assistant sont nombreux ;
# on les ramène à cinq familles pour rester configurable sans 15 champs.

METEO_FAMILLES = {
    "soleil": ("sunny", "clear-night", "clear"),
    "nuageux": ("partlycloudy", "cloudy", "fog"),
    "pluie": ("rainy", "pouring", "lightning-rainy", "snowy-rainy", "hail"),
    "neige": ("snowy",),
    "tempete": ("lightning", "windy", "windy-variant", "exceptional"),
}


def famille_meteo(etat: str | None) -> str:
    """Famille météo correspondant à un état d'entité weather."""
    if not etat:
        return "nuageux"
    etat = etat.lower()
    for famille, valeurs in METEO_FAMILLES.items():
        if etat in valeurs:
            return famille
    return "nuageux"
