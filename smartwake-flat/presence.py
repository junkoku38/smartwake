"""Interprétation des capteurs de présence au lit.

L'utilisateur choisit ses capteurs, l'intégration doit les comprendre quelle
qu'en soit la nature : binaire (radar, tapis, in_bed), numérique (pression,
poids), ou à valeur d'état (home/away). Chacun a sa sémantique et son
comportement propre.

Cas particulier des capteurs Withings : leur état passe à « unknown » peu après
l'endormissement et le reste toute la nuit, l'intégration ne publiant l'état
que par synchronisation. Un « unknown » ne signifie donc pas « on ne sait
pas », mais « rien de neuf depuis le dernier état connu ». On consulte alors le
recorder pour récupérer ce dernier état, dans une fenêtre récente.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

INDISPONIBLES = ("unknown", "unavailable", "none", "", None)

_VRAI = ("on", "home", "occupied", "detected", "true", "present", "yes")
_FAUX = ("off", "not_home", "clear", "not_detected", "false", "absent", "no", "away")

# Au-delà, un dernier état connu « au lit » n'est plus une preuve de présence :
# la personne peut s'être levée sans que le capteur l'ait publié.
FENETRE_DERNIER_ETAT = timedelta(hours=12)


def interpreter_etat(valeur: str | None) -> bool | None:
    """Traduit l'état brut d'un capteur en présence au lit.

    Renvoie True (au lit), False (pas au lit) ou None (indéterminé).
    """
    if valeur is None:
        return None
    brut = str(valeur).strip().lower()
    if brut in _VRAI:
        return True
    if brut in _FAUX:
        return False
    try:
        # Capteur numérique : pression, poids, distance… toute valeur non nulle
        # est interprétée comme une présence.
        return float(brut) > 0
    except (TypeError, ValueError):
        return None


async def _dernier_etat_exploitable(
    hass: HomeAssistant, entity_id: str
) -> bool | None:
    """Dernier état connu d'un capteur, quand son état courant est indisponible.

    Sert aux capteurs Withings, « unknown » la nuit : le dernier « au lit »
    reste pertinent tant qu'aucun « levé » ne l'a suivi.
    """
    try:
        from homeassistant.components.recorder import get_instance, history
    except ImportError:
        return None

    debut = dt_util.now() - FENETRE_DERNIER_ETAT
    try:
        brut = await get_instance(hass).async_add_executor_job(
            lambda: history.state_changes_during_period(
                hass, debut, dt_util.now(), entity_id,
                include_start_time_state=True, no_attributes=True,
            )
        )
    except Exception as exc:  # noqa: BLE001 - l'historique est un bonus
        _LOGGER.debug("Historique indisponible pour %s: %s", entity_id, exc)
        return None

    etats = (brut or {}).get(entity_id) or []
    for etat in reversed(etats):
        valeur = getattr(etat, "state", None)
        verdict = interpreter_etat(valeur)
        if verdict is not None:
            return verdict
    return None


async def releve_presence_lit(
    hass: HomeAssistant, capteurs: list[str]
) -> dict[str, bool]:
    """Verdict de présence pour chaque capteur réellement exploitable.

    Un capteur dont l'état courant est indisponible est rattrapé par son dernier
    état connu. Les capteurs qui restent indéterminés sont absents du résultat.
    """
    verdicts: dict[str, bool] = {}
    for entity_id in capteurs:
        etat = hass.states.get(entity_id)
        brut = etat.state if etat is not None else None

        verdict = interpreter_etat(brut)
        if verdict is None and (brut is None or brut in INDISPONIBLES):
            verdict = await _dernier_etat_exploitable(hass, entity_id)

        if verdict is not None:
            verdicts[entity_id] = verdict
    return verdicts


async def diagnostic_capteurs(
    hass: HomeAssistant, capteurs: list[str]
) -> str | None:
    """Message d'aide si aucun capteur n'est exploitable, sinon None."""
    if not capteurs:
        return ("Aucun capteur de présence au lit configuré. Renseignez-en un "
                "dans la section Intelligence.")

    verdicts = await releve_presence_lit(hass, capteurs)
    if verdicts:
        return None

    details = []
    for entity_id in capteurs:
        etat = hass.states.get(entity_id)
        details.append(f"{entity_id} ({etat.state if etat else 'introuvable'})")
    return (
        "Capteur(s) de présence au lit configuré(s), mais aucun n'est "
        "exploitable actuellement, même via leur dernier état connu : "
        + ", ".join(details) + ". Un capteur Withings passe à « unknown » la "
        "nuit et n'est publié qu'après synchronisation ; un radar hors ligne "
        "est « unavailable »."
    )
