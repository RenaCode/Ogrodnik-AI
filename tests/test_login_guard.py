"""
Co licznik nieudanych logowań robi, a czego nie robi.

Punkt wyjścia audytu brzmiał: czy jest tu ten sam błąd, co w Dietetyku, gdzie
licznik blokady był kluczowany wartością zmieniającą się przy każdej próbie,
więc nigdy nie dobijał progu. NIE MA GO - przy zgadywaniu hasła login jest
stały ("admin"), więc klucz jest stały i próg zostaje osiągnięty
(test_licznik_dobija_progu).

Są za to dwie inne rzeczy, obie potwierdzone pomiarem:

1. Licznik jest kluczowany adresem klienta, a za odwrotnym proxy ten adres jest
   jeden dla całego internetu - razem z właścicielem. Dopóki operator nie ustawi
   TRUSTED_PROXY_CIDRS, ktokolwiek może trzymać panel zamknięty przed
   właścicielem samymi błędnymi hasłami (test_wspolny_licznik_odcina_wlasciciela).
2. Słownik licznika rósł bez ograniczeń, bo klucz zawiera login podany przez
   pytającego, a sprzątanie dotykało tylko klucza akurat używanego. Zmierzone
   przed poprawką: 300 prób z losowym loginem = 300 kluczy, zero usuniętych.
"""

import secrets
import time

import pytest

from app import login_guard


@pytest.fixture(autouse=True)
def _reset_cap():
    oryginalny = login_guard.MAX_TRACKED_KEYS
    yield
    login_guard.MAX_TRACKED_KEYS = oryginalny
    login_guard._failures.clear()


def test_licznik_dobija_progu():
    """Błąd z Dietetyka: klucz zmieniał się co próbę, więc próg był nieosiągalny."""
    for _ in range(login_guard.MAX_ATTEMPTS):
        assert not login_guard.is_blocked("1.2.3.4", "admin")
        login_guard.register_failure("1.2.3.4", "admin")
    assert login_guard.is_blocked("1.2.3.4", "admin")


def test_blokada_jest_per_adres_i_login():
    for _ in range(login_guard.MAX_ATTEMPTS):
        login_guard.register_failure("1.2.3.4", "admin")
    assert login_guard.is_blocked("1.2.3.4", "admin")
    assert not login_guard.is_blocked("5.6.7.8", "admin")
    assert not login_guard.is_blocked("1.2.3.4", "ktos-inny")


def test_wspolny_licznik_odcina_wlasciciela():
    """
    UDOKUMENTOWANE ZACHOWANIE, NIE ŻYCZENIE. Gdy wszyscy dzielą jeden adres
    (tak jest za Traefikiem bez TRUSTED_PROXY_CIDRS), próby napastnika blokują
    właściciela. Test stoi tutaj po to, żeby ta cena była widoczna w kodzie, a
    nie odkrywana na produkcji.
    """
    adres_poda_ingressu = "10.42.0.7"
    for _ in range(login_guard.MAX_ATTEMPTS):
        login_guard.register_failure(adres_poda_ingressu, "admin")
    assert login_guard.is_blocked(adres_poda_ingressu, "admin")


def test_slownik_nie_rosnie_bez_ograniczen():
    login_guard.MAX_TRACKED_KEYS = 100
    for _ in range(3000):
        login_guard.register_failure("10.42.0.7", secrets.token_hex(4))
    assert len(login_guard._failures) <= login_guard.MAX_TRACKED_KEYS + 1


def test_zalew_losowymi_loginami_nie_kasuje_istniejacej_blokady():
    """
    Wyrzucanie najstarszych kluczy nie może być obejściem blokady: inaczej
    wystarczyłoby zalać licznik losowymi loginami, żeby wypchnąć z niego własny
    dobity wpis i zacząć zgadywanie od zera.
    """
    login_guard.MAX_TRACKED_KEYS = 100
    for _ in range(login_guard.MAX_ATTEMPTS):
        login_guard.register_failure("10.42.0.7", "admin")
    assert login_guard.is_blocked("10.42.0.7", "admin")

    for _ in range(3000):
        login_guard.register_failure("10.42.0.7", secrets.token_hex(4))

    assert login_guard.is_blocked("10.42.0.7", "admin")


def test_przeterminowane_wpisy_znikaja_przy_zamiataniu():
    """
    Zamiatanie całości uruchamia się dopiero po przekroczeniu MAX_TRACKED_KEYS -
    do tego progu przeterminowane klucze po prostu leżą, bo pamięć i tak jest
    ograniczona, a przeglądanie słownika przy każdej próbie byłoby pracą na
    darmo. Test ustawia niski próg, żeby sprawdzić samo zamiatanie.
    """
    login_guard.MAX_TRACKED_KEYS = 10
    stary = time.time() - login_guard.WINDOW_SECONDS - 1
    for i in range(50):
        login_guard._failures[("10.42.0.7", f"stary{i}")] = [stary]
    login_guard.register_failure("10.42.0.7", "swiezy")
    assert len(login_guard._failures) == 1


def test_przeterminowany_wpis_nie_blokuje():
    """Niezależnie od zamiatania: wpis starszy niż okno nie liczy się do progu."""
    stary = time.time() - login_guard.WINDOW_SECONDS - 1
    login_guard._failures[("1.2.3.4", "admin")] = [stary] * (login_guard.MAX_ATTEMPTS * 2)
    assert not login_guard.is_blocked("1.2.3.4", "admin")


def test_udane_logowanie_zeruje_licznik():
    for _ in range(login_guard.MAX_ATTEMPTS - 1):
        login_guard.register_failure("1.2.3.4", "admin")
    login_guard.reset("1.2.3.4", "admin")
    assert not login_guard.is_blocked("1.2.3.4", "admin")
    assert ("1.2.3.4", "admin") not in login_guard._failures
