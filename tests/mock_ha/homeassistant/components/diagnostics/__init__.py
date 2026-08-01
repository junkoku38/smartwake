"""Mock minimal de homeassistant.components.diagnostics."""

REDACTED = "**REDACTED**"


def async_redact_data(data, to_redact):
    if not isinstance(data, dict):
        return data
    redacted = {}
    for key, value in data.items():
        if key in to_redact and value is not None:
            redacted[key] = REDACTED
        elif isinstance(value, dict):
            redacted[key] = async_redact_data(value, to_redact)
        else:
            redacted[key] = value
    return redacted
