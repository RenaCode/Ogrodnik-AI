from pathlib import Path

from dotenv import load_dotenv
from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")


class Settings(BaseSettings):
    garden_lat: float = 52.2297
    garden_lon: float = 21.0122
    garden_name: str = "Mój ogród"

    hydrawise_api_key: str | None = None

    ha_base_url: str | None = None
    ha_long_lived_token: str | None = None
    ha_mower_entity_id: str | None = None

    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"

    poll_interval_minutes: int = 5

    admin_username: str = "admin"

    # ADMIN_PASSWORD i SECRET_KEY celowo NIE mają wartości domyślnych. Repo jest
    # publiczne (MIT), więc każda wpisana tu domyślna wartość jest z definicji
    # znana wszystkim - a login chroni zakładkę "Ustawienia" z tokenem Home
    # Assistanta i kluczami API. Ciche zejście na wartość domyślną jest gorsze
    # niż awaria, bo instancja wygląda na działającą i zabezpieczoną. Brak
    # którejkolwiek z tych zmiennych = twarde zatrzymanie startu (patrz niżej).
    admin_password: str
    # Klucz podpisu identyfikatorów sesji - osobny sekret, NIE pochodna hasła
    # (patrz app/sessions.py). Wygeneruj: python -c "import secrets;
    # print(secrets.token_urlsafe(48))"
    secret_key: str

    # Sieci, z których wolno wierzyć nagłówkowi X-Forwarded-For przy ustalaniu
    # adresu klienta (patrz app/main.py:_client_ip). Lista CIDR po przecinku,
    # np. "10.42.0.0/16" dla domyślnej sieci podów k3s.
    #
    # DOPÓKI JEST PUSTA, limit prób logowania działa GLOBALNIE, nie per adres:
    # za Traefikiem każde połączenie przychodzi z poda ingressu, więc wszyscy
    # klienci z internetu - razem z właścicielem - dzielą jeden licznik.
    # Konsekwencja jest taka, że ktokolwiek może trzymać panel zamknięty przed
    # właścicielem, wysyłając MAX_ATTEMPTS błędnych haseł raz na WINDOW_SECONDS.
    #
    # Wartości domyślnej celowo NIE MA: zaufanie nagłówkowi bez wskazania sieci
    # proxy jest gorsze niż brak limitu (każdy dopisuje losowy adres i ma
    # czysty licznik na każdą próbę). Adres sieci podów musi podać operator.
    trusted_proxy_cidrs: str = ""

    data_dir: Path = ROOT_DIR / "data"
    photos_dir: Path = ROOT_DIR / "data" / "photos"
    maps_dir: Path = ROOT_DIR / "data" / "maps"
    db_path: Path = ROOT_DIR / "data" / "ogrodnik.db"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def trusted_proxy_networks(self) -> list:
        """TRUSTED_PROXY_CIDRS rozbite na obiekty sieci; wpisy nie do sparsowania pomijamy."""
        import ipaddress

        networks = []
        for item in self.trusted_proxy_cidrs.split(","):
            item = item.strip()
            if not item:
                continue
            try:
                networks.append(ipaddress.ip_network(item, strict=False))
            except ValueError:
                continue
        return networks


# Opisy zmiennych wymaganych do startu - trafiają do komunikatu błędu, żeby
# operator wiedział nie tylko CZEGO brakuje, ale i co dokładnie wpisać.
_REQUIRED_ENV_HELP: dict[str, str] = {
    "ADMIN_PASSWORD": (
        "hasło do logowania w panelu (login z ADMIN_USERNAME, domyślnie \"admin\")"
    ),
    "SECRET_KEY": (
        "losowy klucz podpisu sesji, np. z:\n"
        "        python -c \"import secrets; print(secrets.token_urlsafe(48))\""
    ),
}


def _missing_env_error(exc: ValidationError) -> str:
    missing = [
        str(err["loc"][0]).upper()
        for err in exc.errors()
        if err.get("type") == "missing" and err.get("loc")
    ]
    lines = [
        "",
        "Ogrodnik AI nie wystartuje: brak wymaganych zmiennych środowiskowych.",
        "",
    ]
    for name in missing:
        lines.append(f"  {name} - {_REQUIRED_ENV_HELP.get(name, 'wartość wymagana')}")
    lines += [
        "",
        "Ustaw je w pliku .env (patrz .env.example), w sekcji environment/env_file",
        "docker-compose.yml, albo w Secrecie Kubernetes wskazanym przez",
        "values.yaml -> secretName.",
        "",
    ]
    return "\n".join(lines)


try:
    settings = Settings()
except ValidationError as exc:
    if any(err.get("type") == "missing" for err in exc.errors()):
        # SystemExit zamiast ValidationError: chodzi o to, żeby w logach poda
        # (albo w konsoli docker compose) było widać czytelną instrukcję, a nie
        # ścianę stacktrace'u pydantica.
        raise SystemExit(_missing_env_error(exc)) from None
    raise

settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.photos_dir.mkdir(parents=True, exist_ok=True)
settings.maps_dir.mkdir(parents=True, exist_ok=True)
