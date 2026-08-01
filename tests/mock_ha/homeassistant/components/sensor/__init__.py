"""Mock minimal de homeassistant.components.sensor."""

from enum import StrEnum


class SensorDeviceClass(StrEnum):
    TIMESTAMP = "timestamp"
    ENUM = "enum"


class SensorStateClass(StrEnum):
    MEASUREMENT = "measurement"
    TOTAL = "total"
    TOTAL_INCREASING = "total_increasing"


class SensorEntityDescription:
    def __init__(self, key, name=None, icon=None, device_class=None,
                 state_class=None, entity_category=None, options=None, **kw):
        self.key = key
        self.name = name
        self.icon = icon
        self.device_class = device_class
        self.state_class = state_class
        self.entity_category = entity_category
        self.options = options
        for k, v in kw.items():
            setattr(self, k, v)


class SensorEntity:
    entity_description = None
    hass = None

    def async_write_ha_state(self):
        pass

    def async_on_remove(self, fn):
        pass
