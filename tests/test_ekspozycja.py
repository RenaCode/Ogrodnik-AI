"""
Co było wystawione bez logowania - i test, żeby nie wróciło.

Sprawdzone anonimowo na produkcji 2026-09-12 (https://ogrodnik.renacode.com):

* GET /openapi.json  -> 200 z pełną mapą aplikacji (wszystkie trasy, nazwy pól
  formularza ustawień). /docs -> 200. Te trzy trasy rejestruje sam FastAPI,
  więc `dependencies=[Depends(authenticate)]` przy routerach ich nie dotyczyło.
* GET /photos/<cokolwiek> i /maps/<cokolwiek> -> 404 prosto ze StaticFiles,
  a nie 307 na /login jak każda chroniona trasa. `app.mount()` montuje osobną
  aplikację ASGI, do której zależności routerów się nie stosują. Nazwy plików
  to UUID4, więc nie dało się ich zgadnąć - ale to jest sekret przez
  nieodgadywalność, a nie kontrola dostępu: adres wycieka razem z Refererem,
  historią przeglądarki i logami proxy.
* Strona logowania ładowała kroje z fonts.googleapis.com (adres IP i
  User-Agent każdego odwiedzającego szły do Google) oraz skrypty z dwóch CDN-ów
  wykonywane w originie panelu.
"""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import TEST_PASSWORD, TEST_USERNAME

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "app" / "templates"


def _anon():
    from app.main import app

    return TestClient(app, base_url="https://testserver")


@pytest.mark.parametrize("sciezka", ["/openapi.json", "/docs", "/redoc"])
def test_schemat_openapi_nie_jest_wystawiony(sciezka):
    assert _anon().get(sciezka, follow_redirects=False).status_code == 404


@pytest.mark.parametrize("sciezka", ["/photos/deadbeef.jpg", "/maps/cafe1234.png"])
def test_zdjecia_i_mapy_wymagaja_sesji(sciezka):
    """Bez sesji ma być przekierowanie na /login, NIE odpowiedź ze statycznych plików."""
    response = _anon().get(sciezka, follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/login"


def test_zalogowany_dostaje_zdjecie_z_wlasciwym_typem(logged_in):
    from app.config import settings

    client, _ = logged_in
    settings.photos_dir.mkdir(parents=True, exist_ok=True)
    (settings.photos_dir / "test-zdjecie.jpg").write_bytes(b"\xff\xd8\xff\xe0udajemy-jpeg")

    response = client.get("/photos/test-zdjecie.jpg")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/jpeg")
    assert response.headers["x-content-type-options"] == "nosniff"


def test_plik_html_w_katalogu_zdjec_nie_jest_serwowany(logged_in):
    """
    Rozszerzenie bierze się z nazwy nadanej przez wysyłającego
    (routers/actions.py: `Path(photo.filename).suffix`), więc ".html" w katalogu
    zdjęć serwowałby się jako text/html z originu aplikacji. Biała lista
    rozszerzeń ma to odciąć, nawet gdy plik leży na dysku.
    """
    from app.config import settings

    client, _ = logged_in
    settings.photos_dir.mkdir(parents=True, exist_ok=True)
    (settings.photos_dir / "zlosliwy.html").write_bytes(b"<script>alert(1)</script>")

    assert client.get("/photos/zlosliwy.html").status_code == 404


@pytest.mark.parametrize("nazwa", ["..%2Fogrodnik-test.db", "%2e%2e%2fogrodnik-test.db", "podkatalog%2Fplik.jpg"])
def test_nie_da_sie_wyjsc_poza_katalog(logged_in, nazwa):
    client, _ = logged_in
    assert client.get(f"/photos/{nazwa}", follow_redirects=False).status_code in (307, 404)


def test_kroje_sa_serwowane_z_wlasnego_serwera():
    """Ekran logowania musi wczytać kroje, zanim ktokolwiek ma sesję - /static jest jawne."""
    response = _anon().get("/static/fonts/outfit-latin.woff2")
    assert response.status_code == 200
    assert response.content[:4] == b"wOF2"


def test_szablony_nie_wolaja_google_fonts():
    """
    Ten sam błąd naprawiono wcześniej w renacode-website. Panel administracyjny
    ma go nie mieć ponownie: zapytanie o krój wysyła IP i User-Agent do Google
    przy samym wyświetleniu ekranu logowania.

    Patrzymy na ATRYBUTY href/src, a nie na całą treść pliku - inaczej test
    wywracałby się o komentarz, który tę historię opisuje.
    """
    winowajcy = []
    for plik in TEMPLATES_DIR.glob("*.html"):
        for adres in re.findall(r"(?:href|src)=\"(https?://[^\"]+)\"", plik.read_text(encoding="utf-8")):
            if "fonts.googleapis.com" in adres or "fonts.gstatic.com" in adres:
                winowajcy.append(f"{plik.name}: {adres}")
    assert not winowajcy, f"kroje z Google Fonts wróciły do: {winowajcy}"


def test_kazdy_zewnetrzny_skrypt_ma_przypieta_wersje_albo_jest_znanym_wyjatkiem():
    """
    Skrypt z CDN-u wykonuje się w zalogowanej sesji administratora, a z tej
    sesji widać /settings z tokenem Home Assistanta i kluczami API. Ruchomy
    adres (`chart.js@4`) oznacza wykonywanie kodu, którego nikt tu nie widział.

    cdn.tailwindcss.com jest ZNANYM, ŚWIADOMYM wyjątkiem: to kompilator
    budowany na bieżąco, więc nie da się go przypiąć ani objąć `integrity`.
    Domknięcie wymaga zbudowania arkusza do pliku w obrazie.
    """
    dozwolone_bez_integrity = {"https://cdn.tailwindcss.com"}
    braki = []
    for plik in TEMPLATES_DIR.glob("*.html"):
        tresc = plik.read_text(encoding="utf-8")
        for tag in re.findall(r"<script\b[^>]*\bsrc=\"(https?://[^\"]+)\"[^>]*>", tresc):
            znacznik = re.search(
                r"<script\b[^>]*\bsrc=\"" + re.escape(tag) + r"\"[^>]*>", tresc
            ).group(0)
            if tag in dozwolone_bez_integrity:
                continue
            if "integrity=" not in znacznik:
                braki.append(f"{plik.name}: {tag}")
    assert not braki, f"zewnętrzny skrypt bez integrity: {braki}"


def test_login_dziala_po_zmianach():
    """Zabezpieczenie przed tym, żeby powyższe nie zepsuło zwykłego logowania."""
    client = _anon()
    response = client.post(
        "/login",
        data={"username": TEST_USERNAME, "password": TEST_PASSWORD},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert client.get("/", follow_redirects=False).status_code == 200
