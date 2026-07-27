from datetime import datetime, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlmodel import select

from ..analysis import get_latest_insight
from ..db import get_session
from ..models import GardenAction, MowingEvent, WateringEvent
from ..templates import templates

router = APIRouter(tags=["dashboard"])


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    since = datetime.utcnow() - timedelta(days=14)
    with get_session() as session:
        watering_count = len(
            session.exec(select(WateringEvent).where(WateringEvent.start_time >= since)).all()
        )
        mowing_count = len(
            session.exec(select(MowingEvent).where(MowingEvent.start_time >= since)).all()
        )
        recent_actions = session.exec(
            select(GardenAction).order_by(GardenAction.timestamp.desc()).limit(10)
        ).all()

    # Najnowszy wniosek AI z bazy - generowany automatycznie w tle (scheduler,
    # raz na 24h) albo ręcznie. Dashboard pokazuje go domyślnie, bez czekania
    # na kliknięcie - "na żądanie" jest tylko opcją wymuszenia odświeżenia.
    latest_insight = get_latest_insight()

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "watering_count": watering_count,
            "mowing_count": mowing_count,
            "recent_actions": recent_actions,
            "latest_insight": latest_insight,
        },
    )
