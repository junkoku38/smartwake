def async_get(hass):
    return _Registry()
class _Registry:
    def async_get(self, entity_id):
        return None
