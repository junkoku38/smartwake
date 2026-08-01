"""Mock minimal de homeassistant.helpers.restore_state."""


class RestoreEntity:
    async def async_added_to_hass(self):
        pass

    async def async_get_last_state(self):
        return None
