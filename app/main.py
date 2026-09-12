import logging
import secrets
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, status, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from .templates import templates
from . import login_guard, sessions
from .config import settings
from .db import init_db
from .routers import actions, api, dashboard, garden, settings as settings_router
from .scheduler import create_scheduler

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger("ogrodnik.auth")

STATIC_DIR = Path(__file__).resolve().parent / "static"

# Schemat OpenAPI wyłączony: /docs, /redoc i /openapi.json są w FastAPI dostępne
# BEZ żadnej zależności z uwierzytelnianiem - `dependencies=[Depends(...)]`
# podpinamy do routerów, a te trzy trasy rejestruje sam framework. Na
# ogrodnik.renacode.com anonimowy GET /openapi.json zwracał 200 z pełną mapą
# aplikacji (nazwy pól formularza ustawień, /plants/identify, /api/*) - czyli
# gotową instrukcję dla kogoś, kto zgadnie hasło albo szuka celu do CSRF.
app = FastAPI(
    title="Ogrodnik AI - POC",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


def _client_ip(request: Request) -> str:
    """
    Adres klienta używany jako część klucza w login_guard.

    Za Traefikiem gniazdo TCP przychodzi z poda ingressu, więc
    `request.client.host` jest dla WSZYSTKICH klientów z internetu tą samą
    wartością. Uvicorn ma wprawdzie ProxyHeadersMiddleware włączony domyślnie,
    ale ufa nagłówkom X-Forwarded-* tylko wtedy, gdy drugi koniec połączenia
    jest na liście `forwarded_allow_ips` (domyślnie: sam 127.0.0.1) - pod
    Traefika na niej nie jest, więc nagłówek jest ignorowany.

    Dlatego czytamy X-Forwarded-For sami, ale WYŁĄCZNIE gdy operator jawnie
    wskaże sieć proxy w TRUSTED_PROXY_CIDRS. Bezwarunkowe zaufanie temu
    nagłówkowi byłoby gorsze niż brak limitu: każdy mógłby dopisać losowy adres
    i dostawać świeży licznik do każdej próby hasła.
    """
    peer = request.client.host if request.client else None
    if peer is None:
        return "unknown"
    if not settings.trusted_proxy_networks or not _is_trusted_proxy(peer):
        return peer
    forwarded = request.headers.get("x-forwarded-for", "")
    # Bierzemy ostatni wpis spoza zaufanych sieci - wcześniejsze może dopisać
    # sam klient, ten dopisuje nasze proxy. Wpisy, które nie są adresem IP,
    # POMIJAMY zamiast zwracać: klient może wpisać w ten nagłówek dowolny tekst,
    # a gdyby taki tekst stawał się kluczem licznika, wybierałby sobie kubełek.
    for candidate in reversed([h.strip() for h in forwarded.split(",") if h.strip()]):
        if not _parse_ip(candidate):
            continue
        if not _is_trusted_proxy(candidate):
            return candidate
    return peer


def _parse_ip(address: str):
    import ipaddress

    try:
        return ipaddress.ip_address(address)
    except ValueError:
        return None


def _is_trusted_proxy(address: str) -> bool:
    ip = _parse_ip(address)
    if ip is None:
        return False
    return any(ip in net for net in settings.trusted_proxy_networks)


def authenticate(request: Request):
    username = sessions.resolve_session(request.cookies.get(sessions.COOKIE_NAME))
    if username is None:
        if request.url.path.startswith("/api"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Brak autoryzacji"
            )
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": "/login"}
        )
    return username

# Custom exception handler to process redirect exceptions smoothly
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code in (301, 302, 303, 307):
        return RedirectResponse(url=exc.headers.get("Location"), status_code=exc.status_code)
    from fastapi.exception_handlers import http_exception_handler as default_handler
    return await default_handler(request, exc)

# Authentication endpoints
@app.get("/login", response_class=HTMLResponse)
def login_get(request: Request):
    if sessions.resolve_session(request.cookies.get(sessions.COOKIE_NAME)):
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app.post("/login")
def login_post(request: Request, username: str = Form(...), password: str = Form(...)):
    client_ip = _client_ip(request)

    if login_guard.is_blocked(client_ip, username):
        logger.warning("Zbyt wiele nieudanych prób logowania z %s (login: %s)", client_ip, username)
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Zbyt wiele nieudanych prób. Spróbuj ponownie za kilkanaście minut."},
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    correct_username = secrets.compare_digest(username, settings.admin_username)
    correct_password = secrets.compare_digest(password, settings.admin_password)

    if correct_username and correct_password:
        login_guard.reset(client_ip, username)
        token, max_age = sessions.create_session(settings.admin_username)
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(
            key=sessions.COOKIE_NAME,
            value=token,
            httponly=True,
            max_age=max_age,
            samesite="lax",
            secure=True
        )
        return response

    login_guard.register_failure(client_ip, username)
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": "Niepoprawny login lub hasło"}
    )

@app.get("/logout")
def logout(request: Request):
    # Kasujemy sesję po stronie serwera - samo delete_cookie usuwa ciasteczko
    # tylko w tej przeglądarce, a skopiowana wartość działałaby dalej.
    sessions.destroy_session(request.cookies.get(sessions.COOKIE_NAME))
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(sessions.COOKIE_NAME)
    return response

app.include_router(dashboard.router, dependencies=[Depends(authenticate)])
app.include_router(actions.router, dependencies=[Depends(authenticate)])
app.include_router(api.router, dependencies=[Depends(authenticate)])
app.include_router(garden.router, dependencies=[Depends(authenticate)])
app.include_router(settings_router.router, dependencies=[Depends(authenticate)])

# Zdjęcia akcji ogrodowych i mapy działki - ZA LOGOWANIEM.
#
# Wcześniej stało tu `app.mount("/photos", StaticFiles(...))`. `app.mount` nie
# ma nic wspólnego z `dependencies=[Depends(authenticate)]` przy routerach -
# montuje osobną aplikację ASGI, do której zależności routerów się nie stosują.
# Efekt sprawdzony na produkcji: GET https://ogrodnik.renacode.com/photos/... i
# /maps/... odpowiadały bez ciasteczka sesji (404 prosto ze StaticFiles, nie 307
# na /login jak każda chroniona trasa). Nazwy plików to UUID4, więc nie dało się
# ich zgadnąć - ale adres zdjęcia wycieka wszędzie tam, gdzie wycieka adres URL:
# w nagłówku Referer, w historii przeglądarki, w logach proxy, w zrzucie ekranu.
# To był sekret przez nieodgadywalność, nie kontrola dostępu.
#
# Drugi powód: rozszerzenie pliku bierze się z nazwy nadanej przez wysyłającego
# (routers/actions.py, routers/garden.py), a StaticFiles dobiera Content-Type po
# rozszerzeniu. Plik ".html" w tym katalogu serwowałby się jako text/html
# z originu aplikacji.
# Typ zawartości bierzemy z BIAŁEJ LISTY rozszerzeń, a nie z mimetypes.guess().
# Rozszerzenie pochodzi z nazwy nadanej przez wysyłającego (routers/actions.py,
# routers/garden.py biorą `Path(photo.filename).suffix`), więc zgadywanie typu
# pozwalałoby podać plik ".html" jako text/html z originu aplikacji. Nie na
# liście = 404, choćby plik leżał na dysku.
_IMAGE_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".heic": "image/heic",
}


def _serve_media(directory, filename: str) -> FileResponse:
    # Sama nazwa pliku, bez katalogów - odcina "..", "/" i ścieżki bezwzględne
    # zanim dotkniemy dysku.
    if filename in ("", ".", "..") or filename != Path(filename).name:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    media_type = _IMAGE_TYPES.get(Path(filename).suffix.lower())
    if media_type is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    path = directory / filename
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    return FileResponse(path, media_type=media_type, headers={"X-Content-Type-Options": "nosniff"})


@app.get("/photos/{filename}", dependencies=[Depends(authenticate)])
def photo(filename: str):
    return _serve_media(settings.photos_dir, filename)


@app.get("/maps/{filename}", dependencies=[Depends(authenticate)])
def map_image(filename: str):
    return _serve_media(settings.maps_dir, filename)


# Zasoby wlasne (kroje pisma) - jedyny katalog serwowany BEZ logowania i tak ma
# byc: ekran logowania musi je wczytac, zanim ktokolwiek ma sesje. W przeciwienstwie
# do /photos i /maps nic tu nie trafia od uzytkownika - zawartosc pochodzi
# z obrazu (COPY app ./app w docker/app.Dockerfile).
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

scheduler = create_scheduler()


@app.on_event("startup")
async def on_startup():
    init_db()
    scheduler.start()


@app.on_event("shutdown")
async def on_shutdown():
    scheduler.shutdown()


@app.get("/health")
def health():
    """Prosty endpoint dla Docker HEALTHCHECK / load balancera."""
    return {"status": "ok"}
