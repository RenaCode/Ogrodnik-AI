import logging
import secrets
import hmac
import hashlib
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, status, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from .templates import templates
from . import login_guard, sessions
from .config import settings
from .db import init_db
from .routers import actions, api, dashboard, garden, settings as settings_router
from .scheduler import create_scheduler

logging.basicConfig(level=logging.INFO)

scheduler = create_scheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    scheduler.start()
    yield
    scheduler.shutdown()

app = FastAPI(title="Ogrodnik AI - POC", lifespan=lifespan)
templates = Jinja2Templates(directory="app/templates")


def sign_session(username: str) -> str:
    expires_at = int(time.time()) + (7 * 24 * 60 * 60)  # 7 days
    nonce = secrets.token_hex(16)
    payload = f"{username}:{expires_at}:{nonce}"
    signature = hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{signature}"

def verify_session(cookie_value: str) -> bool:
    try:
        parts = cookie_value.split(":")
        if len(parts) != 4:
            return False
        username, expires_at_str, nonce, signature = parts
        
        # Verify expiration
        if time.time() > int(expires_at_str):
            return False
            
        # Verify signature
        payload = f"{username}:{expires_at_str}:{nonce}"
        expected = hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if hmac.compare_digest(signature, expected) and username == settings.admin_username:
            return True
    except Exception:
        pass
    return False

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

app.mount("/photos", StaticFiles(directory=str(settings.photos_dir)), name="photos")
app.mount("/maps", StaticFiles(directory=str(settings.maps_dir)), name="maps")

# scheduler and lifecycle events are now managed via lifespan on app initialization


@app.get("/health")
def health():
    """Prosty endpoint dla Docker HEALTHCHECK / load balancera."""
    return {"status": "ok"}
