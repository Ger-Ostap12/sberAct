"""Обязательные решения пользователя для ипотечной генерации."""


def mortgage_choices_error(data):
    fields = data.get("fields") or {}
    def pick(key):
        return data[key] if key in data else fields.get(key)
    if pick("solidaryLiability") not in ("true", "false"):
        return "Выберите солидарное или несолидарное взыскание"
    if pick("claimResolution") not in ("full", "partial", "deny"):
        return "Выберите исход удовлетворения иска"
    return None
