"""Mock minimal de homeassistant.components.select."""


class SelectEntityDescription:
    def __init__(self, key, name=None, icon=None, **kw):
        self.key = key
        self.name = name
        self.icon = icon
        for k, v in kw.items():
            setattr(self, k, v)


class SelectEntity:
    entity_description = None
    hass = None

    def async_write_ha_state(self):
        pass

    def async_on_remove(self, fn):
        pass
