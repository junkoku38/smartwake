"""Minimal mock of homeassistant.util.dt."""
from datetime import datetime, timezone, timedelta


def now():
    return datetime.now()


def utcnow():
    return datetime.now(timezone.utc)