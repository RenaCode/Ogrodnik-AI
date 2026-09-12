"""
Klient do Hunter Hydrawise REST API v1.

Ograniczenie API (świadomie przyjęte, patrz ARCHITECTURE.md): statusschedule.php
zwraca tylko NADCHODZĄCY harmonogram, nie historię. Historię budujemy sami w
scheduler.py, wykrywając przejścia stref między "czeka" i "biegnie teraz" (gdy
pole `time` w odpowiedzi == 1, strefa biegnie w tej chwili; `run` to wtedy
liczba sekund DO KOŃCA biegu).

Dokumentacja: https://www.hunterirrigation.com/sites/default/files/2024-03/Hydrawise%20REST%20API.pdf
"""

from datetime import datetime, timedelta
from typing import Any

import httpx

from .. import runtime_settings as rs

BASE_URL = "https://api.hydrawise.com/api/v1"


async def _get_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    """
    Wykonuje zapytanie i NIE WYPUSZCZA adresu URL do wyjątku.

    Hydrawise przyjmuje klucz API w query stringu (tak ma zaprojektowane API,
    nie mamy wyboru). `resp.raise_for_status()` httpx-a wkłada do komunikatu
    pełny adres razem z query stringiem:

        Client error '401 Unauthorized' for url
        'https://api.hydrawise.com/api/v1/statusschedule.php?api_key=...'

    a scheduler.py łapie to przez `logger.exception(...)`, więc klucz lądował
    otwartym tekstem w logach poda - czyli tam, gdzie sięga każdy z dostępem do
    logów albo do ich zbiórki, bez wchodzenia do panelu. Sprawdzone: klucz
    faktycznie pojawia się w sformatowanym rekordzie logu.

    Zamieniamy więc HTTPStatusError na wyjątek z samym kodem odpowiedzi.
    """
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, params=params)
        if resp.is_error:
            raise RuntimeError(
                f"Hydrawise API odpowiedziało HTTP {resp.status_code} "
                f"({url.rsplit('/', 1)[-1]})"
            )
        return resp.json()


class HydrawiseClient:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or rs.get_value("hydrawise_api_key")

    def _require_key(self) -> str:
        if not self.api_key:
            raise RuntimeError(
                "HYDRAWISE_API_KEY nie jest ustawiony - dodaj go w Ustawieniach albo w .env"
            )
        return self.api_key

    async def get_status_schedule(self, controller_id: int | None = None) -> dict[str, Any]:
        params = {"api_key": self._require_key()}
        if controller_id:
            params["controller_id"] = controller_id
        return await _get_json(f"{BASE_URL}/statusschedule.php", params)

    async def get_controllers(self) -> dict[str, Any]:
        params = {"api_key": self._require_key()}
        return await _get_json(f"{BASE_URL}/customerdetails.php", params)

    async def run_zone(self, relay_id: int, seconds: int) -> dict[str, Any]:
        params = {
            "api_key": self._require_key(),
            "action": "run",
            "period_id": 999,
            "relay_id": relay_id,
            "custom": seconds,
        }
        return await _get_json(f"{BASE_URL}/setzone.php", params)

    @staticmethod
    def parse_active_relays(status: dict[str, Any]) -> list[dict[str, Any]]:
        """Zwraca strefy, które w tej chwili biegną (time == 1)."""
        now = datetime.utcnow()
        active = []
        for relay in status.get("relays", []):
            if relay.get("time") == 1:
                run_seconds_remaining = relay.get("run", 0)
                active.append(
                    {
                        "relay_id": relay.get("relay_id"),
                        "name": relay.get("name"),
                        "estimated_end": now + timedelta(seconds=run_seconds_remaining),
                        "raw": relay,
                    }
                )
        return active
