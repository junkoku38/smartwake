"""Fonctions utilitaires partagées pour les entités."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN, integration_version


def make_device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer="SmartWAKE",
        model="Progressive alarm",
        sw_version=integration_version(),
    )