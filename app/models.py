from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class WateringEvent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    relay_id: Optional[int] = Field(default=None, index=True)
    zone_name: str
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_min: Optional[float] = None
    source: str = "hydrawise"
    raw_payload: Optional[str] = None


class MowingEvent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_min: Optional[float] = None
    area_m2: Optional[float] = None
    battery_start: Optional[int] = None
    battery_end: Optional[int] = None
    source: str = "dreame"
    raw_payload: Optional[str] = None


class WeatherSnapshot(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(index=True)
    temperature_c: Optional[float] = None
    precipitation_mm: Optional[float] = None
    humidity_pct: Optional[float] = None
    wind_kph: Optional[float] = None
    source: str = "open-meteo"


class GardenAction(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=datetime.utcnow, index=True)
    action_type: str  # fertilizing | planting | pruning | pest_control | other
    description: Optional[str] = None
    product: Optional[str] = None
    amount: Optional[str] = None
    zone: Optional[str] = None
    photo_path: Optional[str] = None


class Insight(SQLModel, table=True):
    """
    Historia wniosków AI (Gemini) wygenerowanych na podstawie zebranych danych.
    Generowane automatycznie co X godzin przez scheduler ORAZ na żądanie z
    dashboardu - obie ścieżki zapisują tutaj, żeby budować historię wniosków,
    a nie tylko pojedynczą odpowiedź "na żądanie".
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=datetime.utcnow, index=True)
    period_days: int
    summary_text: str
    triggered_by: str = "scheduler"  # scheduler | manual


class AppSetting(SQLModel, table=True):
    """
    Prosty magazyn klucz-wartość na ustawienia wpisywane w UI (klucze API,
    lokalizacja ogrodu itd.) - patrz app/runtime_settings.py. Pozwala zmieniać
    konfigurację z aplikacji (zakładka "Ustawienia") bez edycji .env i restartu
    kontenera.

    Uwaga: wartości trzymane są w bazie SQLite w postaci czystego tekstu, bez
    szyfrowania - wystarczające dla użytku osobistego/POC w sieci domowej, ale
    nie traktuj tego jako bezpiecznego magazynu sekretów produkcyjnych.
    """

    key: str = Field(primary_key=True)
    value: Optional[str] = None


class SessionToken(SQLModel, table=True):
    """
    Aktywna sesja zalogowanego użytkownika - patrz app/sessions.py.

    Trzymamy sesje w bazie (a nie w pamięci procesu), bo pod na k3s restartuje
    się przy każdym wdrożeniu (115 ReplicaSetów w ~2,5 miesiąca), a sesje w
    pamięci znikałyby wtedy razem z nim. Baza leży na PVC, więc przeżywa
    rollout i pozwala realnie unieważnić sesję przy wylogowaniu.

    W kolumnie NIE ma surowego tokenu z ciasteczka, tylko HMAC-SHA256 z niego,
    liczony kluczem SECRET_KEY. Dzięki temu ktoś, kto potrafi czytać albo
    zapisywać tę bazę z boku (np. sidecar sqlite-web), ani nie odtworzy cudzej
    sesji, ani nie wstrzyknie własnej - nie zna klucza.
    """

    token_hash: str = Field(primary_key=True)
    username: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime = Field(index=True)


class Plant(SQLModel, table=True):
    """Roślina umieszczona na mapie ogrodu (pin)."""

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    scientific_name: Optional[str] = None
    notes: Optional[str] = None
    zone: Optional[str] = None
    photo_path: Optional[str] = None
    x_pct: Optional[float] = None  # pozycja na mapie, 0-100% szerokości obrazu tła
    y_pct: Optional[float] = None  # pozycja na mapie, 0-100% wysokości obrazu tła
    added_via: str = "manual"  # manual | ai
    created_at: datetime = Field(default_factory=datetime.utcnow)


class GardenMapImage(SQLModel, table=True):
    """Obraz tła mapy ogrodu (zdjęcie/szkic). Używamy najnowszego wpisu jako aktywnej mapy."""

    id: Optional[int] = Field(default=None, primary_key=True)
    image_path: str
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)
