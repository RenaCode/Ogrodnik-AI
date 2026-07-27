"""
Ustawienia, które można nadpisać z UI (zakładka "Ustawienia"), zamiast tylko
przez .env - wygodne w Dockerze, gdzie edycja .env wymaga przebudowy/restartu
kontenera, a tak wystarczy formularz w aplikacji.

Pierwszeństwo: wartość zapisana w bazie (tabela AppSetting) > wartość z .env
(app/config.py) > brak (None).
"""

from typing import Optional

from .config import settings as env_settings
from .db import get_session
from .models import AppSetting

# Klucze, które można nadpisać z UI - razem z etykietami/opisami do formularza.
OVERRIDABLE_FIELDS: list[dict[str, str]] = [
    {"key": "garden_name", "label": "Nazwa ogrodu", "type": "text"},
    {"key": "garden_lat", "label": "Szerokość geograficzna (lat)", "type": "text"},
    {"key": "garden_lon", "label": "Długość geograficzna (lon)", "type": "text"},
    {"key": "hydrawise_api_key", "label": "Hunter Hydrawise - API key", "type": "password"},
    {"key": "ha_base_url", "label": "Home Assistant - adres (np. http://homeassistant.local:8123)", "type": "text"},
    {"key": "ha_long_lived_token", "label": "Home Assistant - Long-Lived Access Token", "type": "password"},
    {"key": "ha_mower_entity_id", "label": "Home Assistant - entity_id kosiarki", "type": "text"},
    {"key": "gemini_api_key", "label": "Gemini AI - API key", "type": "password"},
    {"key": "gemini_model", "label": "Gemini AI - model", "type": "text"},
    {"key": "language", "label": "Język / Language", "type": "select"},
]
OVERRIDABLE_KEYS = {f["key"] for f in OVERRIDABLE_FIELDS}


def get_value(key: str) -> Optional[str]:
    if key not in OVERRIDABLE_KEYS:
        raise KeyError(f"Nieznany klucz ustawienia: {key}")
    with get_session() as session:
        row = session.get(AppSetting, key)
    if row and row.value:
        return row.value
    default = getattr(env_settings, key, None)
    if key == "language" and not default:
        return "pl"
    return str(default) if default is not None else None


def get_float(key: str) -> Optional[float]:
    value = get_value(key)
    return float(value) if value not in (None, "") else None


def set_value(key: str, value: Optional[str]) -> None:
    if key not in OVERRIDABLE_KEYS:
        raise KeyError(f"Nieznany klucz ustawienia: {key}")
    with get_session() as session:
        row = session.get(AppSetting, key)
        if row is None:
            row = AppSetting(key=key, value=value or None)
        else:
            row.value = value or None
        session.add(row)
        session.commit()


def get_all() -> dict[str, Optional[str]]:
    return {f["key"]: get_value(f["key"]) for f in OVERRIDABLE_FIELDS}


def set_all(values: dict[str, str]) -> None:
    """Zapisuje tylko pola, dla których przesłano niepustą wartość - puste pole
    w formularzu oznacza "zachowaj obecną wartość" (patrz routers/settings.py)."""
    for key in OVERRIDABLE_KEYS:
        if key in values and values[key].strip():
            set_value(key, values[key].strip())
