"""
Sesje logowania trzymane po stronie serwera.

Wcześniej ciasteczko sesyjne było zwykłym HMAC-em z hasła admina i nazwy
użytkownika - czyli JEDNĄ stałą wartością: identyczną przy każdym logowaniu, bez
terminu ważności i nie do unieważnienia (`delete_cookie` kasuje ciasteczko tylko
w przeglądarce, skopiowana wartość działała dalej aż do zmiany hasła).

Teraz przy logowaniu losujemy nieprzewidywalny identyfikator sesji, a jego HMAC
zapisujemy w bazie (tabela SessionToken). Wylogowanie kasuje wiersz, więc token
naprawdę przestaje działać; wiersz ma też datę wygaśnięcia.

Gdzie trzymamy sesje i dlaczego: w bazie SQLite na PVC, nie w pamięci procesu.
Pod na k3s restartuje się przy każdym wdrożeniu (115 ReplicaSetów w ~2,5
miesiąca), więc sesje w pamięci znikałyby po każdym deployu i wylogowywały
użytkownika. Zapis w bazie przeżywa rollout, a przy jednej replice (replicaCount
= 1) SQLite w zupełności wystarcza.

W bazie NIE leży surowy token, tylko HMAC-SHA256 z niego liczony SECRET_KEY-em.
Sidecar sqlite-web ma tę samą bazę pod ręką - bez znajomości klucza nie odtworzy
z tabeli działającego ciasteczka ani nie dopisze własnego wiersza pasującego do
tokenu, który sam sobie wymyślił.
"""

import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional

from sqlmodel import select

from .config import settings
from .db import get_session
from .models import SessionToken

logger = logging.getLogger("ogrodnik.sessions")

COOKIE_NAME = "session_token"

# Po tylu dniach sesja wygasa niezależnie od aktywności - tyle samo, ile żyło
# ciasteczko (max_age) w poprzedniej wersji.
SESSION_TTL = timedelta(days=7)


def _hash_token(token: str) -> str:
    return hmac.new(
        settings.secret_key.encode(), token.encode(), hashlib.sha256
    ).hexdigest()


def create_session(username: str) -> tuple[str, int]:
    """Zakłada nową sesję. Zwraca (surowy token do ciasteczka, max_age w sekundach)."""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + SESSION_TTL
    with get_session() as session:
        session.add(
            SessionToken(
                token_hash=_hash_token(token),
                username=username,
                expires_at=expires_at,
            )
        )
        session.commit()
    purge_expired()
    return token, int(SESSION_TTL.total_seconds())


def resolve_session(token: Optional[str]) -> Optional[str]:
    """Zwraca nazwę użytkownika dla ważnej sesji albo None."""
    if not token:
        return None
    with get_session() as session:
        row = session.get(SessionToken, _hash_token(token))
        if row is None:
            return None
        if row.expires_at <= datetime.utcnow():
            # Sesja przeterminowana - kasujemy przy okazji, żeby nie zostawała
            # w tabeli do najbliższego purge_expired().
            session.delete(row)
            session.commit()
            return None
        return row.username


def destroy_session(token: Optional[str]) -> None:
    """Unieważnia sesję po stronie serwera (wylogowanie)."""
    if not token:
        return
    with get_session() as session:
        row = session.get(SessionToken, _hash_token(token))
        if row is not None:
            session.delete(row)
            session.commit()


def purge_expired() -> None:
    """Sprząta wygasłe wiersze, żeby tabela nie rosła w nieskończoność."""
    with get_session() as session:
        stale = session.exec(
            select(SessionToken).where(SessionToken.expires_at <= datetime.utcnow())
        ).all()
        for row in stale:
            session.delete(row)
        if stale:
            session.commit()
            logger.info("Usunięto %d wygasłych sesji", len(stale))
