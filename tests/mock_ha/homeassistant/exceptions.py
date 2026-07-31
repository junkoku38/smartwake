"""Mock minimal de homeassistant.exceptions."""


class HomeAssistantError(Exception):
    """Erreur générique de Home Assistant."""


class ServiceValidationError(HomeAssistantError):
    """Erreur de validation d'un appel de service."""


class ConfigEntryNotReady(HomeAssistantError):
    """L'entrée de configuration n'est pas prête."""
