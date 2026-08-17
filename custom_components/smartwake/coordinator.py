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
import math
from datetime import date, datetime, time, timedelta
from typing import Any, Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, State, callback
from homeassistant.helpers.event import (
    async_track_point_in_time,
    async_track_state_change_event,
    async_track_time_change,
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
    CONF_ESCALADE_INTELLIGENTE,
    CONF_ESCALADE_MIN,
    CONF_HEURE,
    CONF_HEURE_LUNDI,
    CONF_HEURE_MARDI,
    CONF_HEURE_MERCREDI,
    CONF_HEURE_JEUDI,
    CONF_HEURE_VENDREDI,
    CONF_HEURE_SAMEDI,
    CONF_HEURE_DIMANCHE,
    CONF_MODE_HEURE,
    CONF_RATTRAPAGE_MIN,
    DEFAULT_RATTRAPAGE_MIN,
    CONF_IGNORER_FERIES,
    CONF_IGNORER_VACANCES_SCOLAIRE,
    CONF_VACANCES_SCOLAIRES_CALENDAR,
    CONF_AI_BRIEFING,
    CONF_AI_MUSIQUE_ADAPT,
    CONF_AI_SUGGESTION_HEURE,
    CONF_AI_SUGGESTION_HEURE_PLANIF,
    CONF_AI_BILAN_JOUR,
    CONF_VERIF_NOCTURNE,
    CONF_VERIF_NOCTURNE_ENTITIES,
    CONF_VERIF_NOCTURNE_HEURE,
    CONF_VERIF_NOCTURNE_MESSAGE,
    DEFAULT_VERIF_NOCTURNE_HEURE,
    DEFAULT_VERIF_NOCTURNE_MESSAGE,
    CONF_AI_BILAN_HEURE_PLANIF,
    CONF_AI_BILAN_HEBDO,
    DEFAULT_AI_SUGGESTION_HEURE,
    DEFAULT_AI_BILAN_HEURE,
    DEFAULT_AI_BILAN_JOUR,
    JOURS_LIST,
    CONF_AI_VERIF_LEVER,
    CONF_AI_CUSTOM_ENABLED,
    CONF_AI_CUSTOM_TASKS,
    CONF_ADAPTATIF_AGENDA,
    CONF_AGENDA_ENTITY,
    CONF_AGENDA_MARGE_MIN,
    CONF_JOURS,
    CONF_JOURS_PERSO,
    CONF_LEVER_ANTICIPE,
    CONF_LUMIERE,
    CONF_LUMIERE_ACTIVEE,
    CONF_LUMIERE_COULEUR,
    CONF_LUMIERE_COURBE,
    CONF_LUMIERE_SCENE,
    CONF_LUMIERE_TEMP_COULEUR,
    COURBE_DOUCE,
    CONF_MOUVEMENT_CUISINE,
    CONF_MOUVEMENT_SDB,
    CONF_MOUVEMENT_STOP,
    CONF_MEDIA_PLAYER,
    CONF_MODE_VACANCES,
    CONF_MODE_VACANCES_ENTITY,
    CONF_MUSIQUE_ACTIVEE,
    CONF_NOTIF_MESSAGE,
    CONF_NOTIF_TITRE,
    CONF_NOTIFICATION_ACTIVEE,
    CONF_NOTIFY_DEVICE,
    CONF_PLAYLIST,
    CONF_PLAYLIST_DOUCE,
    CONF_PLAYLIST_ENERGIQUE,
    CONF_PONCTUEL,
    CONF_PRECHAUFFE_MIN,
    CONF_PRESENCE,
    CONF_RADIATEUR,
    CONF_SCENE_MATIN_ENTITIES,
    CONF_SCENES_MATIN,
    CONF_SKIP_PROCHAIN,
    CONF_SNOOZE_DUREE,
    CONF_SNOOZE_MAX,
    CONF_TTS_ACTIVEE,
    CONF_TTS_ENGINE,
    CONF_TTS_ENTITY,
    CONF_TTS_MESSAGE,
    CONF_VOLUME_DUREE,
    CONF_VOLUME_FINAL,
    CONF_VOLUME_INITIAL,
    CONF_VOLETS,
    CONF_VOLETS_POSITION,
    CONF_VOLETS_SOLEIL,
    CONF_WEATHER_ENTITY,
    CONF_PRESENCE_LIT_SENSORS,
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
    DEFAULT_TTS_MESSAGE,
    DEFAULT_PRECHAUFFE_MIN,
    DEFAULT_SNOOZE_DUREE,
    DEFAULT_SNOOZE_MAX,
    DEFAULT_AGENDA_MARGE_MIN,
    DEFAULT_VOLUME_DUREE,
    DEFAULT_VOLUME_FINAL,
    DEFAULT_VOLUME_INITIAL,
    JOURS_NUM,
    JOURS_OPTIONS,
    slugify,
    STATUT_DONE,
    STATUT_IDLE,
    STATUT_INACTIF,
    STATUT_PREWAKE,
    STATUT_RINGING,
    STATUT_SNOOZED,
)

_LOGGER = logging.getLogger(__name__)


def _jours_actifs(
    mode: str,
    jours_perso: list[str] | None = None,
    heures_par_jour: dict[int, str | None] | None = None,
) -> set[int]:
    """Retourne l'ensemble des numéros de jour (0=lundi) actifs.

    En mode « par_jour », un jour est actif si une heure est configurée pour ce
    jour. Sans cela, le réveil ne sonnait jamais en mode « par_jour » : la
    fonction retournait un ensemble vide car ce mode n'était pas reconnu.
    """
    if mode == "tous":
        return set(range(7))
    if mode == "semaine":
        return {0, 1, 2, 3, 4}
    if mode == "weekend":
        return {5, 6}
    if mode == "par_jour" and heures_par_jour is not None:
        return {j for j, h in heures_par_jour.items() if h}
    if mode == "personnalise":
        if jours_perso:
            return {JOURS_NUM[j] for j in jours_perso if j in JOURS_NUM}
        return set()  # personnalise vide = aucun jour
    if mode in JOURS_NUM:
        return {JOURS_NUM[mode]}
    return set(range(7))  # fallback pour mode inconnu


def _parse_heure(heure_str: str, defaut: str = "07:00") -> time:
    """Analyse « HH:MM ». Une valeur invalide ne doit pas interrompre le calcul
    du prochain réveil : l'exception remontait jusqu'au rafraîchissement du
    coordinator, laissant toutes les entités indisponibles."""
    for candidat in (heure_str, defaut):
        try:
            parts = str(candidat).split(":")
            return time(hour=int(parts[0]), minute=int(parts[1]))
        except (ValueError, IndexError, TypeError):
            continue
    return time(hour=7, minute=0)


class ReveilCoordinator(DataUpdateCoordinator):
    """Coordinateur du moteur de réveil."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"smartwake_{entry.entry_id}",
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
        self._cancel_mouvement: Callable | None = None
        self._cancel_rampes: list[asyncio.Task] = []
        self._cancel_snooze: asyncio.Task | None = None
        # Instant de reprise de la sonnerie, pour un compte à rebours réel.
        # Seule la durée configurée était exposée : l'interface affichait donc
        # « Re-sonne dans 5 min » sans jamais décompter.
        self._snooze_fin: datetime | None = None
        # Luminosité atteinte par la rampe, pour la reprendre après un snooze
        self._aube_niveau = 0
        # Vrai si la rampe de lumière a déjà été jouée par le pré-réveil,
        # pour ne pas la relancer à l'heure du réveil
        self._aube_faite = False
        self._aube_niveau = 0
        self._snooze_fin = None
        self._reveil_en_cours = False
        self._snooze_count = 0
        self._skip_prochain = False
        # États d'origine des appareils modifiés pendant le cycle (prewake
        # inclus), pour les restaurer au stop. Capturés au démarrage du
        # pré-réveil — avant que l'aube ne modifie la lumière — et non à H,
        # sinon on restaurait l'état post-aube au lieu de l'état réel d'origine.
        self._etats_initiaux: dict[str, dict[str, Any]] = {}
        # Vrai si la sonnerie (H) doit être déclenchée à la reprise du snooze
        # alors que le cycle en cours était encore en phase prewake.
        self._pending_ringing = False
        # Statut avant le snooze (prewake ou ringing), pour reprendre la bonne
        # phase à l'issue : un snooze pendant l'aube reprend l'aube, un snooze
        # pendant la sonnerie reprend la sonnerie.
        self._statut_avant_snooze: str | None = None
        # Date de l'occurrence sautée, pour que le saut ne vaille qu'une fois
        self._skip_date: date | None = None
        # Marque une écriture de config provoquée par une entité
        self._internal_update = False
        self._unsub_listeners: list[Callable] = []
        self._learning: Any = None

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
    def snooze_fin(self) -> datetime | None:
        """Instant auquel la sonnerie reprend, pendant un snooze."""
        return self._snooze_fin if self._statut == STATUT_SNOOZED else None

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
            # Le saut ne vaut que pour l'occurrence visée : dès qu'elle est
            # passée, on le consomme, sinon le réveil ne sonnerait plus jamais.
            if (
                self._skip_prochain
                and self._skip_date is not None
                and dt_util.now().date() > self._skip_date
            ):
                self._skip_prochain = False
                self._skip_date = None
                _LOGGER.debug("Saut du prochain consommé pour '%s'", self.entry.title)

            # Filet de sécurité : le déclencheur est à usage unique, on le
            # réarme s'il a été consommé sans qu'un cycle ait démarré.
            if self._cancel_trigger is None:
                self._planifier_trigger()
            else:
                self._calculer_prochain()
        return {
            "actif": self._actif,
            "statut": self._statut,
            "prochain": self._prochain,
            "snooze_count": self._snooze_count,
            "skip_prochain": self._skip_prochain,
        }

    async def async_config_entry_first_refresh(self) -> None:
        """Premier rafraîchissement — watchdog + planification + learning."""
        self._calculer_prochain()
        # Réarme les déclencheurs si le réveil était actif : sans cela, aucun
        # async_track_* n'était enregistré au démarrage de Home Assistant et
        # le réveil ne sonnait pas tant qu'un réglage n'avait pas été modifié.
        if self._actif:
            self._planifier_trigger()
            self._rattraper_reveil_manque()
        await super().async_config_entry_first_refresh()
        # Watchdog : vérifier l'armement au démarrage HA
        self._watchdog()
        # Écouter les actions de notification mobile (Snooze / Stop)
        self._setup_notification_actions()
        # Initialiser le module d'apprentissage
        from .learning import LearningManager
        self._learning = LearningManager(self.hass, self.entry.entry_id)
        await self._learning.async_load()

    @callback
    def _rattraper_reveil_manque(self) -> None:
        """Sonne malgré tout si un redémarrage a fait manquer l'heure de peu.

        Sans cela, un redémarrage de Home Assistant juste avant le réveil — mise
        à jour nocturne, coupure de courant — faisait purement et simplement
        rater le réveil : l'occurrence du jour était considérée comme passée.
        """
        cfg = self.entry.data
        tolerance = cfg.get(CONF_RATTRAPAGE_MIN, DEFAULT_RATTRAPAGE_MIN)
        if tolerance <= 0:
            return

        now = dt_util.now()
        heure = _parse_heure(cfg.get(CONF_HEURE, "07:00"))
        if cfg.get(CONF_MODE_HEURE, "unique") == "par_jour":
            heures = self._heures_par_jour()
            if heures.get(now.weekday()):
                heure = _parse_heure(heures[now.weekday()])

        prevu = self._instant_local(now.date(), heure)
        retard = (now - prevu).total_seconds() / 60

        if 0 < retard <= tolerance and self._sonne_aujourd_hui(now) \
                and not self._reveil_en_cours:
            _LOGGER.warning(
                "Réveil '%s' rattrapé : heure dépassée de %.0f min au démarrage "
                "(tolérance %d min)", self.entry.title, retard, tolerance,
            )
            self._log_event(f"Réveil rattrapé (+{retard:.0f} min)")
            self._cancel_cycle = self.hass.async_create_task(self._executer_cycle())

    @property
    def entity_id_prefix(self) -> str:
        """Préfixe des entity_id des entités par jour.

        Les entités sont nommées time.<slug(reveil+nom_entite)>_heure_<jour>.
        Pour un réveil « Chambre 1er Réveil » et une entité « Heure Lundi »,
        l'entity_id est time.chambre_1er_reveil_heure_lundi.
        Le slug combine le titre du réveil et le nom convivial de l'entité.
        """
        try:
            from homeassistant.util import slugify
            return slugify(self.entry.title)
        except ImportError:
            return self.entry.title.lower().replace(" ", "_")

    def _heures_par_jour(self) -> dict[int, str | None]:
        """Heures configurées par jour de la semaine (0 = lundi).

        Les heures sont stockées dans les entités time.<nom>_heure_<jour>,
        pas dans entry.data : la config ne contient que des valeurs par défaut,
        les vraies heures sont éditées via les entités time.*.
        """
        resultat: dict[int, str | None] = {}
        for idx, jour in enumerate(
            ("lundi", "mardi", "mercredi", "jeudi", "vendredi",
             "samedi", "dimanche")
        ):
            cle_cfg = f"heure_{jour}"
            heure = self.entry.data.get(cle_cfg)
            if not heure:
                # Les heures sont dans les entités time.*, pas dans entry.data
                entity_id = f"time.{self.entity_id_prefix}_heure_{jour}"
                etat = self.hass.states.get(entity_id)
                if etat and etat.state not in ("unknown", "unavailable"):
                    heure = etat.state
            resultat[idx] = heure if heure else None
        return resultat

    def _watchdog(self) -> None:
        """Vérifie au démarrage HA que l'alarme est cohérente + détecte les anomalies."""
        cfg = self.entry.data
        anomalies = []

        if self._actif and self._prochain is None:
            _LOGGER.warning(
                "Watchdog: réveil '%s' actif mais aucun prochain déclenchement — "
                "vérifiez la configuration des jours",
                self.entry.title,
            )
            anomalies.append("alarme_non_armee")
        elif self._actif:
            _LOGGER.info(
                "Watchdog: réveil '%s' armé, prochain déclenchement %s",
                self.entry.title,
                self._prochain,
            )

        # Détecter si HA a redémarré pendant la nuit (entre 22h et 8h)
        now = dt_util.now()
        if now.hour >= 22 or now.hour < 8:
            _LOGGER.warning(
                "Anomalie: HA a redémarré à %s (période nocturne) — vérifier que '%s' est armé",
                now.strftime("%H:%M"),
                self.entry.title,
            )
            anomalies.append("redemarrage_nocturne")

        if anomalies:
            self._fire_event("smartwake_anomalie", type=anomalies)
            self._log_event(f"Anomalie détectée: {', '.join(anomalies)}")
            # Alerter l'utilisateur si notification configurée
            notify = cfg.get(CONF_NOTIFY_DEVICE)
            if notify and "alarme_non_armee" in anomalies:
                try:
                    self.hass.async_create_task(self._alerter_anomalie(notify, anomalies))
                except Exception:
                    pass

    async def _alerter_anomalie(self, notify_device: str, anomalies: list[str]) -> None:
        """Envoie une alerte si une anomalie est détectée."""
        msg = "⚠️ Anomalie SmartWAKE: " + ", ".join(anomalies)
        await self._notifier(notify_device, "⚠️ SmartWAKE Anomalie", msg)

    def _setup_notification_actions(self) -> None:
        """Écoute les actions REVEIL_SNOOZE / REVEIL_STOP depuis l'app mobile."""
        entry_id = self.entry.entry_id
        # Les actions portent l'identifiant de l'entrée : sans lui, avec
        # plusieurs réveils configurés, un appui sur Snooze agissait sur tous.
        suffixe = f"_{entry_id}"

        @callback
        def _handle_notification_action(event):
            action = event.data.get("action")
            if not action:
                return

            if action.startswith("REVEIL_SNOOZE"):
                if action != "REVEIL_SNOOZE" and not action.endswith(suffixe):
                    return  # destiné à un autre réveil
                _LOGGER.info("Action Snooze reçue pour '%s'", self.entry.title)
                self.hass.async_create_task(self.snooze())
            elif action.startswith("REVEIL_STOP"):
                if action != "REVEIL_STOP" and not action.endswith(suffixe):
                    return
                _LOGGER.info("Action Stop reçue pour '%s'", self.entry.title)
                self.hass.async_create_task(self.stop(raison="notification"))
            elif action and action.startswith("REVEIL_ACCEPTER_"):
                # Suggestion IA acceptée — valider et appliquer l'heure
                heure = action.replace("REVEIL_ACCEPTER_", "")
                import re
                m = re.match(r"^(\d{1,2}):(\d{2})$", heure)
                if not m or not (0 <= int(m.group(1)) < 24 and 0 <= int(m.group(2)) < 60):
                    _LOGGER.warning("Heure invalide reçue via notification: %s", heure)
                    return
                _LOGGER.info("Suggestion IA acceptée: %s", heure)
                self._log_event("Suggestion IA acceptée")
                self.hass.async_create_task(self.set_heure(heure))
            elif action == "REVEIL_REFUSER":
                _LOGGER.info("Suggestion IA refusée")
                self._log_event("Suggestion IA refusée")

        # Le désabonnement doit être conservé : sans cela l'écouteur survivait
        # à chaque rechargement et un appui « Snooze » était traité N fois.
        self._unsub_listeners.append(
            self.hass.bus.async_listen(
                "mobile_app_notification_action", _handle_notification_action
            )
        )

        # Créneau du soir : suggestion d'heure et tâches IA « on_evening »
        cfg = self.entry.data
        if cfg.get(CONF_AI_SUGGESTION_HEURE) or cfg.get(CONF_AI_CUSTOM_TASKS) \
                or cfg.get(CONF_AI_CUSTOM_ENABLED):
            self._setup_ai_suggestion()

    @staticmethod
    def _heure_minute(valeur: str | None, defaut: str) -> tuple[int, int]:
        """Analyse une heure « HH:MM » avec repli sur la valeur par défaut."""
        for candidat in (valeur, defaut):
            if not candidat:
                continue
            try:
                parts = str(candidat).split(":")
                h, m = int(parts[0]), int(parts[1])
                if 0 <= h < 24 and 0 <= m < 60:
                    return h, m
            except (ValueError, IndexError):
                continue
        return 21, 30

    def _setup_ai_suggestion(self) -> None:
        """Planifie le traitement IA du soir, à l'heure configurée.

        L'heure était figée à 21:30 dans le code. Le bilan hebdomadaire n'était
        par ailleurs déclenchable que par appel de service : il est désormais
        programmé au jour et à l'heure choisis.
        """
        cfg = self.entry.data

        heure, minute = self._heure_minute(
            cfg.get(CONF_AI_SUGGESTION_HEURE_PLANIF), DEFAULT_AI_SUGGESTION_HEURE
        )
        self._unsub_listeners.append(
            async_track_time_change(
                self.hass, self._ai_suggestion_callback,
                hour=heure, minute=minute, second=0,
            )
        )
        _LOGGER.debug(
            "Traitement IA du soir planifié à %02d:%02d pour '%s'",
            heure, minute, self.entry.title,
        )

        if cfg.get(CONF_AI_BILAN_HEBDO):
            h_bilan, m_bilan = self._heure_minute(
                cfg.get(CONF_AI_BILAN_HEURE_PLANIF), DEFAULT_AI_BILAN_HEURE
            )
            self._unsub_listeners.append(
                async_track_time_change(
                    self.hass, self._ai_bilan_callback,
                    hour=h_bilan, minute=m_bilan, second=0,
                )
            )
            _LOGGER.debug(
                "Bilan hebdomadaire planifié le %s à %02d:%02d pour '%s'",
                cfg.get(CONF_AI_BILAN_JOUR, DEFAULT_AI_BILAN_JOUR),
                h_bilan, m_bilan, self.entry.title,
            )

        # Vérification nocturne : alerte si une ouverture reste ouverte
        if cfg.get(CONF_VERIF_NOCTURNE, False):
            h_verif, m_verif = self._heure_minute(
                cfg.get(CONF_VERIF_NOCTURNE_HEURE), DEFAULT_VERIF_NOCTURNE_HEURE
            )
            self._unsub_listeners.append(
                async_track_time_change(
                    self.hass, self._verif_nocturne_callback,
                    hour=h_verif, minute=m_verif, second=0,
                )
            )
            _LOGGER.debug(
                "Vérification nocturne planifiée à %02d:%02d pour '%s'",
                h_verif, m_verif, self.entry.title,
            )

    @callback
    def _verif_nocturne_callback(self, now: datetime) -> None:
        """Vérifie les ouvertures et alerte si l'une reste ouverte.

        Contrairement aux tâches IA, c'est une logique déterministe : on
        compare l'état attendu (« fermé ») à l'état réel de chaque entité
        désignée. Aucun risque d'hallucination, et ça fonctionne même sans
        modèle IA configuré.
        """
        cfg = self.entry.data
        entites = cfg.get(CONF_VERIF_NOCTURNE_ENTITIES, [])
        if not entites:
            return

        # États considérés comme « fermé » selon le domaine.
        # lock.locked = sécurisé (fermé), lock.unlocked = ouvert
        FERME = {"off", "closed", "locked", "not_home", "0"}

        ouvertes = []
        for entity_id in entites:
            etat = self.hass.states.get(entity_id)
            if etat is None or etat.state in ("unknown", "unavailable"):
                continue
            if etat.state not in FERME:
                fn = etat.attributes.get("friendly_name", entity_id)
                ouvertes.append(f"• {fn} ({etat.state})")

        if not ouvertes:
            _LOGGER.debug("Vérification nocturne '%s' : tout est fermé", self.entry.title)
            return

        message = cfg.get(CONF_VERIF_NOCTURNE_MESSAGE, DEFAULT_VERIF_NOCTURNE_MESSAGE)
        corps = f"{message}\n" + "\n".join(ouvertes)
        _LOGGER.info("Vérification nocturne '%s' : %d ouverture(s)", self.entry.title, len(ouvertes))
        self._log_event(f"Vérif nocturne : {len(ouvertes)} ouverture(s)")
        self.hass.async_create_task(
            self._notifier(
                cfg.get(CONF_NOTIFY_DEVICE),
                "🔒 Vérification nocturne",
                corps,
            )
        )

    @callback
    def _ai_bilan_callback(self, now: datetime) -> None:
        """Déclenche le bilan hebdomadaire le jour choisi."""
        jour = self.entry.data.get(CONF_AI_BILAN_JOUR, DEFAULT_AI_BILAN_JOUR)
        attendu = JOURS_LIST.index(jour) if jour in JOURS_LIST else 6
        if now.weekday() != attendu:
            return
        self.hass.async_create_task(self.bilan_hebdo_ia())

    @callback
    def _ai_suggestion_callback(self, now: datetime) -> None:
        """Callback du soir — suggestion d'heure et tâches IA « on_evening »."""
        if not self._actif:
            return
        cfg = self.entry.data
        if cfg.get(CONF_AI_SUGGESTION_HEURE):
            self.hass.async_create_task(self._run_ai_suggestion())
        # Le déclencheur « on_evening » était proposé dans l'interface mais
        # jamais émis : une tâche IA configurée « Le soir » ne s'exécutait pas.
        if cfg.get(CONF_AI_CUSTOM_ENABLED) or cfg.get(CONF_AI_CUSTOM_TASKS):
            self.hass.async_create_task(self._run_custom_ai("on_evening"))

    async def _run_ai_suggestion(self) -> None:
        """Génère et envoie une suggestion d'heure via IA + notification actionnable."""
        from .ai import suggest_wake_time
        cfg = self.entry.data
        current_time = cfg.get(CONF_HEURE, "07:00")
        suggestion = await suggest_wake_time(self.hass, cfg, current_time)
        if not suggestion or not suggestion.get("decaler"):
            return

        heure_proposee = suggestion.get("heure_proposee", "")
        raison = suggestion.get("raison", "")
        notify_device = cfg.get(CONF_NOTIFY_DEVICE, "")
        if not notify_device:
            return

        if await self._notifier(
            notify_device,
            "⏰ Suggestion réveil",
            f"Demain : {heure_proposee} ? {raison}",
            actions=[
                {"action": f"REVEIL_ACCEPTER_{heure_proposee}", "title": "Accepter"},
                {"action": "REVEIL_REFUSER", "title": f"Garder {current_time}"},
            ],
        ):
            self._log_event("Suggestion IA envoyée")

    async def async_shutdown(self) -> None:
        if self._cancel_trigger:
            self._cancel_trigger()
            self._cancel_trigger = None
        if self._cancel_prewake:
            self._cancel_prewake()
            self._cancel_prewake = None
        if self._cancel_mouvement:
            self._cancel_mouvement()
            self._cancel_mouvement = None
        # Écouteurs longue durée (actions de notification, suggestion du soir) :
        # ils n'étaient jamais libérés et s'accumulaient à chaque rechargement.
        for unsub in self._unsub_listeners:
            try:
                unsub()
            except Exception as exc:  # noqa: BLE001 - nettoyage best effort
                _LOGGER.debug("Désabonnement impossible: %s", exc)
        self._unsub_listeners.clear()
        for task in (self._cancel_cycle, self._cancel_escalade,
                     self._cancel_snooze, *self._cancel_rampes):
            if task and not task.done():
                task.cancel()
        _LOGGER.info("Réveil '%s' arrêté", self.entry.title)
        await super().async_shutdown()

    def _notify(self) -> None:
        self.async_set_updated_data({
            "actif": self._actif,
            "statut": self._statut,
            "prochain": self._prochain,
            "snooze_count": self._snooze_count,
            "skip_prochain": self._skip_prochain,
        })

    def _log_event(self, message: str, domain: str = "smartwake") -> None:
        """Journalise un événement dans le logbook HA."""
        try:
            self.hass.bus.async_fire(
                "logbook_entry",
                {
                    "name": self.entry.title,
                    "message": message,
                    "domain": domain,
                    "entity_id": f"sensor.{slugify(self.entry.title)}_statut",
                },
            )
        except Exception as exc:
            _LOGGER.debug("Erreur logbook: %s", exc)

    def _fire_event(self, event_type: str, **kwargs) -> None:
        """Émet un événement sur le bus HA pour les automatisations externes.

        Events disponibles:
          - smartwake_triggered  (heure, jours, prochain)
          - smartwake_stopped     (raison: manual|snooze_max|mouvement_sdb)
          - smartwake_snoozed     (count, max)
          - smartwake_escalade    (level)
          - smartwake_prewake     (phase: chauffage|aube|cafe)
          - smartwake_skipped     (prochain_reveil)
          - smartwake_activated   (heure, prochain)
          - smartwake_deactivated ()
        """
        try:
            self.hass.bus.async_fire(event_type, {
                "name": self.entry.title,
                "entry_id": self.entry.entry_id,
                "entity_id": f"switch.{slugify(self.entry.title)}_actif",
                **kwargs,
            })
        except Exception as exc:
            _LOGGER.debug("Erreur fire event %s: %s", event_type, exc)

    def _increment_stat(self, key: str) -> None:
        """Incrémente un compteur de statistiques."""
        if not hasattr(self, "_stats") or self._stats is None:
            self._stats = {
                "total_declenchements": 0,
                "total_snoozes": 0,
                "total_stops": 0,
                "dernier_reveil": None,
                "heures_lever": [],
            }
        if key in self._stats:
            self._stats[key] = self._stats.get(key, 0) + 1
        self._notify()

    # ── Activation ──────────────────────────────────────────────

    async def set_actif(self, actif: bool) -> None:
        self._actif = actif
        if actif:
            self._snooze_count = 0
            self._statut = STATUT_IDLE
            self._planifier_trigger()
            self._log_event("Réveil activé")
            self._fire_event("smartwake_activated", heure=self.config.get(CONF_HEURE, "07:00"), prochain=self._prochain.isoformat() if self._prochain else None)
        else:
            # Un cycle peut être en cours : il faut l'interrompre réellement.
            # Seuls les déclencheurs horaires étaient nettoyés, si bien que
            # couper l'interrupteur pendant la sonnerie laissait la musique
            # jouer et la rampe de volume continuer de monter.
            if self._reveil_en_cours or self._statut == STATUT_PREWAKE:
                await self._interrompre_cycle()
            self._statut = STATUT_INACTIF
            self._prochain = None
            self._nettoyer_triggers()
            self._reveil_en_cours = False
            self._aube_faite = False
            self._snooze_fin = None
            self._etats_initiaux = {}
            self._pending_ringing = False
            self._statut_avant_snooze = None
            self._log_event("Réveil désactivé")
            self._fire_event("smartwake_deactivated")
        self._notify()

    async def _interrompre_cycle(self) -> None:
        """Annule les tâches du cycle et éteint ce qui a été allumé."""
        for task in (self._cancel_cycle, self._cancel_escalade,
                     self._cancel_snooze, *self._cancel_rampes):
            if task and not task.done():
                task.cancel()
        self._cancel_cycle = None
        self._cancel_escalade = None
        self._cancel_snooze = None
        self._cancel_rampes = []
        if self._cancel_mouvement is not None:
            self._cancel_mouvement()
            self._cancel_mouvement = None

        cfg = self.entry.data
        if cfg.get(CONF_MUSIQUE_ACTIVEE) and cfg.get(CONF_MEDIA_PLAYER):
            try:
                await self.hass.services.async_call(
                    "media_player", "media_stop",
                    {"entity_id": cfg[CONF_MEDIA_PLAYER]},
                    blocking=True,
                )
            except Exception as exc:
                _LOGGER.error("Erreur arrêt musique: %s", exc)
        if cfg.get(CONF_LUMIERE_ACTIVEE) and cfg.get(CONF_LUMIERE):
            try:
                await self.hass.services.async_call(
                    "light", "turn_off", {"entity_id": cfg[CONF_LUMIERE]},
                    blocking=True,
                )
            except Exception as exc:
                _LOGGER.error("Erreur extinction: %s", exc)

    def _nettoyer_triggers(self) -> None:
        if self._cancel_trigger:
            self._cancel_trigger()
            self._cancel_trigger = None
        if self._cancel_prewake:
            self._cancel_prewake()
            self._cancel_prewake = None

    # ── Mise à jour config ─────────────────────────────────────

    def consume_internal_update(self) -> bool:
        """Indique si la dernière écriture de config vient d'une entité.

        Une écriture provoquée par une entité (curseur, heure, sélecteur) est
        déjà traitée sur place par _planifier_trigger() et _notify() : il ne
        faut surtout pas recharger l'entrée, sinon l'état d'exécution du
        coordinator est perdu et le réveil se retrouve désarmé.
        """
        interne = self._internal_update
        self._internal_update = False
        return interne

    def _ecrire_config(self, **valeurs: Any) -> None:
        """Écrit dans entry.data sans déclencher de rechargement.

        async_update_entry n'appelle les écouteurs que si les données ont
        réellement changé. Réécrire une valeur identique laisserait donc le
        drapeau armé, et c'est la modification d'options suivante qui serait
        prise pour une écriture interne — donc ignorée.
        """
        self._internal_update = True
        new_data = {**self.entry.data, **valeurs}
        modifie = self.hass.config_entries.async_update_entry(
            self.entry, data=new_data
        )
        if not modifie:
            self._internal_update = False

    async def set_heure(self, heure: str) -> None:
        """Met à jour l'heure du réveil.

        En mode « par_jour », l'heure de référence (CONF_HEURE) ne sert à rien
        : ce sont les entités time.<nom>_heure_<jour> qui pilotent la
        planification. Une suggestion IA acceptée via notification écrivait
        seulement CONF_HEURE, qui était ensuite ignorée par
        _calculer_prochain en mode par_jour — l'heure suggérée était perdue.
        On écrit aussi dans l'entité du jour courant si le mode est par_jour.
        """
        self._ecrire_config(**{CONF_HEURE: heure})
        cfg = self.entry.data
        if cfg.get(CONF_MODE_HEURE, "unique") == "par_jour":
            jour_courant = JOURS_LIST[dt_util.now().weekday()]
            entity_id = f"time.{self.entity_id_prefix}_heure_{jour_courant}"
            try:
                await self.hass.services.async_call(
                    "time", "set_value",
                    {"entity_id": entity_id, "time": heure},
                    blocking=True,
                )
                _LOGGER.info(
                    "Heure %s appliquée à %s (mode par_jour, jour courant)",
                    heure, entity_id,
                )
            except Exception as exc:
                _LOGGER.warning(
                    "Impossible d'appliquer l'heure à %s: %s. "
                    "L'heure de référence a été mise à jour mais le jour "
                    "courant n'a pas été modifié.", entity_id, exc,
                )
        if self._actif:
            self._planifier_trigger()
        self._notify()

    async def set_jours(self, mode: str) -> None:
        self._ecrire_config(**{CONF_JOURS: mode})
        if self._actif:
            self._planifier_trigger()
        self._notify()

    async def set_config_value(self, key: str, value: Any) -> None:
        """Met à jour une clé de configuration et replanifie."""
        self._ecrire_config(**{key: value})
        if self._actif:
            self._planifier_trigger()
        self._notify()

    async def set_skip(self, skip: bool) -> None:
        """Active ou annule le saut de la prochaine occurrence."""
        self._skip_prochain = skip
        # Le saut ne vaut que pour l'occurrence actuellement planifiée
        self._skip_date = self._prochain.date() if (skip and self._prochain) else None
        self._notify()

    # ── Conditions de déclenchement ────────────────────────────

    def _sonne_aujourd_hui(self, now: datetime) -> bool:
        """Vérifie si le réveil doit sonner aujourd'hui."""
        cfg = self.entry.data
        if not self._actif:
            return False
        # Mode vacances : booléen OU entité (calendar/input_boolean/binary_sensor/person)
        if cfg.get(CONF_MODE_VACANCES, False):
            return False
        if self._mode_vacances_entite():
            return False
        # Le saut ne s'applique qu'à l'occurrence visée. Sans cette borne, un
        # appui sur « Sauter prochain » désactivait le réveil définitivement,
        # car stop() — seul à remettre le drapeau à zéro — n'était plus atteint.
        if self._skip_prochain and (
            self._skip_date is None or now.date() == self._skip_date
        ):
            return False

        mode = cfg.get(CONF_JOURS, "semaine")
        jours_perso = cfg.get(CONF_JOURS_PERSO, [])
        heures_par_jour = self._heures_par_jour() if mode == "par_jour" else None
        jours = _jours_actifs(mode, jours_perso, heures_par_jour)
        if now.weekday() not in jours:
            return False

        # Jours fériés : le code vérifiait le workday_sensor, qui vaut « off »
        # le weekend. Or « off » signifie « pas un jour travaillé », pas « jour
        # férié ». Le code annulait donc le réveil tous les jours non travaillés,
        # y compris le weekend. On vérifie maintenant binary_sensor.jour_ferie
        # (interne), qui vaut « on » uniquement les jours fériés.
        if cfg.get(CONF_IGNORER_FERIES, True):
            entite_ferie = f"binary_sensor.{self.entity_id_prefix}_jour_ferie"
            state = self.hass.states.get(entite_ferie)
            if state and state.state == "on":
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

    def _capteurs_lit(self) -> list[str]:
        """Capteurs indiquant qu'une personne est couchée.

        Les deux anciens champs Withings restent lus au cas où la migration
        n'aurait pas encore eu lieu.
        """
        cfg = self.entry.data
        capteurs = list(cfg.get(CONF_PRESENCE_LIT_SENSORS) or [])
        for ancienne in (CONF_WITHINGS_BED_1, CONF_WITHINGS_BED_2):
            valeur = cfg.get(ancienne)
            if valeur and valeur not in capteurs:
                capteurs.append(valeur)
        return capteurs

    def _personne_au_lit(self) -> bool:
        """Vrai si au moins un capteur signale une personne couchée.

        Chemin synchrone (planification) : on se contente de l'état courant,
        binaire, numérique ou à valeur textuelle. Le rattrapage par dernier état
        connu, asynchrone, est réservé à la vérification du lever.
        """
        from .presence import interpreter_etat

        for entity in self._capteurs_lit():
            state = self.hass.states.get(entity)
            if state is not None and interpreter_etat(state.state) is True:
                return True
        return False

    def _personne_pas_au_lit(self) -> bool:
        """Vrai si au moins un capteur signale explicitement personne au lit.

        Un capteur « unknown » (non synchronisé) ne compte pas : on ne sait
        pas s'il y a quelqu'un. Seul un « off » explicite permet d'annuler.
        """
        from .presence import interpreter_etat

        for entity in self._capteurs_lit():
            state = self.hass.states.get(entity)
            if state is not None and interpreter_etat(state.state) is False:
                return True
        return False

    # ── Planification ─────────────────────────────────────────

    def _calculer_prochain(self) -> None:
        cfg = self.entry.data
        mode_jours = cfg.get(CONF_JOURS, "tous")
        jours_perso = cfg.get(CONF_JOURS_PERSO, [])
        mode_heure = cfg.get(CONF_MODE_HEURE, "unique")
        heures_par_jour = self._heures_par_jour() if mode_heure == "par_jour" else None
        jours = _jours_actifs(mode_jours, jours_perso, heures_par_jour)
        now = dt_util.now()

        heure_defaut = _parse_heure(cfg.get(CONF_HEURE, "07:00"))

        # Mode vacances : aucun réveil planifié, ni par booléen ni par entité.
        # Le capteur « Prochain réveil » annonçait sinon une date à laquelle
        # rien ne se déclenchait.
        if cfg.get(CONF_MODE_VACANCES, False) or self._mode_vacances_entite():
            self._prochain = None
            if self._statut not in (STATUT_RINGING, STATUT_SNOOZED, STATUT_PREWAKE):
                self._statut = STATUT_IDLE if self._actif else STATUT_INACTIF
            return

        for i in range(8):
            candidate_date = now + timedelta(days=i)
            jour_semaine = candidate_date.weekday()

            if jour_semaine not in jours:
                continue

            # Heure pour ce jour
            if mode_heure == "par_jour" and heures_par_jour.get(jour_semaine):
                heure = _parse_heure(heures_par_jour[jour_semaine])
            else:
                heure = heure_defaut

            candidate = self._instant_local(candidate_date.date(), heure)

            # Les ajustements s'appliquent sur le datetime, pas sur l'heure
            # seule : un décalage franchissant minuit produisait sinon une
            # heure reportée de près de 24 h sur le même jour.
            if cfg.get(CONF_ADAPTATIF_AGENDA, False) and cfg.get(CONF_AGENDA_ENTITY):
                ajuste = self._instant_adaptatif_agenda(candidate)
                if ajuste is not None:
                    candidate = ajuste

            if candidate <= now:
                continue

            # Occurrence explicitement sautée : on cherche la suivante
            if self._skip_prochain and self._skip_date == candidate.date():
                continue

            self._prochain = candidate
            if self._statut not in (STATUT_RINGING, STATUT_SNOOZED, STATUT_PREWAKE):
                self._statut = STATUT_IDLE if self._actif else STATUT_INACTIF
            return

        # Aucune occurrence trouvée sur huit jours. Le cas le plus courant est
        # le mode « personnalisé » sans jour coché : le réveil est alors
        # silencieusement désactivé et le capteur « Prochain réveil » passe à
        # inconnu, sans que rien n'explique pourquoi.
        if not jours:
            _LOGGER.warning(
                "Réveil '%s' : aucun jour actif (mode « %s »). Le réveil ne "
                "sonnera pas tant qu'aucun jour n'est sélectionné.",
                self.entry.title, mode_jours,
            )
        self._prochain = None
        if self._statut not in (STATUT_RINGING, STATUT_SNOOZED, STATUT_PREWAKE):
            self._statut = STATUT_INACTIF

    def _instant_local(self, jour: date, heure: time) -> datetime:
        """Combine une date et une heure dans le fuseau de Home Assistant.

        On ne peut pas partir de `now().replace(hour=...)` : sur un datetime
        tz-aware, l'offset UTC de « maintenant » est conservé, ce qui décale
        l'instant d'une heure le jour du changement d'heure.

        HA 2025+ expose `dt_util.get_default_time_zone()` ; les versions
        antérieures utilisent `dt_util.DEFAULT_TIME_ZONE`. On teste les deux
        pour éviter un datetime naïf qui casserait les comparaisons avec
        `dt_util.now()` (tz-aware).
        """
        naif = datetime.combine(jour, heure)
        tz = None
        if hasattr(dt_util, "get_default_time_zone"):
            tz = dt_util.get_default_time_zone()
        if tz is None:
            tz = getattr(dt_util, "DEFAULT_TIME_ZONE", None)
        return naif.replace(tzinfo=tz) if tz is not None else naif

    def _mode_vacances_entite(self) -> bool:
        """Vrai si l'entité de mode vacances configurée est active."""
        entite = self.entry.data.get(CONF_MODE_VACANCES_ENTITY)
        if not entite:
            return False
        state = self.hass.states.get(entite)
        return state is not None and state.state == "on"

    def _instant_adaptatif_agenda(self, candidate: datetime) -> datetime | None:
        """Avance le réveil selon le premier rendez-vous du jour visé.

        L'ancienne version parcourait les jours suivants mais sortait de la
        boucle dès la première itération, calculait deux bornes de journée
        qu'elle n'utilisait pas, et appliquait le décalage sans vérifier que le
        rendez-vous concernait bien le jour planifié.
        """
        cfg = self.entry.data
        calendar = cfg.get(CONF_AGENDA_ENTITY)
        marge = cfg.get(CONF_AGENDA_MARGE_MIN, DEFAULT_AGENDA_MARGE_MIN)

        try:
            state = self.hass.states.get(calendar)
            if state is None:
                return None
            start = state.attributes.get("start_time")
            if not start:
                return None

            debut_rdv = datetime.fromisoformat(start)
            if debut_rdv.tzinfo is None:
                tz = getattr(dt_util, "DEFAULT_TIME_ZONE", None)
                if tz is not None:
                    debut_rdv = debut_rdv.replace(tzinfo=tz)

            # Le rendez-vous doit tomber le jour du réveil planifié
            if debut_rdv.date() != candidate.date():
                return None

            reveil = debut_rdv - timedelta(minutes=marge)
            if reveil >= candidate:
                return None  # le RDV est tardif, l'heure normale suffit

            _LOGGER.info(
                "Réveil adaptatif: %s (RDV %s − %d min)",
                reveil.strftime("%H:%M"), start, marge,
            )
            self._log_event("Réveil adaptatif déclenché")
            return reveil
        except Exception as exc:
            _LOGGER.error("Erreur agenda adaptatif: %s", exc)
        return None

    def _planifier_trigger(self) -> None:
        """Programme les déclencheurs pour le pré-réveil et le réveil.

        La planification se cale sur `self._prochain`, qui intègre déjà le mode
        « heure par jour » et l'agenda adaptatif. Un point
        dans le temps est utilisé plutôt qu'un déclencheur horaire quotidien :
        ce dernier sonnait à toutes les heures configurées quel que soit le
        jour, et ignorait les décalages adaptatifs.
        """
        self._nettoyer_triggers()
        self._calculer_prochain()
        if self._prochain is None:
            return

        self._cancel_trigger = async_track_point_in_time(
            self.hass, self._trigger_callback, self._prochain
        )

        prechauffe = self.entry.data.get(CONF_PRECHAUFFE_MIN, DEFAULT_PRECHAUFFE_MIN)
        aube = self.entry.data.get(CONF_AUBE_MIN, DEFAULT_AUBE_MIN)
        pre_delai = max(prechauffe, aube)

        if pre_delai > 0:
            instant_pre = self._prochain - timedelta(minutes=pre_delai)
            if instant_pre > dt_util.now():
                self._cancel_prewake = async_track_point_in_time(
                    self.hass, self._trigger_prewake, instant_pre
                )

        _LOGGER.info(
            "Réveil '%s' programmé pour %s (pré-réveil à H-%dmin)",
            self.entry.title, self._prochain, pre_delai,
        )

    # ── Callbacks triggers ─────────────────────────────────────

    @callback
    def _trigger_prewake(self, now: datetime) -> None:
        """Phase de pré-réveil : chauffage, aube, café."""
        # Déclencheur à usage unique : il est consommé
        self._cancel_prewake = None
        if not self._sonne_aujourd_hui(now):
            return
        if self._capteurs_lit() and not self._personne_au_lit():
            _LOGGER.info("Pré-réveil annulé — personne au lit (Withings)")
            return

        self._statut = STATUT_PREWAKE
        # Le pré-réveil fait partie du cycle arrêtable : stop() et snooze()
        # doivent pouvoir agir pendant l'aube. Sans cela, le bouton Stop
        # laissait tourner radiateur, chauffe-eau et aube pendant jusqu'à
        # 45 min, et le snooze était refusé (garde sur _reveil_en_cours).
        self._reveil_en_cours = True
        self._fire_event("smartwake_prewake", phase="demarrage")
        self._notify()
        # La tâche était créée sans référence : ni stop() ni async_shutdown()
        # ne pouvaient l'annuler, et elle survivait au déchargement.
        self._cancel_cycle = self.hass.async_create_task(self._executer_prewake())

    @callback
    def _abandonner_reveil(self, motif: str) -> None:
        """Sort proprement d'un réveil annulé avant la sonnerie.

        Sans cette remise à zéro, le statut restait bloqué sur « prewake »
        indéfiniment — _calculer_prochain excluant cet état de la
        réinitialisation — et binary_sensor.reveil_en_cours restait « on ».
        """
        _LOGGER.info("Réveil '%s' annulé — %s", self.entry.title, motif)
        self._aube_faite = False
        self._reveil_en_cours = False
        self._etats_initiaux = {}
        self._pending_ringing = False
        self._statut_avant_snooze = None
        self._statut = STATUT_IDLE if self._actif else STATUT_INACTIF
        self._notify()

    @callback
    def _trigger_callback(self, now: datetime) -> None:
        """Phase de réveil principal."""
        # Déclencheur à usage unique : il est consommé
        self._cancel_trigger = None
        # Le pré-réveil met _reveil_en_cours à True pour autoriser snooze/stop
        # pendant l'aube. À H, il faut transitionner vers la sonnerie : on ne
        # sort donc que si la sonnerie est déjà en cours (ringing) ou si on
        # est en snooze (la reprise relancera la sonnerie via _pending_ringing).
        if self._statut == STATUT_RINGING:
            return
        if self._statut == STATUT_SNOOZED:
            # La sonnerie reprendra à la fin du snooze ; on signale qu'il faut
            # alors passer en ringing plutôt que de reprendre l'aube.
            self._pending_ringing = True
            return
        if not self._sonne_aujourd_hui(now):
            self._abandonner_reveil("conditions du jour non remplies")
            return

        # Lever anticipé : si mouvement cuisine détecté récemment
        if self.entry.data.get(CONF_LEVER_ANTICIPE, False):
            cuisine = self.entry.data.get(CONF_MOUVEMENT_CUISINE)
            if cuisine:
                state = self.hass.states.get(cuisine)
                if state and state.state == "on":
                    # Borné au jour courant, sinon le réveil serait désactivé
                    # définitivement après un simple passage en cuisine.
                    self._skip_prochain = True
                    self._skip_date = now.date()
                    self._abandonner_reveil("lever anticipé détecté")
                    return

        # Withings : si personne au lit
        # Un capteur "unknown" (pas encore synchronisé) ne doit pas annuler
        # le reveil : on ne sait pas si la personne est au lit ou non.
        # On n'annule que si au moins un capteur dit explicitement "off"
        # (pas au lit) et aucun ne dit "on" (au lit).
        if self._capteurs_lit():
            au_lit = self._personne_au_lit()
            explicitement_pas_au_lit = self._personne_pas_au_lit()
            if explicitement_pas_au_lit and not au_lit:
                self._abandonner_reveil("personne n'est au lit")
                return

        self._cancel_cycle = self.hass.async_create_task(self._executer_cycle())

    # ── Phase pré-réveil ───────────────────────────────────────

    def _capturer_etats_initiaux(self) -> None:
        """Snapshot l'état des appareils avant de les modifier pendant le cycle.

        Doit être appelé au tout début du pré-réveil (avant d'allumer le
        radiateur, le chauffe-eau ou l'aube) : la lumière est allumée pendant
        l'aube, donc la capturer à H restaurait l'état post-aube au lieu de
        l'état d'origine. Ne fait rien si un snapshot existe déjà (cas où le
        pré-réveil a déjà capturé et où _executer_cycle est atteint normalement
        à H — on ne veut pas écraser la bonne capture).
        """
        if self._etats_initiaux:
            return
        cfg = self.entry.data
        if cfg.get(CONF_MEDIA_PLAYER):
            etat = self.hass.states.get(cfg[CONF_MEDIA_PLAYER])
            if etat:
                self._etats_initiaux[cfg[CONF_MEDIA_PLAYER]] = {
                    "volume": etat.attributes.get("volume_level"),
                    "state": etat.state,
                }
        if cfg.get(CONF_LUMIERE):
            etat = self.hass.states.get(cfg[CONF_LUMIERE])
            if etat:
                self._etats_initiaux[cfg[CONF_LUMIERE]] = {
                    "state": etat.state,
                    "brightness": etat.attributes.get("brightness"),
                }
        if cfg.get(CONF_RADIATEUR):
            etat = self.hass.states.get(cfg[CONF_RADIATEUR])
            if etat:
                self._etats_initiaux[cfg[CONF_RADIATEUR]] = {
                    "preset": etat.attributes.get("preset_mode"),
                    "state": etat.state,
                }

    async def _executer_prewake(self) -> None:
        """Pré-chauffage, simulation d'aube, café, chauffe-eau."""
        cfg = self.entry.data
        _LOGGER.info("Pré-réveil démarré pour '%s'", self.entry.title)

        # Capture l'état d'origine AVANT de modifier quoi que ce soit. La
        # restauration au stop se basait sur l'état à H, donc post-aube : la
        # lumière revenait allumée au lieu d'être éteinte.
        self._capturer_etats_initiaux()

        # Notification actionnable dès le pré-réveil : les boutons Snooze/Stop
        # doivent être disponibles pendant l'aube, pas seulement à H. Sans
        # cela, l'utilisateur ne pouvait pas interrompre l'aube qui dure
        # jusqu'à 60 min.
        if cfg.get(CONF_NOTIFICATION_ACTIVEE):
            try:
                await self._envoyer_notification()
            except Exception as exc:
                _LOGGER.error("Erreur notification pré-réveil: %s", exc)

        # Chauffage
        radiateur = cfg.get(CONF_RADIATEUR)
        if radiateur:
            try:
                await self.hass.services.async_call(
                    "climate", "set_preset_mode",
                    {"entity_id": radiateur, "preset_mode": "comfort"},
                    blocking=True,
                )
                _LOGGER.info("Radiateur confort: %s", radiateur)
            except Exception as exc:
                _LOGGER.error("Erreur radiateur: %s", exc)

        # Chauffe-eau / sèche-serviettes
        chauffe_eau = cfg.get(CONF_CHAUFFE_EAU)
        if chauffe_eau:
            try:
                await self.hass.services.async_call("switch", "turn_on", {"entity_id": chauffe_eau}, blocking=True)
            except Exception as exc:
                _LOGGER.error("Erreur chauffe-eau: %s", exc)

        # Café / bouilloire : programmé en parallèle pour tomber réellement
        # à H - cafetiere_min. Le délai était calculé avec DEFAULT_AUBE_MIN au
        # lieu du délai de pré-réveil effectif (10 - 20 -> négatif, donc 0), et
        # le sleep se trouvait après la rampe de lumière qui bloque ~20 min :
        # le café partait à H-26 au lieu de H-10.
        cafetiere = cfg.get(CONF_CAFETIERE)
        cafetiere_min = cfg.get(CONF_CAFETIERE_MIN, DEFAULT_CAFETIERE_MIN)
        if cafetiere and cafetiere_min > 0:
            prechauffe = cfg.get(CONF_PRECHAUFFE_MIN, DEFAULT_PRECHAUFFE_MIN)
            aube = cfg.get(CONF_AUBE_MIN, DEFAULT_AUBE_MIN)
            attente = max(0, (max(prechauffe, aube) - cafetiere_min) * 60)
            self._cancel_rampes.append(
                self.hass.async_create_task(self._lancer_cafetiere(cafetiere, attente))
            )

        # Simulation d'aube (lumière progressive)
        if cfg.get(CONF_LUMIERE_ACTIVEE) and cfg.get(CONF_LUMIERE):
            self._aube_faite = True
            await self._cycle_lumiere_progressive()

    async def _lancer_cafetiere(self, cafetiere: str, attente: float) -> None:
        """Allume la cafetière après le délai voulu."""
        await asyncio.sleep(attente)
        try:
            await self.hass.services.async_call(
                "switch", "turn_on", {"entity_id": cafetiere}, blocking=True
            )
            _LOGGER.info("Cafetière allumée: %s", cafetiere)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _LOGGER.error("Erreur cafetière: %s", exc)

    # ── Phase réveil ────────────────────────────────────────────

    async def _executer_cycle(self) -> None:
        """Cycle de réveil complet avec contrôle d'erreurs."""
        cfg = self.entry.data
        erreurs = []

        self._reveil_en_cours = True
        self._snooze_count = 0
        self._statut = STATUT_RINGING

        # Sauvegarde l'état initial des appareils pour les restaurer au stop.
        # Délégué à _capturer_etats_initiaux() qui ne fait rien si le pré-réveil
        # a déjà capturé (cas normal). Pour un déclenchement manuel
        # (declencher_manuel) qui court-circuite le pré-réveil, la capture se
        # fait ici à H — comportement inchangé.
        self._capturer_etats_initiaux()
        self._log_event("Réveil déclenché")
        self._fire_event("smartwake_triggered", heure=cfg.get(CONF_HEURE, "07:00"), prochain=self._prochain.isoformat() if self._prochain else None)
        self._increment_stat("total_declenchements")
        self._notify()

        # 1. Notification actionnable EN PREMIER.
        # Elle était envoyée après la musique et la rampe de lumière, qui
        # bloquent respectivement ~5 et ~19 min : les boutons Snooze/Stop
        # n'arrivaient sur le téléphone qu'environ 25 min après la sonnerie.
        if cfg.get(CONF_NOTIFICATION_ACTIVEE):
            try:
                await self._envoyer_notification()
            except Exception as exc:
                erreurs.append("notification")
                _LOGGER.error("Erreur notification: %s", exc)

        # Notification persistante : visible sur tous les dashboards, pas
        # seulement sur le téléphone. Elle reste affichée jusqu'à ce qu'on
        # la ferme, contrairement à la notification Android qui disparaît.
        try:
            await self.hass.services.async_call(
                "persistent_notification", "create",
                {
                    "title": "⏰ " + self.entry.title,
                    "message": "Le réveil sonne ! Cliquez Stop ou Snooze depuis l'application mobile.",
                    "notification_id": f"smartwake_{self.entry.entry_id}",
                },
                blocking=True,
            )
        except Exception as exc:
            _LOGGER.error("Erreur notification persistante: %s", exc)

        # 2. Arrêt par mouvement, armé avant les rampes pour la même raison
        if cfg.get(CONF_MOUVEMENT_STOP, False) and cfg.get(CONF_MOUVEMENT_SDB):
            self._setup_mouvement_stop()

        # 3. Escalade — une seule fois. Elle était programmée deux fois, la
        # première tâche devenant orpheline et donc non annulable par stop().
        if cfg.get(CONF_ESCALADE_INTELLIGENTE, False):
            self._cancel_escalade = self.hass.async_create_task(
                self._escalade_intelligente()
            )
        else:
            self._cancel_escalade = self.hass.async_create_task(
                self._escalade(cfg.get(CONF_ESCALADE_MIN, DEFAULT_ESCALADE_MIN))
            )

        # 4. Rampes longues en parallèle plutôt qu'en séquence
        self._cancel_rampes = []

        async def _rampe(nom: str, coro) -> None:
            try:
                await coro
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                erreurs.append(nom)
                _LOGGER.error("Erreur critique %s: %s", nom, exc)
                if nom == "musique":
                    await self._alerter_sonnerie_echouee(nom)

        if cfg.get(CONF_MUSIQUE_ACTIVEE) and cfg.get(CONF_MEDIA_PLAYER):
            self._cancel_rampes.append(
                self.hass.async_create_task(_rampe("musique", self._demarrer_musique()))
            )
        if cfg.get(CONF_VOLETS):
            self._cancel_rampes.append(
                self.hass.async_create_task(_rampe("volets", self._ouvrir_volets()))
            )
        # La rampe de lumière n'est relancée que si l'aube ne l'a pas déjà fait.
        # Le test précédent portait sur le statut, forcé à « ringing » juste
        # au-dessus : il était donc toujours vrai et deux rampes concurrentes
        # pilotaient la même lampe.
        if cfg.get(CONF_LUMIERE_ACTIVEE) and cfg.get(CONF_LUMIERE) and not self._aube_faite:
            self._cancel_rampes.append(
                self.hass.async_create_task(
                    _rampe("lumière", self._cycle_lumiere_progressive())
                )
            )

        # 5. Scène matin et tâches IA
        # L'activation était conditionnée à un booléen sans champ dans le
        # formulaire : les scènes choisies ne se déclenchaient donc jamais. Une
        # liste renseignée suffit désormais.
        if cfg.get(CONF_SCENE_MATIN_ENTITIES) or cfg.get(CONF_SCENES_MATIN, False):
            try:
                await self._activer_scene_matin()
            except Exception as exc:
                _LOGGER.error("Erreur scène matin: %s", exc)

        if cfg.get(CONF_AI_CUSTOM_ENABLED) or cfg.get(CONF_AI_CUSTOM_TASKS):
            self.hass.async_create_task(self._run_custom_ai("on_wake"))

    async def _alerter_sonnerie_echouee(self, quoi: str) -> None:
        """Prévient l'utilisateur quand le réveil sonore a échoué.

        La condition précédente (`erreurs and not CONF_MUSIQUE_ACTIVEE`) ne
        pouvait jamais être vraie : « musique » n'entre dans les erreurs que
        si la musique est activée.
        """
        self._log_event(f"Sonnerie échouée: {quoi}")
        await self._notifier(
            self.entry.data.get(CONF_NOTIFY_DEVICE),
            "⚠️ SmartWAKE",
            f"Le réveil sonore a échoué ({quoi}) — vérifiez la configuration",
        )

    @staticmethod
    def _media_id(valeur: Any) -> str:
        """Identifiant média, que le sélecteur renvoie un dict ou une chaîne.

        Le MediaSelector de Home Assistant renvoie « media_content_id », non
        « content_id » : chercher la mauvaise clé faisait passer une playlist
        pourtant configurée pour vide.
        """
        if isinstance(valeur, dict):
            return str(
                valeur.get("media_content_id") or valeur.get("content_id") or ""
            ).strip()
        return str(valeur or "").strip()

    def _volume_actuel(self, media: str) -> float:
        """Volume actuel d'un lecteur, pour reprendre la montée au bon niveau."""
        etat = self.hass.states.get(media)
        if etat is not None:
            try:
                return float(etat.attributes.get("volume_level", 0))
            except (TypeError, ValueError):
                pass
        return 0.0

    async def _demarrer_musique(self) -> None:
        """Démarre la musique avec volume progressif. Retry + fallback TTS si échec."""
        cfg = self.entry.data
        media = cfg[CONF_MEDIA_PLAYER]
        playlist_raw = cfg.get(CONF_PLAYLIST, "")
        vol_initial = cfg.get(CONF_VOLUME_INITIAL, DEFAULT_VOLUME_INITIAL)
        vol_final = cfg.get(CONF_VOLUME_FINAL, DEFAULT_VOLUME_FINAL)
        duree = cfg.get(CONF_VOLUME_DUREE, DEFAULT_VOLUME_DUREE)

        # MediaSelector retourne un dict {content_id, content_type} ou un string
        content_id = self._media_id(playlist_raw)
        content_type = "music"
        if isinstance(playlist_raw, dict):
            content_type = (
                playlist_raw.get("media_content_type")
                or playlist_raw.get("content_type")
                or "music"
            )

        # Musique adaptative IA : choisir parmi les playlists réellement
        # configurées. Les options étaient auparavant des noms inventés, que le
        # lecteur ne sait pas jouer : le choix de l'IA cassait la lecture.
        if cfg.get(CONF_AI_MUSIQUE_ADAPT):
            from .ai import choose_adaptive_music

            options = [content_id] + [
                self._media_id(cfg.get(cle))
                for cle in (CONF_PLAYLIST_DOUCE, CONF_PLAYLIST_ENERGIQUE)
            ]
            options = [o for o in dict.fromkeys(options) if o]
            if len(options) > 1:
                chosen = await choose_adaptive_music(self.hass, cfg, options)
                if chosen in options:
                    content_id = chosen
                    self._log_event("Musique adaptative IA")
                elif chosen:
                    _LOGGER.warning(
                        "Choix IA « %s » écarté : absent des playlists configurées",
                        chosen,
                    )
            else:
                _LOGGER.debug(
                    "Musique adaptative sans effet : une seule playlist configurée"
                )

        # Une lecture sans identifiant échoue côté lecteur — sur Sonos par un
        # IndexError peu parlant, async_process_play_media_url indexant la
        # chaîne vide. Autant le dire clairement et passer au repli vocal.
        if not content_id:
            _LOGGER.error(
                "Réveil '%s' : aucune playlist configurée. Renseignez « Playlist » "
                "dans Options → Musique, ou désactivez la musique.",
                self.entry.title,
            )
            self._log_event("Aucune playlist configurée — repli vocal")
            await self._tts_speak("Il est l'heure de se lever !")
            await self._alerter_sonnerie_echouee("aucune playlist configurée")
            return

        musique_ok = False
        for attempt in range(3):
            try:
                await self.hass.services.async_call(
                    "media_player", "volume_set",
                    {"entity_id": media, "volume_level": vol_initial},
                    blocking=True,
                )
                await self.hass.services.async_call(
                    "media_player", "play_media",
                    {"entity_id": media, "media_content_id": content_id, "media_content_type": content_type},
                    blocking=True,
                )
                musique_ok = True
                _LOGGER.info("Musique lancée sur %s (tentative %d)", media, attempt + 1)
                break
            except Exception as exc:
                _LOGGER.warning("Tentative musique %d/3 échouée: %s", attempt + 1, exc)
                if attempt < 2:
                    await asyncio.sleep(5)

        if not musique_ok:
            _LOGGER.error("Musique échouée après 3 tentatives — fallback TTS")
            self._log_event("Musique échouée — fallback")
            # Fallback : TTS d'alarme si configuré
            await self._tts_speak("Il est l'heure de se lever !")
            await self._alerter_sonnerie_echouee("musique")
            return

        # Montée progressive du volume
        steps = max(int(duree), 1)
        increment = (vol_final - vol_initial) / steps
        for i in range(steps):
            await asyncio.sleep(60)
            vol = min(vol_initial + increment * (i + 1), vol_final)
            try:
                await self.hass.services.async_call(
                    "media_player", "volume_set",
                    {"entity_id": media, "volume_level": vol},
                    blocking=True,
                )
            except Exception as exc:
                _LOGGER.error("Erreur volume musique: %s", exc)

    async def _ouvrir_volets(self) -> None:
        """Ouvre les volets si le soleil est levé."""
        cfg = self.entry.data
        volets = cfg[CONF_VOLETS]
        soleil_seulement = cfg.get(CONF_VOLETS_SOLEIL, True)

        if soleil_seulement:
            sun = self.hass.states.get("sun.sun")
            if sun and sun.state != "above_horizon":
                _LOGGER.info("Volets fermés — soleil pas encore levé")
                # Fallback : programmer l'ouverture au lever du soleil
                self.hass.async_create_task(self._ouvrir_volets_au_lever(volets))
                return

        for attempt in range(2):
            try:
                position = cfg.get(CONF_VOLETS_POSITION, 100)
                if position >= 100:
                    await self.hass.services.async_call("cover", "open_cover", {"entity_id": volets}, blocking=True)
                else:
                    await self.hass.services.async_call("cover", "set_cover_position", {"entity_id": volets, "position": position}, blocking=True)
                _LOGGER.info("Volets ouverts (%d%%): %s", position, volets)
                return
            except Exception as exc:
                _LOGGER.warning("Tentative volets %d/2 échouée: %s", attempt + 1, exc)
                if attempt < 1:
                    await asyncio.sleep(3)
        _LOGGER.error("Ouverture volets échouée après 2 tentatives")

    async def _ouvrir_volets_au_lever(self, volets: str) -> None:
        """Ouvre les volets au lever du soleil (repli).

        Utilisait async_track_state_change, retirée de Home Assistant : l'import
        levait ImportError dans la tâche, si bien que les volets ne s'ouvraient
        jamais les jours où le soleil était encore sous l'horizon.
        """
        termine = asyncio.Event()

        @callback
        def _try_open(event) -> None:
            if termine.is_set():
                return
            nouveau = event.data.get("new_state")
            if nouveau is not None and nouveau.state == "above_horizon":
                termine.set()
                self.hass.async_create_task(self._open_volets_now(volets))

        unsub = async_track_state_change_event(self.hass, ["sun.sun"], _try_open)
        try:
            # Attente du lever, plafonnée à 2 h — libère dès l'ouverture au lieu
            # de dormir systématiquement jusqu'au bout.
            await asyncio.wait_for(termine.wait(), timeout=2 * 3600)
        except asyncio.TimeoutError:
            _LOGGER.warning("Lever du soleil non détecté en 2 h — volets non ouverts")
        except asyncio.CancelledError:
            raise
        finally:
            unsub()

    async def _open_volets_now(self, volets: str) -> None:
        try:
            await self.hass.services.async_call("cover", "open_cover", {"entity_id": volets}, blocking=True)
            _LOGGER.info("Volets ouverts au lever du soleil: %s", volets)
        except Exception as exc:
            _LOGGER.error("Erreur ouverture volets au lever: %s", exc)

    async def _activer_scene_matin(self) -> None:
        """Active la scène matin : éclairage cuisine + couloir + autres pièces."""
        cfg = self.entry.data
        entities = cfg.get(CONF_SCENE_MATIN_ENTITIES, [])
        if not entities:
            return
        for entity in entities:
            try:
                domain = entity.split(".")[0]
                if domain == "light":
                    await self.hass.services.async_call(
                        "light", "turn_on",
                        {"entity_id": entity, "brightness_pct": 80, "transition": 30},
                        blocking=True,
                    )
                elif domain == "switch":
                    await self.hass.services.async_call("switch", "turn_on", {"entity_id": entity}, blocking=True)
                elif domain == "scene":
                    await self.hass.services.async_call("scene", "turn_on", {"entity_id": entity}, blocking=True)
                _LOGGER.info("Scène matin: %s activé", entity)
            except Exception as exc:
                _LOGGER.error("Erreur scène matin %s: %s", entity, exc)

    async def _escalade_intelligente(self) -> None:
        """Escalade progressive : 3 niveaux (doux → moyen → max)."""
        # Niveau 1 (5 min) : volume 60%
        await asyncio.sleep(5 * 60)
        if not self._escalade_pertinente():
            return
        await self._escalade_niveau(0.6, 60, "doux")
        # Niveau 2 (10 min) : volume 80%
        await asyncio.sleep(5 * 60)
        if not self._escalade_pertinente():
            return
        await self._escalade_niveau(0.8, 80, "moyen")
        # Niveau 3 (15 min) : volume 100% + toutes lumières
        await asyncio.sleep(5 * 60)
        if not self._escalade_pertinente():
            return
        await self._escalade_niveau(1.0, 100, "max")
        self._log_event("Escalade intelligente : niveau max")
        self._fire_event("smartwake_escalade", level="max")

    async def _escalade_niveau(self, volume: float, brightness_pct: int, niveau: str) -> None:
        """Applique un niveau d'escalade."""
        cfg = self.entry.data
        _LOGGER.info("Escalade niveau %s pour '%s'", niveau, self.entry.title)
        self._fire_event("smartwake_escalade", level=niveau)
        if cfg.get(CONF_MUSIQUE_ACTIVEE) and cfg.get(CONF_MEDIA_PLAYER):
            try:
                await self.hass.services.async_call(
                    "media_player", "volume_set",
                    {"entity_id": cfg[CONF_MEDIA_PLAYER], "volume_level": volume},
                    blocking=True,
                )
            except Exception as exc:
                _LOGGER.error("Erreur escalade volume: %s", exc)
        if cfg.get(CONF_LUMIERE_ACTIVEE) and cfg.get(CONF_LUMIERE):
            try:
                await self.hass.services.async_call(
                    "light", "turn_on",
                    {"entity_id": cfg[CONF_LUMIERE], "brightness_pct": brightness_pct},
                    blocking=True,
                )
            except Exception as exc:
                _LOGGER.error("Erreur escalade lumière: %s", exc)

    @staticmethod
    def _couleur_lumiere(cfg: dict) -> dict[str, Any]:
        """Paramètres de couleur pour light.turn_on.

        Home Assistant refuse une couleur RVB et une température de couleur dans
        le même appel : la couleur explicite prime.
        """
        rgb = cfg.get(CONF_LUMIERE_COULEUR)
        if rgb:
            try:
                valeurs = [int(v) for v in rgb][:3]
                if len(valeurs) == 3:
                    return {"rgb_color": valeurs}
            except (TypeError, ValueError):
                _LOGGER.debug("Couleur de réveil illisible: %r", rgb)
        kelvin = cfg.get(CONF_LUMIERE_TEMP_COULEUR)
        if kelvin:
            try:
                return {"color_temp_kelvin": int(kelvin)}
            except (TypeError, ValueError):
                _LOGGER.debug("Température de couleur illisible: %r", kelvin)
        return {}

    async def _cycle_lumiere_progressive(self) -> None:
        """Augmentation progressive de la luminosité jusqu'à la valeur réglée.

        La rampe envoyait auparavant 20 fois `brightness_step_pct: 1`, soit 20 %
        au total quel que soit le réglage, et comparait la luminosité lue
        (échelle 0-255) à `brightness_max` (même échelle) alors que les
        incréments étaient en pourcentage. Le réglage « Luminosité max » n'avait
        donc quasiment aucun effet. On vise désormais des valeurs absolues.
        """
        cfg = self.entry.data
        lumiere = cfg[CONF_LUMIERE]
        brightness_max = max(1, min(255, int(cfg.get(CONF_BRIGHTNESS_MAX, DEFAULT_BRIGHTNESS_MAX))))
        duree = max(1, int(cfg.get(CONF_DUREE_PROGRESSIVE, DEFAULT_DUREE_PROGRESSIVE)))
        couleur = self._couleur_lumiere(cfg)
        douce = cfg.get(CONF_LUMIERE_COURBE, COURBE_DOUCE) == COURBE_DOUCE

        # Un pas toutes les 30 s environ, borné pour rester raisonnable
        steps = max(1, min(brightness_max, duree * 2))
        intervalle = (duree * 60) / steps

        # Reprise après un snooze : on repart du niveau atteint plutôt que de
        # recommencer la montée depuis le début.
        depart = 1
        if self._aube_niveau > 0:
            # Le point de reprise doit être l'inverse de la courbe employée,
            # sans quoi une montée douce repartirait trop bas.
            part = min(1.0, self._aube_niveau / brightness_max)
            if douce:
                part = math.sqrt(part)
            depart = min(steps, max(1, round(steps * part)))

        try:
            for i in range(depart, steps + 1):
                # Une montée quadratique paraît plus naturelle qu'une montée
                # linéaire, l'œil percevant mal les écarts dans les niveaux bas.
                fraction = (i / steps) ** 2 if douce else i / steps
                cible = max(1, round(brightness_max * fraction))
                self._aube_niveau = cible
                charge: dict[str, Any] = {"entity_id": lumiere, "brightness": cible}
                charge.update(couleur)
                await self.hass.services.async_call(
                    "light", "turn_on", charge, blocking=True
                )
                if i < steps:
                    await asyncio.sleep(intervalle)

            # Scène de fin : permet une ambiance riche sur plusieurs lampes,
            # que la montée d'une seule luminosité ne sait pas rendre.
            scene = cfg.get(CONF_LUMIERE_SCENE)
            if scene:
                try:
                    await self.hass.services.async_call(
                        "scene", "turn_on", {"entity_id": scene}, blocking=True
                    )
                    _LOGGER.info("Scène de réveil appliquée: %s", scene)
                except Exception as exc:
                    _LOGGER.error("Erreur scène de réveil: %s", exc)
            _LOGGER.info(
                "Lumière progressive terminée pour '%s' (%d/255 en %d min)",
                self.entry.title, brightness_max, duree,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _LOGGER.error("Erreur lumière: %s", exc)

    def _service_notify(self, cible: str) -> str | None:
        """Service notify historique correspondant à une cible de notification.

        Seul ce service accepte une clé `data`, donc des boutons d'action. Or
        une entité `notify.<objet>` est fournie par une plateforme dont le
        service s'appelle `<plateforme>_<objet>` : pour l'application mobile,
        l'entité `notify.sm_g991u1` correspond au service
        `notify.mobile_app_sm_g991u1`. Chercher `notify.sm_g991u1` échouait donc,
        et les notifications partaient sans boutons.
        """
        if not cible:
            return None
        objet = cible.split(".", 1)[1] if "." in cible else cible

        candidats: list[str] = []
        try:
            from homeassistant.helpers import entity_registry as er

            entree = er.async_get(self.hass).async_get(cible)
            if entree is not None and entree.platform:
                candidats.append(f"{entree.platform}_{objet}")
        except Exception as exc:  # noqa: BLE001 - le registre est indicatif
            _LOGGER.debug("Registre d'entités indisponible: %s", exc)

        candidats += [f"mobile_app_{objet}", objet]
        for nom in dict.fromkeys(candidats):
            if self.hass.services.has_service("notify", nom):
                return nom
        return None

    async def _notifier(
        self,
        cible: str | None,
        titre: str,
        message: str,
        actions: list[dict[str, str]] | None = None,
    ) -> bool:
        """Envoie une notification, avec boutons d'action si demandé.

        L'entity service `notify.send_message` n'accepte que `message` et
        `title` : passer une clé `data` — donc des boutons d'action — fait
        échouer la validation. Seul le service historique
        `notify.<nom_du_service>` accepte `data`. On l'utilise donc dès que des
        actions sont nécessaires, avec repli sur l'entity service sinon.
        """
        if not cible:
            return False

        # Le message doit être une string, pas un dict
        if not isinstance(message, str):
            message = str(message) if message else ""

        service = self._service_notify(cible)
        charge: dict[str, Any] = {"title": titre, "message": message}
        if actions:
            charge["data"] = {"actions": actions}

        # Service historique : seul chemin qui accepte les actions
        if service:
            try:
                await self.hass.services.async_call(
                    "notify", service, charge, blocking=True
                )
                return True
            except Exception as exc:
                _LOGGER.error("Erreur notification (%s): %s", service, exc)
                return False

        # Repli : entity service, sans les boutons d'action
        if actions:
            _LOGGER.warning(
                "Aucun service notify historique pour « %s » — notification "
                "envoyée sans boutons Snooze/Stop", cible,
            )
        entite = cible if cible.startswith("notify.") else f"notify.{cible}"
        try:
            await self.hass.services.async_call(
                "notify", "send_message",
                {"entity_id": entite, "title": titre, "message": message},
                blocking=True,
            )
            return True
        except Exception as exc:
            _LOGGER.error("Erreur notification (%s): %s", entite, exc)
            return False

    async def _envoyer_notification(self) -> None:
        """Notification actionnable avec boutons Snooze / Stop."""
        cfg = self.entry.data
        notify_device = cfg.get(CONF_NOTIFY_DEVICE)
        if not notify_device:
            _LOGGER.warning(
                "Aucun destinataire de notification configuré. "
                "Renseignez « Destinataire » dans Options → Notification."
            )
            return
        envoye = await self._notifier(
            notify_device,
            str(cfg.get(CONF_NOTIF_TITRE, DEFAULT_NOTIF_TITRE)),
            str(cfg.get(CONF_NOTIF_MESSAGE, DEFAULT_NOTIF_MESSAGE)),
            actions=[
                {"action": f"REVEIL_SNOOZE_{self.entry.entry_id}", "title": "Snooze"},
                {"action": f"REVEIL_STOP_{self.entry.entry_id}", "title": "Stop"},
            ],
        )
        if envoye:
            _LOGGER.info("Notification envoyée pour '%s'", self.entry.title)

    def _escalade_pertinente(self) -> bool:
        """L'escalade ne doit s'appliquer que pendant une sonnerie effective.

        Elle ne testait que _reveil_en_cours, vrai aussi pendant un snooze :
        avec les valeurs par défaut (snooze 5 min, escalade 5 min), les lumières
        passaient à 100 % et le volume au maximum en pleine période de snooze.
        """
        return self._reveil_en_cours and self._statut == STATUT_RINGING

    async def _escalade(self, delai_min: int) -> None:
        """Escalade : volume max + toutes lumières si pas de stop."""
        await asyncio.sleep(delai_min * 60)
        if not self._escalade_pertinente():
            return

        cfg = self.entry.data
        _LOGGER.info("Escalade déclenchée pour '%s'", self.entry.title)
        self._log_event("Escalade : volume max + lumières 100%")
        self._fire_event("smartwake_escalade", level="max")

        # Volume max
        if cfg.get(CONF_MUSIQUE_ACTIVEE) and cfg.get(CONF_MEDIA_PLAYER):
            try:
                await self.hass.services.async_call(
                    "media_player", "volume_set",
                    {"entity_id": cfg[CONF_MEDIA_PLAYER], "volume_level": 1.0},
                    blocking=True,
                )
            except Exception as exc:
                _LOGGER.error("Erreur escalade volume: %s", exc)

        # Toutes lumières à 100%
        if cfg.get(CONF_LUMIERE_ACTIVEE) and cfg.get(CONF_LUMIERE):
            try:
                await self.hass.services.async_call(
                    "light", "turn_on",
                    {"entity_id": cfg[CONF_LUMIERE], "brightness_pct": 100},
                    blocking=True,
                )
            except Exception as exc:
                _LOGGER.error("Erreur escalade lumière: %s", exc)

    def _setup_mouvement_stop(self) -> None:
        """Configure l'arrêt par détection de mouvement salle de bain.

        Écoutait auparavant un event_type « state_changed.<entité> » qui
        n'existe pas sur le bus Home Assistant : le callback n'était jamais
        appelé et la fonction était donc morte. Le désabonnement n'était par
        ailleurs pas conservé, alors que la méthode est rappelée à chaque
        cycle — les écouteurs s'accumulaient.
        """
        sdb = self.entry.data.get(CONF_MOUVEMENT_SDB)
        if not sdb:
            return

        # Évite d'empiler un écouteur par cycle
        if self._cancel_mouvement is not None:
            self._cancel_mouvement()
            self._cancel_mouvement = None

        @callback
        def _on_mouvement(event) -> None:
            if not self._reveil_en_cours:
                return
            nouveau = event.data.get("new_state")
            ancien = event.data.get("old_state")
            if nouveau is None or nouveau.state != "on":
                return
            if ancien is not None and ancien.state == "on":
                return  # déjà détecté, pas une nouvelle transition
            _LOGGER.info("Mouvement SdB détecté — arrêt du réveil")
            self.hass.async_create_task(self.stop(raison="mouvement_sdb"))

        self._cancel_mouvement = async_track_state_change_event(
            self.hass, [sdb], _on_mouvement
        )

    # ── Snooze / Stop / Skip ────────────────────────────────────

    async def snooze(self) -> None:
        """Met la sonnerie en pause pour la durée configurée.

        L'attente se fait dans une tâche de fond : le service smartwake.snooze
        bloquait sinon l'appelant pendant toute la durée du snooze (5 min par
        défaut), ce qui figeait l'automatisation ou le script appelant.
        """
        if not self._reveil_en_cours:
            return
        # Sans ce garde, deux appuis rapprochés (notification + bouton)
        # lançaient deux minuteries concurrentes qui relançaient la musique
        # chacune de leur côté.
        if self._statut == STATUT_SNOOZED:
            _LOGGER.debug("Snooze déjà en cours pour '%s'", self.entry.title)
            return

        max_snooze = self.entry.data.get(CONF_SNOOZE_MAX, DEFAULT_SNOOZE_MAX)
        if self._snooze_count >= max_snooze:
            _LOGGER.info("Snooze max atteint pour '%s'", self.entry.title)
            return

        self._snooze_count += 1
        # Mémorise la phase d'origine pour la reprise : un snooze déclenché
        # pendant l'aube (prewake) doit reprendre l'aube, pas la sonnerie.
        self._statut_avant_snooze = self._statut
        self._statut = STATUT_SNOOZED
        self._snooze_fin = dt_util.now() + timedelta(
            minutes=self.entry.data.get(CONF_SNOOZE_DUREE, DEFAULT_SNOOZE_DUREE)
        )
        self._log_event(f"Snooze ({self._snooze_count}/{max_snooze})")
        self._fire_event("smartwake_snoozed", count=self._snooze_count, max=max_snooze)
        self._increment_stat("total_snoozes")
        self._notify()

        cfg = self.entry.data

        if cfg.get(CONF_MUSIQUE_ACTIVEE) and cfg.get(CONF_MEDIA_PLAYER):
            try:
                await self.hass.services.async_call(
                    "media_player", "media_pause",
                    {"entity_id": cfg[CONF_MEDIA_PLAYER]},
                    blocking=True,
                )
            except Exception as exc:
                _LOGGER.error("Erreur pause snooze: %s", exc)

        # Les rampes doivent être suspendues, sans quoi la montée de lumière
        # continuait pendant le snooze : la lampe se rallumait au pas suivant,
        # une trentaine de secondes après avoir été éteinte, et poursuivait sa
        # progression jusqu'à la reprise.
        for tache in self._cancel_rampes:
            if tache and not tache.done():
                tache.cancel()
        self._cancel_rampes = []

        if cfg.get(CONF_LUMIERE_ACTIVEE) and cfg.get(CONF_LUMIERE):
            try:
                await self.hass.services.async_call(
                    "light", "turn_off", {"entity_id": cfg[CONF_LUMIERE]},
                    blocking=True,
                )
            except Exception as exc:
                _LOGGER.error("Erreur extinction snooze: %s", exc)

        self._cancel_snooze = self.hass.async_create_task(self._reprendre_apres_snooze())

    async def _reprendre_apres_snooze(self) -> None:
        """Relance l'aube ou la sonnerie à l'issue du snooze.

        Un snooze déclenché pendant l'aube (prewake) reprend l'aube ; un snooze
        pendant la sonnerie reprend la sonnerie. Si l'heure H est tombée
        pendant le snooze, _pending_ringing force la reprise en sonnerie.
        """
        cfg = self.entry.data
        duree = cfg.get(CONF_SNOOZE_DUREE, DEFAULT_SNOOZE_DUREE)
        try:
            await asyncio.sleep(int(duree) * 60)
        except asyncio.CancelledError:
            _LOGGER.warning(
                "Reprise de snooze annulée pour '%s' (statut=%s, en_cours=%s)",
                self.entry.title, self._statut, self._reveil_en_cours,
            )
            raise

        # Un stop ou un nouveau cycle peut être survenu entre-temps
        if not self._reveil_en_cours or self._statut != STATUT_SNOOZED:
            _LOGGER.warning(
                "Reprise de snooze: conditions non remplies pour '%s' "
                "(en_cours=%s, statut=%s)",
                self.entry.title, self._reveil_en_cours, self._statut,
            )
            return

        # Détermine la phase de reprise : sonnerie si on était en ringing,
        # si H est tombée pendant le snooze (_pending_ringing), sinon aube.
        vers_ringing = (
            self._pending_ringing
            or self._statut_avant_snooze == STATUT_RINGING
        )
        self._pending_ringing = False
        self._statut_avant_snooze = None
        self._snooze_fin = None

        if not vers_ringing:
            # Reprise de l'aube : on remet le statut en prewake et on relance
            # la rampe de lumière au niveau atteint avant le snooze.
            self._statut = STATUT_PREWAKE
            self._notify()
            if cfg.get(CONF_LUMIERE_ACTIVEE) and cfg.get(CONF_LUMIERE):
                self._cancel_rampes.append(
                    self.hass.async_create_task(self._cycle_lumiere_progressive())
                )
            return

        self._statut = STATUT_RINGING
        self._notify()

        # Renvoie la notification actionnable après la reprise du snooze,
        # pour que l'utilisateur puisse re-snoozer ou re-stopper.
        if cfg.get(CONF_NOTIFICATION_ACTIVEE):
            try:
                await self._envoyer_notification()
            except Exception as exc:
                _LOGGER.error("Erreur notification reprise: %s", exc)

        if cfg.get(CONF_MUSIQUE_ACTIVEE) and cfg.get(CONF_MEDIA_PLAYER):
            # Relance la lecture, puis reprend la montée de volume là où elle
            # s'était interrompue. La rampe originale a été annulée au snooze :
            # sans cette relance, la musique reprenait mais restait bloquée au
            # volume du dernier pas atteint avant le snooze.
            async def _reprise_musique():
                try:
                    await self.hass.services.async_call(
                        "media_player", "media_play",
                        {"entity_id": cfg[CONF_MEDIA_PLAYER]},
                        blocking=True,
                    )
                except Exception as exc:
                    _LOGGER.error("Erreur reprise musique: %s", exc)
                    return
                # Montée de volume depuis le niveau actuel
                vol_initial = self._volume_actuel(cfg[CONF_MEDIA_PLAYER])
                vol_final = cfg.get(CONF_VOLUME_FINAL, DEFAULT_VOLUME_FINAL)
                duree = cfg.get(CONF_VOLUME_DUREE, DEFAULT_VOLUME_DUREE)
                steps = max(int(duree), 1)
                increment = (vol_final - vol_initial) / steps
                for i in range(steps):
                    await asyncio.sleep(60)
                    if not self._reveil_en_cours or self._statut != STATUT_RINGING:
                        return
                    vol = min(vol_initial + increment * (i + 1), vol_final)
                    try:
                        await self.hass.services.async_call(
                            "media_player", "volume_set",
                            {"entity_id": cfg[CONF_MEDIA_PLAYER], "volume_level": vol},
                            blocking=True,
                        )
                    except Exception as exc:
                        _LOGGER.error("Erreur volume reprise: %s", exc)
                        return

            self._cancel_rampes.append(
                self.hass.async_create_task(_reprise_musique())
            )

        # La rampe de lumière reprend au niveau où elle avait été suspendue
        if cfg.get(CONF_LUMIERE_ACTIVEE) and cfg.get(CONF_LUMIERE):
            self._cancel_rampes.append(
                self.hass.async_create_task(self._cycle_lumiere_progressive())
            )

    async def stop(self, raison: str = "manual") -> None:
        """Arrête le cycle de réveil, pré-réveil compris.

        Le garde ne testait que _reveil_en_cours, vrai à partir de la sonnerie
        seulement : pendant toute la phase de pré-réveil (jusqu'à 45 min), le
        bouton Stop et le service smartwake.stop ne faisaient rien, laissant
        tourner radiateur, chauffe-eau, aube et cafetière.
        """
        if not self._reveil_en_cours and self._statut != STATUT_PREWAKE:
            return

        for task in (self._cancel_cycle, self._cancel_escalade,
                     self._cancel_snooze, *self._cancel_rampes):
            if task and not task.done():
                task.cancel()
        self._cancel_cycle = None
        self._cancel_escalade = None
        self._cancel_snooze = None
        # Les rampes (musique, lumière, volets) tournent en parallèle : sans
        # cette annulation, la montée de volume continuait après le stop.
        self._cancel_rampes = []
        if self._cancel_mouvement is not None:
            self._cancel_mouvement()
            self._cancel_mouvement = None

        cfg = self.entry.data
        # Restaure l'état initial des appareils modifiés pendant le réveil.
        # Le volume du Sonos reste à 30% après le stop ; on le remet à sa
        # valeur d'origine. La lumière est éteinte, sauf si elle était allumée
        # avant le réveil. Le radiateur revient à son preset d'origine.
        if hasattr(self, "_etats_initiaux") and self._etats_initiaux:
            for entity_id, etat in self._etats_initiaux.items():
                domaine = entity_id.split(".")[0]
                try:
                    if domaine == "media_player":
                        await self.hass.services.async_call(
                            "media_player", "media_stop",
                            {"entity_id": entity_id}, blocking=True,
                        )
                        if etat.get("volume") is not None:
                            await self.hass.services.async_call(
                                "media_player", "volume_set",
                                {"entity_id": entity_id,
                                 "volume_level": etat["volume"]},
                                blocking=True,
                            )
                    elif domaine == "light":
                        if etat.get("state") == "on":
                            charge = {"entity_id": entity_id}
                            if etat.get("brightness") is not None:
                                charge["brightness"] = etat["brightness"]
                            await self.hass.services.async_call(
                                "light", "turn_on", charge, blocking=True,
                            )
                        else:
                            await self.hass.services.async_call(
                                "light", "turn_off",
                                {"entity_id": entity_id}, blocking=True,
                            )
                    elif domaine == "climate":
                        if etat.get("preset") is not None:
                            await self.hass.services.async_call(
                                "climate", "set_preset_mode",
                                {"entity_id": entity_id,
                                 "preset_mode": etat["preset"]},
                                blocking=True,
                            )
                except Exception as exc:
                    _LOGGER.error("Erreur restauration %s: %s", entity_id, exc)
        else:
            # Pas d'état initial sauvegardé : comportement par défaut
            if cfg.get(CONF_MUSIQUE_ACTIVEE) and cfg.get(CONF_MEDIA_PLAYER):
                try:
                    await self.hass.services.async_call(
                        "media_player", "media_stop",
                        {"entity_id": cfg[CONF_MEDIA_PLAYER]},
                        blocking=True,
                    )
                except Exception as exc:
                    _LOGGER.error("Erreur stop musique: %s", exc)
            if cfg.get(CONF_LUMIERE_ACTIVEE) and cfg.get(CONF_LUMIERE):
                try:
                    await self.hass.services.async_call(
                        "light", "turn_off",
                        {"entity_id": cfg[CONF_LUMIERE]}, blocking=True,
                    )
                except Exception as exc:
                    _LOGGER.error("Erreur extinction: %s", exc)

        # Ferme la notification persistante : le réveil est arrêté.
        try:
            await self.hass.services.async_call(
                "persistent_notification", "dismiss",
                {"notification_id": f"smartwake_{self.entry.entry_id}"},
                blocking=True,
            )
        except Exception as exc:
            _LOGGER.debug("Erreur fermeture notif persistante: %s", exc)

        # Briefing : IA si activée, sinon TTS basique
        briefing_msg = None
        if cfg.get(CONF_AI_BRIEFING):
            from .ai import generate_briefing
            try:
                briefing_msg = await generate_briefing(self.hass, cfg, self.entry.title)
            except Exception as exc:
                _LOGGER.error("Erreur briefing IA au stop: %s", exc)

        if briefing_msg:
            # Notification Android + persistante
            await self._notifier(
                cfg.get(CONF_NOTIFY_DEVICE),
                "⏰ Briefing SmartWAKE", briefing_msg
            )
            try:
                await self.hass.services.async_call(
                    "persistent_notification", "create",
                    {
                        "title": "⏰ Briefing SmartWAKE",
                        "message": briefing_msg,
                        "notification_id": f"smartwake_briefing_{self.entry.entry_id}",
                    },
                    blocking=True,
                )
            except Exception as exc:
                _LOGGER.error("Erreur notif persistante briefing: %s", exc)
            # TTS
            if cfg.get(CONF_TTS_ENTITY):
                await self._tts_speak(briefing_msg)
        elif cfg.get(CONF_TTS_ACTIVEE) and cfg.get(CONF_TTS_ENTITY):
            await self._tts_briefing()

        # Vérif lever par IA (caméra) si activée
        if cfg.get(CONF_AI_VERIF_LEVER):
            self.hass.async_create_task(self._verif_lever_ia())

        # AI task personnalisée (au stop)
        if cfg.get(CONF_AI_CUSTOM_ENABLED) or cfg.get(CONF_AI_CUSTOM_TASKS):
            self.hass.async_create_task(self._run_custom_ai("on_stop"))

        self._reveil_en_cours = False
        self._skip_prochain = False
        self._skip_date = None
        self._aube_faite = False
        self._aube_niveau = 0
        self._snooze_fin = None
        self._etats_initiaux = {}
        self._pending_ringing = False
        self._statut_avant_snooze = None
        self._statut = STATUT_DONE
        # Réarme le déclencheur pour l'occurrence suivante : la planification
        # est à usage unique depuis le passage en point-dans-le-temps.
        self._planifier_trigger()
        self._log_event("Réveil arrêté")
        self._fire_event("smartwake_stopped", raison=raison)

        # Mode ponctuel : le réveil ne doit sonner qu'une fois. L'option était
        # proposée dans l'interface mais n'était lue nulle part.
        if cfg.get(CONF_PONCTUEL, False):
            _LOGGER.info("Réveil ponctuel '%s' — désactivation", self.entry.title)
            self._log_event("Réveil ponctuel — désactivé")
            await self.set_actif(False)
        self._increment_stat("total_stops")
        if hasattr(self, "_stats") and self._stats is not None:
            self._stats["dernier_reveil"] = dt_util.now().isoformat()
        # Enregistrer le lever réel pour l'apprentissage
        if self._learning is not None:
            try:
                heure_pgm = self.config.get(CONF_HEURE, "07:00")
                await self._learning.record_lever(heure_pgm, dt_util.now(), self._snooze_count)
            except Exception as exc:
                _LOGGER.debug("Erreur enregistrement learning: %s", exc)
        self._notify()
        _LOGGER.info("Réveil '%s' arrêté", self.entry.title)

    async def _tts_briefing(self) -> None:
        """Briefing vocal basique (fallback) : utilise le message configuré + météo."""
        cfg = self.entry.data
        # L'accès direct cfg[CONF_TTS_ENTITY] levait KeyError quand aucune
        # enceinte n'était configurée. _tts_speak gère déjà ce cas.
        try:
            tts_msg = cfg.get(CONF_TTS_MESSAGE, DEFAULT_TTS_MESSAGE)
            meteo = self.hass.states.get(cfg.get(CONF_WEATHER_ENTITY, "weather.home"))
            meteo_str = ""
            if meteo:
                meteo_str = f"Météo: {meteo.state}, {meteo.attributes.get('temperature', '?')}°C. "
            message = f"{tts_msg} {meteo_str}"
            await self._tts_speak(message)
        except Exception as exc:
            _LOGGER.error("Erreur TTS: %s", exc)

    def _tts_engine(self) -> str | None:
        """Entité du moteur de synthèse vocale.

        Si elle n'est pas configurée, on retient la première entité du domaine
        `tts` disponible : c'est plus utile que d'échouer silencieusement.
        """
        engine = self.entry.data.get(CONF_TTS_ENGINE)
        if engine:
            return engine
        for state in self.hass.states.async_all("tts"):
            return state.entity_id
        return None

    async def _tts_speak(self, message: str) -> None:
        """Parle via TTS sur l'enceinte configurée.

        `tts.speak` cible le moteur (`tts.*`) et reçoit l'enceinte dans
        `media_player_entity_id`. L'appel passait auparavant l'enceinte comme
        `entity_id` et omettait le paramètre requis : il était donc toujours
        rejeté, ce qui rendait le briefing vocal inopérant.
        """
        cfg = self.entry.data
        enceinte = cfg.get(CONF_TTS_ENTITY)
        if not enceinte:
            _LOGGER.debug("TTS ignoré : aucune enceinte configurée")
            return

        engine = self._tts_engine()
        if not engine:
            _LOGGER.warning(
                "TTS impossible : aucun moteur de synthèse vocale configuré ni détecté"
            )
            return

        try:
            await self.hass.services.async_call(
                "tts", "speak",
                {
                    "entity_id": engine,
                    "media_player_entity_id": enceinte,
                    "message": message,
                },
                blocking=True,
            )
            _LOGGER.info("TTS envoyé sur %s: %s...", enceinte, message[:50])
        except Exception as exc:
            _LOGGER.error("Erreur TTS: %s", exc)

    async def _verif_lever_ia(self) -> None:
        """Vérifie 10 min après le Stop si la personne est encore au lit (caméra+IA)."""
        await asyncio.sleep(10 * 60)
        if self._reveil_en_cours:
            return  # pas encore stoppé définitivement
        from .ai import verify_person_in_bed
        encore_au_lit = await verify_person_in_bed(self.hass, self.entry.data)
        if encore_au_lit:
            _LOGGER.info("Vérif IA: personne encore au lit — relance du réveil")
            self._log_event("Vérif IA: personne encore au lit — relance")
            # Passait par _escalade(0), qui sort aussitôt puisque le réveil est
            # justement arrêté à ce stade : la détection n'avait aucun effet.
            # On applique le niveau max directement.
            self._fire_event("smartwake_escalade", level="max")
            await self._escalade_niveau(1.0, 100, "max")

    async def _run_custom_ai(self, trigger: str) -> None:
        """Exécute les AI tasks personnalisées et notifie les résultats."""
        from .ai import run_custom_ai_task
        cfg = self.entry.data
        results = await run_custom_ai_task(self.hass, cfg, trigger)
        if not results:
            return
        _LOGGER.info("AI tasks custom (%s): %d résultat(s)", trigger, len(results))
        self._log_event(f"AI custom ({trigger}): {len(results)} tâche(s) exécutée(s)")
        # Notifier chaque résultat
        notify = cfg.get(CONF_NOTIFY_DEVICE)
        for msg in results:
            await self._notifier(notify, "🤖 SmartWAKE IA", msg)

    async def sauter_prochain(self) -> None:
        """Saute la prochaine occurrence sans toucher la planification."""
        await self.set_skip(True)
        _LOGGER.info(
            "Réveil du %s sauté pour '%s'",
            self._skip_date or "prochain jour actif", self.entry.title,
        )

    async def reset(self) -> None:
        """Remet à zéro l'état (watchdog nocturne)."""
        self._snooze_count = 0
        self._skip_prochain = False
        self._skip_date = None
        self._aube_faite = False
        self._aube_niveau = 0
        self._snooze_fin = None
        self._reveil_en_cours = False
        self._etats_initiaux = {}
        self._pending_ringing = False
        self._statut_avant_snooze = None
        self._statut = STATUT_IDLE if self._actif else STATUT_INACTIF
        self._planifier_trigger()
        self._notify()
        _LOGGER.info("Reset du réveil '%s'", self.entry.title)

    async def tester_ia(self, tache: str) -> str:
        """Exécute une tâche IA et rend un compte rendu lisible.

        Les tâches IA ne se déclenchent qu'à des moments précis, ce qui rendait
        leur mise au point laborieuse. Cette méthode les rend exécutables à la
        demande, depuis le menu d'options comme depuis le service smartwake.tester_ia.
        """
        from . import ai

        # On force le drapeau de la fonctionnalité testée : le test doit
        # fonctionner même si l'option n'est pas encore activée.
        cfg = dict(self.entry.data)
        drapeaux = {
            "briefing": CONF_AI_BRIEFING,
            "musique": CONF_AI_MUSIQUE_ADAPT,
            "suggestion": CONF_AI_SUGGESTION_HEURE,
            "bilan": CONF_AI_BILAN_HEBDO,
            "lever": CONF_AI_VERIF_LEVER,
        }
        if tache in drapeaux:
            cfg[drapeaux[tache]] = True

        try:
            if tache == "briefing":
                res = await ai.generate_briefing(self.hass, cfg, self.entry.title)
                if res:
                    await self._notifier(
                        cfg.get(CONF_NOTIFY_DEVICE), "⏰ Briefing SmartWAKE", res
                    )
                    # Tester aussi le TTS si configuré
                    if cfg.get(CONF_TTS_ENTITY):
                        await self._tts_speak(res)
            elif tache == "musique":
                options = [self._media_id(cfg.get(cle)) for cle in
                           (CONF_PLAYLIST, CONF_PLAYLIST_DOUCE, CONF_PLAYLIST_ENERGIQUE)]
                options = [o for o in dict.fromkeys(options) if o]
                if len(options) < 2:
                    return ("Au moins deux playlists sont nécessaires pour que "
                            "l'IA ait un choix à faire. Renseignez « Playlist "
                            "douce » ou « Playlist énergique » dans la section Musique.")
                res = await ai.choose_adaptive_music(self.hass, cfg, options)
            elif tache == "suggestion":
                res = await ai.suggest_wake_time(self.hass, cfg, cfg.get(CONF_HEURE, "07:00"))
                if res:
                    await self._notifier(
                        cfg.get(CONF_NOTIFY_DEVICE),
                        "⏰ Suggestion SmartWAKE", res
                    )
            elif tache == "bilan":
                res = await ai.generate_weekly_report(
                    self.hass, cfg, self.snooze_count, "test manuel"
                )
                if res:
                    await self._notifier(
                        cfg.get(CONF_NOTIFY_DEVICE), "🛏️ Bilan sommeil", res
                    )
            elif tache == "lever":
                probleme = await ai.diagnostic_presence_lit(self.hass, cfg)
                if probleme:
                    return probleme
                res = await ai.verify_person_in_bed(self.hass, cfg)
                res = "Une personne est au lit" if res else "Personne au lit"
            elif tache == "personnalisees":
                messages = []
                for declencheur in ("on_wake", "on_stop", "on_evening"):
                    msgs = await ai.run_custom_ai_task(self.hass, cfg, declencheur)
                    for m in msgs:
                        messages.append(f"[{declencheur}] {m}")
                        # Le test doit aussi envoyer la notification, comme le
                        # ferait le vrai déclencheur : sinon on teste le texte
                        # mais pas la livraison.
                        await self._notifier(
                            cfg.get(CONF_NOTIFY_DEVICE),
                            f"🤖 SmartWAKE IA ({declencheur})", m
                        )
                res = "\n".join(messages) if messages else None
            else:
                return f"Tâche inconnue : {tache}"
        except Exception as exc:
            return f"Échec : {type(exc).__name__} — {exc}"

        if res is None:
            return ("Aucun résultat. Vérifiez qu'une entité AI Task est "
                    "sélectionnée dans la section AI Task, et consultez les journaux.")
        return str(res)

    async def declencher_manuel(self) -> None:
        """Déclenche manuellement le cycle de réveil."""
        if self._reveil_en_cours:
            return
        self._cancel_cycle = self.hass.async_create_task(self._executer_cycle())

    async def bilan_hebdo_ia(self) -> None:
        """Génère et envoie un bilan de sommeil hebdomadaire via IA."""
        from .ai import generate_weekly_report
        cfg = self.entry.data
        if not cfg.get(CONF_AI_BILAN_HEBDO, False):
            return
        # Les statistiques d'apprentissage étaient collectées dans le .storage
        # mais get_stats() n'avait aucun appelant : le bilan recevait la chaîne
        # « historique non disponible » et self._snooze_count, nul hors cycle.
        stats = self._learning.get_stats() if self._learning else {}
        if stats.get("disponible"):
            historique = (
                f"{stats['nb_levers']} levers enregistrés, "
                f"écart moyen {stats['ecart_moyen_min']:+.0f} min "
                f"(écart-type {stats['ecart_type_min']:.0f} min), "
                f"{stats['snooze_moyen']:.1f} snooze par réveil, "
                f"rythme {'régulier' if stats.get('regulier') else 'irrégulier'}"
            )
            snoozes = stats.get("snooze_moyen", self._snooze_count)
        else:
            historique = stats.get("message", "historique non disponible")
            snoozes = self._snooze_count

        bilan = await generate_weekly_report(self.hass, cfg, snoozes, historique)
        if bilan:
            if await self._notifier(
                cfg.get(CONF_NOTIFY_DEVICE, ""), "🛏️ Bilan sommeil", bilan
            ):
                self._log_event("Bilan hebdo IA envoyé")