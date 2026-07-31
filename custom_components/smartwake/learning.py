"""Apprentissage automatique — suit les habitudes de réveil et suggère des ajustements.

Stocke l'historique dans le .storage de HA et calcule:
  - Heure de lever réelle moyenne (vs heure programmée)
  - Nombre de snooze moyen
  - Écart type (régularité)
  - Suggestion d'ajustement
"""

from __future__ import annotations

import logging
import statistics
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
STORAGE_KEY = f"{DOMAIN}_learning"
STORAGE_VERSION = 1


class LearningManager:
    """Gère l'apprentissage des habitudes de réveil."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._hass = hass
        self._entry_id = entry_id
        self._store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}_{entry_id}")
        self._data: dict[str, Any] = {}

    async def async_load(self) -> None:
        """Charge les données d'apprentissage."""
        self._data = await self._store.async_load() or {
            "levers": [],
            "snoozes": [],
            "heures_programmees": [],
        }

    async def async_save(self) -> None:
        """Sauvegarde les données."""
        await self._store.async_save(self._data)

    async def record_lever(self, heure_programmee: str, heure_reelle: datetime, snoozes: int) -> None:
        """Enregistre un lever réel."""
        self._data.setdefault("levers", []).append({
            "date": heure_reelle.date().isoformat(),
            "heure_programmee": heure_programmee,
            "heure_reelle": heure_reelle.isoformat(),
            "ecart_min": (heure_reelle - heure_reelle.replace(
                hour=int(heure_programmee.split(":")[0]),
                minute=int(heure_programmee.split(":")[1]),
                second=0, microsecond=0
            )).total_seconds() / 60,
            "snoozes": snoozes,
        })
        self._data.setdefault("snoozes", []).append(snoozes)
        self._data.setdefault("heures_programmees", []).append(heure_programmee)
        # Garder 90 jours max
        for key in ("levers", "snoozes", "heures_programmees"):
            if len(self._data[key]) > 90:
                self._data[key] = self._data[key][-90:]
        await self.async_save()

    def get_stats(self) -> dict[str, Any]:
        """Retourne les statistiques d'apprentissage."""
        levers = self._data.get("levers", [])
        snoozes = self._data.get("snoozes", [])

        if len(levers) < 3:
            return {"disponible": False, "message": "Pas assez de données (minimum 3 levers)"}

        ecarts = [l["ecart_min"] for l in levers]
        ecart_moyen = statistics.mean(ecarts)
        ecart_type = statistics.stdev(ecarts) if len(ecarts) > 1 else 0
        snooze_moyen = statistics.mean(snoozes) if snoozes else 0

        return {
            "disponible": True,
            "nb_levers": len(levers),
            "ecart_moyen_min": round(ecart_moyen, 1),
            "ecart_type_min": round(ecart_type, 1),
            "snooze_moyen": round(snooze_moyen, 1),
            "regulier": ecart_type < 15,
            "suggestion": self._generate_suggestion(ecart_moyen, ecart_type, snooze_moyen),
        }

    def _generate_suggestion(self, ecart_moyen: float, ecart_type: float, snooze_moyen: float) -> str:
        """Génère une suggestion d'ajustement."""
        suggestions = []

        if ecart_moyen > 15:
            suggestions.append(f"Vous vous levez en moyenne {int(ecart_moyen)} min après l'heure programmée. "
                             f"Envisagez de reculer l'heure de {int(ecart_moyen)} min.")
        elif ecart_moyen < -10:
            suggestions.append(f"Vous vous levez en moyenne {int(-ecart_moyen)} min avant l'heure. "
                             f"Envisagez d'avancer l'heure de {int(-ecart_moyen)} min.")

        if snooze_moyen > 2:
            suggestions.append(f"Vous utilisez en moyenne {snooze_moyen:.1f} snoozes. "
                             f"Réduisez le max snooze ou reculez l'heure de {int(snooze_moyen * 5)} min.")

        if ecart_type > 20:
            suggestions.append(f"Vos heures de lever sont irrégulières (écart-type {int(ecart_type)} min). "
                             f"Essayez de fixer une heure plus régulière.")

        if not suggestions:
            suggestions.append("Votre rythme est régulier — aucune ajustement nécessaire.")

        return " ".join(suggestions)