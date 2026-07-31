"""Constantes pour l'intégration Réveil progressif."""

DOMAIN = "reveil_progressif"

# ── Clés config flow ──────────────────────────────────────────
CONF_HEURE = "heure"
CONF_JOURS = "jours"
CONF_JOURS_PERSO = "jours_perso"
CONF_LUMIERE = "lumiere"
CONF_LUMIERE_ACTIVEE = "lumiere_activee"
CONF_LUMIERE_TEMP_COULEUR = "lumiere_temp_couleur"
CONF_MUSIQUE_ACTIVEE = "musique_activee"
CONF_MEDIA_PLAYER = "media_player"
CONF_PLAYLIST = "playlist"
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
CONF_NOTIFICATION_ACTIVEE = "notification_activee"
CONF_NOTIFY_DEVICE = "notify_device"
CONF_NOTIF_TITRE = "notif_titre"
CONF_NOTIF_MESSAGE = "notif_message"
CONF_TTS_ACTIVEE = "tts_activee"
CONF_TTS_ENTITY = "tts_entity"
CONF_PRESENCE = "presence"
CONF_WORKDAY_SENSOR = "workday_sensor"
CONF_IGNORER_FERIES = "ignorer_feries"
CONF_VACANCES_SCOLAIRES_CALENDAR = "vacances_scolaires_calendar"
CONF_IGNORER_VACANCES_SCOLAIRE = "ignorer_vacances_scolaire"
CONF_MODE_VACANCES = "mode_vacances"
CONF_SKIP_PROCHAIN = "skip_prochain"
CONF_PONCTUEL = "ponctuel"
CONF_ADAPTATIF_AGENDA = "adaptatif_agenda"
CONF_AGENDA_ENTITY = "agenda_entity"
CONF_AGENDA_MARGE_MIN = "agenda_marge_min"
CONF_SOMMEIL_PHASE = "sommeil_phase"
CONF_SOMMEIL_FENETRE_MIN = "sommeil_fenetre_min"
CONF_SNOOZE_DUREE = "snooze_duree"
CONF_SNOOZE_MAX = "snooze_max"
CONF_ESCALADE_MIN = "escalade_min"
CONF_MOUVEMENT_SDB = "mouvement_sdb"
CONF_MOUVEMENT_STOP = "mouvement_stop"
CONF_LEVER_ANTICIPE = "lever_anticippe"
CONF_MOUVEMENT_CUISINE = "mouvement_cuisine"
CONF_WITHINGS_BED_1 = "withings_bed_1"
CONF_WITHINGS_BED_2 = "withings_bed_2"
CONF_BRIGHTNESS_MAX = "brightness_max"
CONF_DUREE_PROGRESSIVE = "duree_progressive"

# ── Valeurs par défaut ────────────────────────────────────────
DEFAULT_VOLUME_INITIAL = 0.05
DEFAULT_VOLUME_FINAL = 0.35
DEFAULT_VOLUME_DUREE = 5
DEFAULT_BRIGHTNESS_MAX = 200
DEFAULT_DUREE_PROGRESSIVE = 20
DEFAULT_PLAYLIST = "FV:2/7"
DEFAULT_NOTIFY_DEVICE = "notify.mobile_app_sm_g991u1"
DEFAULT_SNOOZE_DUREE = 5
DEFAULT_SNOOZE_MAX = 2
DEFAULT_ESCALADE_MIN = 5
DEFAULT_PRECHAUFFE_MIN = 45
DEFAULT_CAFETIERE_MIN = 10
DEFAULT_AUBE_MIN = 20
DEFAULT_NOTIF_TITRE = "⏰ Réveil"
DEFAULT_NOTIF_MESSAGE = "Il est l'heure de se lever !"
DEFAULT_AGENDA_MARGE_MIN = 90
DEFAULT_SOMMEIL_FENETRE_MIN = 20

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