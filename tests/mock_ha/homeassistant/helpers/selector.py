"""Minimal mock of homeassistant.helpers.selector — valid voluptuous validators."""
class _Validator:
    def __call__(self, val):
        return val
class EntitySelector(_Validator):
    def __init__(self, config=None): pass
class EntitySelectorConfig:
    def __init__(self, domain=None): pass
class TimeSelector(_Validator):
    pass
class NumberSelector(_Validator):
    def __init__(self, config=None): pass
class NumberSelectorConfig:
    def __init__(self, min=0, max=100, step=1, mode=None, unit_of_measurement=None): pass
class NumberSelectorMode:
    SLIDER = "slider"
class SelectSelector(_Validator):
    def __init__(self, config=None): pass
class SelectSelectorConfig:
    def __init__(self, options=None, mode=None): pass
class SelectSelectorMode:
    DROPDOWN = "dropdown"
class SelectOptionDict:
    def __init__(self, value=None, label=None): pass
