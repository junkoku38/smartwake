"""Minimal mock of homeassistant.helpers.event."""
from __future__ import annotations
from typing import Callable


def async_track_time_change(hass, callback, hour=None, minute=None, second=None):
    return lambda: None


def async_track_point_in_time(hass, callback, point):
    return lambda: None

def async_track_point_in_utc_time(hass, callback, point):
    return lambda: None


def async_track_state_change_event(hass, entities, callback):
    return lambda: None
