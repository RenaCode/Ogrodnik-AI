"""
Dwie rzeczy, które wyciekały albo mogły wyciec.

1. ADRES KLIENTA (app/main.py:_client_ip). Uvicorn ma ProxyHeadersMiddleware
   włączony domyślnie, ale ufa nagłówkom X-Forwarded-* tylko wtedy, gdy drugi
   koniec połączenia jest na liście `forwarded_allow_ips` - a ta domyślnie
   zawiera sam 127.0.0.1, więc pod Traefika na niej nie jest. Czytamy więc ten
   nagłówek sami, ale wyłącznie z sieci wskazanych w TRUSTED_PROXY_CIDRS.
   Bezwarunkowe zaufanie byłoby gorsze niż brak limitu: każdy dopisywałby
   losowy adres i miał czysty licznik do każdej próby hasła.

2. KLUCZ HYDRAWISE W LOGACH. Hydrawise przyjmuje klucz API w query stringu,
   a `httpx.Response.raise_for_status()` wkleja pełny adres do komunikatu
   wyjątku. scheduler.py łapie to przez `logger.exception(...)`, więc klucz
   lądował otwartym tekstem w logach poda - poza panelem i poza logowaniem.
"""

import asyncio
import io
import logging

import httpx
import pytest

from app.config import settings
from app.integrations import hydrawise
from app.main import _client_ip


def _request(peer: str, xff: str | None = None):
    from fastapi import Request

    headers = [(b"x-forwarded-for", xff.encode())] if xff else []
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/login",
            "headers": headers,
            "client": (peer, 1234),
            "scheme": "https",
            "server": ("ogrodnik", 443),
            "query_string": b"",
        }
    )


@pytest.fixture
def zaufane_proxy(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_cidrs", "10.42.0.0/16")


def test_bez_konfiguracji_naglowek_jest_ignorowany(monkeypatch):
    """Domyślnie (pusta lista) X-Forwarded-For nie ma żadnego wpływu."""
    monkeypatch.setattr(settings, "trusted_proxy_cidrs", "")
    assert _client_ip(_request("10.42.0.7", "1.2.3.4")) == "10.42.0.7"


def test_z_zaufanego_proxy_bierzemy_adres_klienta(zaufane_proxy):
    assert _client_ip(_request("10.42.0.7", "203.0.113.9")) == "203.0.113.9"


def test_klient_nie_podszyje_sie_dopisujac_wlasny_wpis(zaufane_proxy):
    """
    Klient może wysłać własny X-Forwarded-For; proxy DOPISUJE do niego adres
    rzeczywisty. Dlatego czytamy od prawej i bierzemy ostatni wpis spoza sieci
    zaufanych - czyli ten dopisany przez proxy, nie ten zmyślony przez klienta.
    """
    assert _client_ip(_request("10.42.0.7", "9.9.9.9, 203.0.113.9")) == "203.0.113.9"


def test_naglowek_od_niezaufanego_peera_jest_ignorowany(zaufane_proxy):
    """Pod z boku klastra, omijający Traefika, nie może sobie wybrać adresu."""
    assert _client_ip(_request("203.0.113.50", "1.2.3.4")) == "203.0.113.50"


def test_smieci_w_naglowku_nie_wywracaja_zapytania(zaufane_proxy):
    assert _client_ip(_request("10.42.0.7", "nie-adres, ???")) == "10.42.0.7"


def test_blad_hydrawise_nie_niesie_klucza_api():
    transport = httpx.MockTransport(lambda request: httpx.Response(401, json={"error": "nope"}))

    async def zawolaj():
        original = httpx.AsyncClient

        class Klient(original):
            def __init__(self, *args, **kwargs):
                kwargs["transport"] = transport
                super().__init__(*args, **kwargs)

        httpx.AsyncClient = Klient
        try:
            await hydrawise._get_json(
                f"{hydrawise.BASE_URL}/statusschedule.php", {"api_key": "SEKRETNY-KLUCZ"}
            )
        finally:
            httpx.AsyncClient = original

    with pytest.raises(RuntimeError) as exc:
        asyncio.run(zawolaj())

    assert "SEKRETNY-KLUCZ" not in str(exc.value)
    assert "401" in str(exc.value)


def test_klucz_nie_trafia_do_sformatowanego_rekordu_logu():
    """
    Tak wygląda ścieżka z produkcji: scheduler.py łapie wyjątek i woła
    logger.exception(). Sprawdzamy to, co faktycznie ląduje w logu.
    """
    bufor = io.StringIO()
    logger = logging.getLogger("test.ogrodnik.hydrawise")
    handler = logging.StreamHandler(bufor)
    logger.addHandler(handler)
    try:
        try:
            raise RuntimeError("Hydrawise API odpowiedziało HTTP 401 (statusschedule.php)")
        except RuntimeError:
            logger.exception("Błąd podczas pollowania Hydrawise")
    finally:
        logger.removeHandler(handler)

    zapis = bufor.getvalue()
    assert "api_key" not in zapis
    assert "401" in zapis
