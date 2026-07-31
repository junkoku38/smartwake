"""Mock minimal de homeassistant.components.number."""


class NumberMode:
    SLIDER = "slider"
    BOX = "box"


class NumberEntityDescription:
    def __init__(self, key, name=None, icon=None, native_min_value=None,
                 native_max_value=None, native_step=None, **kw):
        self.key = key
        self.name = name
        self.icon = icon
        self.native_min_value = native_min_value
        self.native_max_value = native_max_value
        self.native_step = native_step
        for k, v in kw.items():
            setattr(self, k, v)


class NumberEntity:
    entity_description = None
    hass = None

    @property
    def native_step(self):
        return getattr(self.entity_description, "native_step", None)

    def async_write_ha_state(self):
        pass

    def async_on_remove(self, fn):
        pass
