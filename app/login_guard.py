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

Kluczem jest para (adres klienta, login).

CZEGO TEN LIMIT NIE ROBI. Za Traefikiem `request.client.host` to adres poda
ingressu - jeden i ten sam dla całego internetu, więc dopóki operator nie ustawi
TRUSTED_PROXY_CIDRS (patrz app/config.py i app/main.py:_client_ip), licznik jest
GLOBALNY, a nie per adres. To działa w obie strony: zgadywanie hasła spada do
MAX_ATTEMPTS na okno, ale ktokolwiek może utrzymywać ten limit wyczerpany i
właściciel nie wejdzie do panelu nawet z poprawnym hasłem (blokadę sprawdzamy
PRZED hasłem - i tak ma być, inaczej endpoint odpowiadałby inaczej na trafione
hasło i sam by je zdradzał). Zmierzone: 10 błędnych prób na login "admin", po
nich poprawne hasło dostaje 429.

Dlatego TRUSTED_PROXY_CIDRS jest właściwym ustawieniem produkcyjnym, a nie
ozdobnikiem - bez niego blokada per konto jest jednocześnie blokadą właściciela.
"""

import time
from collections import defaultdict

# Maksymalna liczba nieudanych prób w oknie, zanim /login zacznie odrzucać.
MAX_ATTEMPTS = 10
WINDOW_SECONDS = 15 * 60

_failures: defaultdict[tuple[str, str], list[float]] = defaultdict(list)

# Ile kluczy wolno trzymać, zanim wymusimy przegląd całego słownika. Klucz
# zawiera LOGIN, czyli wartość podaną przez tego, kto się dobija - a
# `_recent()` czyści tylko ten klucz, którego akurat dotyka. Nikt nie wraca do
# wymyślonego raz losowego loginu, więc bez zamiatania całości nic nigdy nie
# znikało: zmierzone 300 prób z losowym loginem = 300 kluczy w pamięci, zero
# usuniętych. Przy limicie 512Mi na pod to jest droga do OOMKill z samego
# /login, bez uwierzytelnienia i bez trafienia w próg blokady (każda próba
# zakłada nowy klucz, więc żaden nie dobija MAX_ATTEMPTS).
MAX_TRACKED_KEYS = 10_000


def _sweep(now: float) -> None:
    """
    Sprowadza słownik z powrotem pod MAX_TRACKED_KEYS.

    Krok 1 - kasujemy klucze bez ani jednego świeżego wpisu.

    Krok 2 - jeśli to nie wystarczy, wyrzucamy NAJSTARSZE. Samo czyszczenie
    przeterminowanych nie wystarcza, bo klucze da się zakładać szybciej, niż
    mija WINDOW_SECONDS: 200 próśb z losowym loginem to 200 kluczy, wszystkie
    świeże, żaden do skasowania. Dopiero twarde odcięcie ogranicza pamięć.

    Krok 2 OMIJA KLUCZE, KTÓRE SĄ AKTUALNIE ZABLOKOWANE - inaczej samo
    wyrzucanie byłoby obejściem blokady: wystarczyłoby zalać licznik losowymi
    loginami, żeby wypchnąć z niego własny, dobity do progu wpis i zacząć
    zgadywanie od zera. Klucz zablokowany kosztuje MAX_ATTEMPTS prób i i tak
    znika po WINDOW_SECONDS, więc ich liczba jest ograniczona tempem żądań.
    """
    for key in [k for k, stamps in _failures.items() if all(now - ts >= WINDOW_SECONDS for ts in stamps)]:
        _failures.pop(key, None)

    if len(_failures) <= MAX_TRACKED_KEYS:
        return

    evictable = [
        (max(stamps), key)
        for key, stamps in _failures.items()
        if len([ts for ts in stamps if now - ts < WINDOW_SECONDS]) < MAX_ATTEMPTS
    ]
    evictable.sort()
    for _, key in evictable[: len(_failures) - MAX_TRACKED_KEYS]:
        _failures.pop(key, None)


def _recent(key: tuple[str, str], now: float) -> list[float]:
    fresh = [ts for ts in _failures[key] if now - ts < WINDOW_SECONDS]
    if fresh:
        _failures[key] = fresh
    else:
        _failures.pop(key, None)
    return fresh


def is_blocked(client_ip: str, username: str) -> bool:
    now = time.time()
    return len(_recent((client_ip, username), now)) >= MAX_ATTEMPTS


def register_failure(client_ip: str, username: str) -> None:
    now = time.time()
    if len(_failures) >= MAX_TRACKED_KEYS:
        _sweep(now)
    key = (client_ip, username)
    _recent(key, now)
    _failures[key].append(now)


def reset(client_ip: str, username: str) -> None:
    """Udane logowanie zeruje licznik dla tej pary."""
    _failures.pop((client_ip, username), None)
