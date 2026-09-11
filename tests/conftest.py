"""
Wspólna konfiguracja testów.

Zmienne środowiskowe ustawiamy tutaj, na poziomie modułu, bo app/config.py
buduje obiekt Settings (a app/db.py silnik SQLite) już przy imporcie - później
byłoby za późno. Z tego samego powodu każdy test dostaje bazę w katalogu
tymczasowym, a nie w repo.

Uruchamianie (obraz stoi na Pythonie 3.12; na 3.14 sqlmodel 0.0.22 nie startuje):
    uv venv --python 3.12 .venv
    uv pip install -r requirements.txt -r requirements-dev.txt
    .venv/bin/python -m pytest
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

TEST_USERNAME = "admin"
TEST_PASSWORD = "haslo-tylko-do-testow"
TEST_SECRET_KEY = "klucz-podpisu-tylko-do-testow"

_TMP_DIR = Path(tempfile.mkdtemp(prefix="ogrodnik-tests-"))

os.environ["ADMIN_USERNAME"] = TEST_USERNAME
os.environ["ADMIN_PASSWORD"] = TEST_PASSWORD
os.environ["SECRET_KEY"] = TEST_SECRET_KEY
os.environ["DATA_DIR"] = str(_TMP_DIR)
os.environ["PHOTOS_DIR"] = str(_TMP_DIR / "photos")
os.environ["MAPS_DIR"] = str(_TMP_DIR / "maps")
os.environ["DB_PATH"] = str(_TMP_DIR / "ogrodnik-test.db")

# app/templates.py wskazuje katalog szablonów ścieżką względną ("app/templates"),
# więc testy muszą działać z katalogu głównego repo.
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_TMP_DIR, ignore_errors=True)


@pytest.fixture(autouse=True)
def _clean_state():
    """Każdy test zaczyna z pustą tabelą sesji i wyzerowanym licznikiem prób."""
    from sqlmodel import select

    from app.db import get_session, init_db
    from app.login_guard import _failures
    from app.models import SessionToken

    init_db()
    with get_session() as db:
        for row in db.exec(select(SessionToken)).all():
            db.delete(row)
        db.commit()
    _failures.clear()
    yield


@pytest.fixture
def client():
    """
    Klient testowy.

    Bez `with`, celowo: menedżer kontekstu odpaliłby zdarzenie startup, a razem
    z nim schedulera pytającego o Hydrawise/Open-Meteo/Home Assistanta.
    base_url na https, bo ciasteczko sesyjne ma flagę Secure.
    """
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app, base_url="https://testserver")


@pytest.fixture
def logged_in(client):
    """Klient z aktywną sesją; zwraca (klient, surowy token z ciasteczka)."""
    response = client.post(
        "/login",
        data={"username": TEST_USERNAME, "password": TEST_PASSWORD},
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text
    token = client.cookies["session_token"]
    return client, token
