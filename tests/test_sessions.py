"""
BŁĄD 2: token sesji był stałą wartością - hmac(hasło, "admin").

Skutki, które tu zabezpieczamy testem:
* token był identyczny przy każdym logowaniu i wyprowadzony z hasła,
* /logout kasował ciasteczko tylko w przeglądarce - skopiowana wartość działała
  dalej aż do zmiany hasła,
* sesja nie miała terminu ważności po stronie serwera,
* /login przyjmował dowolnie wiele prób zgadywania hasła.
"""

from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlmodel import select

from conftest import TEST_PASSWORD, TEST_USERNAME


def _new_client():
    from app.main import app

    return TestClient(app, base_url="https://testserver")


def _login(client, password=TEST_PASSWORD, username=TEST_USERNAME):
    return client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )


def test_kolejne_logowania_daja_rozne_tokeny():
    tokens = set()
    for _ in range(3):
        client = _new_client()
        assert _login(client).status_code == 303
        tokens.add(client.cookies["session_token"])
    assert len(tokens) == 3, "token sesji jest stały - da się go odtworzyć raz na zawsze"


def test_token_nie_jest_pochodna_hasla(logged_in):
    import hashlib
    import hmac

    from app.config import settings

    _, token = logged_in

    stary_schemat = hmac.new(
        settings.admin_password.encode(),
        settings.admin_username.encode(),
        hashlib.sha256,
    ).hexdigest()
    assert stary_schemat not in token
    assert settings.admin_username not in token


def test_wylogowanie_uniewaznia_token_po_stronie_serwera(logged_in):
    client, token = logged_in

    assert client.get("/", follow_redirects=False).status_code == 200
    assert client.get("/logout", follow_redirects=False).status_code == 303

    # Kopia ciasteczka zabrana przed wylogowaniem - np. z cudzej przeglądarki
    # albo z logów proxy - nie może dalej działać.
    skopiowane = _new_client()
    skopiowane.cookies.set("session_token", token)
    response = skopiowane.get("/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/login"


def test_wygasla_sesja_jest_odrzucana(logged_in):
    from app.db import get_session
    from app.models import SessionToken

    client, _ = logged_in

    with get_session() as db:
        row = db.exec(select(SessionToken)).one()
        row.expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.add(row)
        db.commit()

    response = client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/login"


def test_w_bazie_nie_ma_surowego_tokenu(logged_in):
    """Sidecar sqlite-web czyta tę bazę - w tabeli ma leżeć HMAC, nie ciasteczko."""
    from app.db import get_session
    from app.models import SessionToken

    _, token = logged_in

    with get_session() as db:
        row = db.exec(select(SessionToken)).one()

    assert row.token_hash != token
    assert token not in row.token_hash


def test_api_bez_sesji_zwraca_401():
    client = _new_client()
    assert client.get("/api/timeline").status_code == 401


def test_login_ogranicza_liczbe_prob():
    from app.login_guard import MAX_ATTEMPTS

    client = _new_client()
    for _ in range(MAX_ATTEMPTS):
        assert _login(client, password="zle-haslo").status_code == 200

    # Po przekroczeniu limitu nawet poprawne hasło ma zostać odrzucone.
    assert _login(client, password="zle-haslo").status_code == 429
    assert _login(client).status_code == 429
