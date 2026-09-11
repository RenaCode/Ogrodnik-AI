"""
Ograniczenie liczby prób logowania.

Wcześniej `/login` przyjmował dowolnie wiele prób w dowolnym tempie, więc hasło
administratora dało się zgadywać zdalnie bez żadnego kosztu.

Licznik trzymamy w pamięci procesu - inaczej niż sesje (app/sessions.py), i
świadomie:

* to krótkotrwały licznik, a nie stan, który musi przeżyć wdrożenie - restart
  poda kasuje najwyżej kilka minut historii nieudanych prób,
* gdyby leżał w bazie SQLite, mógłby go czyścić (albo dowolnie zawyżać, żeby
  zablokować właściciela) każdy, kto ma dostęp z boku do pliku bazy.

Kluczem jest para (adres klienta, login). Za Traefikiem `request.client.host`
bywa adresem poda ingressu, wspólnym dla wszystkich - dlatego limit jest na tyle
luźny, żeby nie odciąć właściciela po zwykłej pomyłce, a i tak sprowadza
zgadywanie hasła z tysięcy prób na minutę do kilkudziesięciu na godzinę.
"""

import time
from collections import defaultdict

# Maksymalna liczba nieudanych prób w oknie, zanim /login zacznie odrzucać.
MAX_ATTEMPTS = 10
WINDOW_SECONDS = 15 * 60

_failures: defaultdict[tuple[str, str], list[float]] = defaultdict(list)


def _recent(key: tuple[str, str], now: float) -> list[float]:
    fresh = [ts for ts in _failures[key] if now - ts < WINDOW_SECONDS]
    if fresh:
        _failures[key] = fresh
    else:
        # Nie zostawiamy pustych kluczy, żeby słownik nie puchł od losowych loginów.
        _failures.pop(key, None)
    return fresh


def is_blocked(client_ip: str, username: str) -> bool:
    now = time.time()
    return len(_recent((client_ip, username), now)) >= MAX_ATTEMPTS


def register_failure(client_ip: str, username: str) -> None:
    now = time.time()
    key = (client_ip, username)
    _recent(key, now)
    _failures[key].append(now)


def reset(client_ip: str, username: str) -> None:
    """Udane logowanie zeruje licznik dla tej pary."""
    _failures.pop((client_ip, username), None)
