import voluptuous as vol
def ensure_list(val):
    if val is None: return []
    return val if isinstance(val, list) else [val]
