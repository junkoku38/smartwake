"""Mock minimal de homeassistant.helpers.selector.

Les sélecteurs sont de simples validateurs voluptuous permissifs : le but est de
valider la logique du config flow, pas le rendu du frontend. Les constructeurs
acceptent n'importe quel argument nommé, afin que l'ajout d'une option de
sélecteur côté intégration ne casse pas la suite de tests.
"""


class _Validator:
    """Validateur voluptuous neutre."""

    def __init__(self, config=None, **kwargs):
        self.config = config
        self.kwargs = kwargs

    def __call__(self, val):
        return val


class _Config(dict):
    """Configuration de sélecteur, tolérante à toute option."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        for key, value in kwargs.items():
            setattr(self, key, value)


class EntitySelector(_Validator):
    pass


class EntitySelectorConfig(_Config):
    pass


class TimeSelector(_Validator):
    pass


class TimeSelectorConfig(_Config):
    pass


class NumberSelector(_Validator):
    pass


class NumberSelectorConfig(_Config):
    pass


class NumberSelectorMode:
    SLIDER = "slider"
    BOX = "box"


class SelectSelector(_Validator):
    pass


class SelectSelectorConfig(_Config):
    pass


class SelectSelectorMode:
    DROPDOWN = "dropdown"
    LIST = "list"


class SelectOptionDict(dict):
    def __init__(self, value=None, label=None):
        super().__init__(value=value, label=label)
        self.value = value
        self.label = label


class TextSelector(_Validator):
    pass


class TextSelectorConfig(_Config):
    pass


class TextSelectorType:
    TEXT = "text"
    PASSWORD = "password"


class BooleanSelector(_Validator):
    pass


class MediaSelector(_Validator):
    pass


class MediaSelectorConfig(_Config):
    pass


class DeviceSelector(_Validator):
    pass


class DeviceSelectorConfig(_Config):
    pass


class AreaSelector(_Validator):
    pass


class AreaSelectorConfig(_Config):
    pass


class TemplateSelector(_Validator):
    pass


class IconSelector(_Validator):
    pass


class DurationSelector(_Validator):
    pass


class DurationSelectorConfig(_Config):
    pass
