import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlmodel import select

from ..config import settings
from ..db import get_session
from ..integrations.gemini import GeminiClient
from ..models import GardenMapImage, Plant
from ..templates import templates

router = APIRouter(tags=["garden"])


def _latest_map_image() -> Optional[GardenMapImage]:
    with get_session() as session:
        return session.exec(select(GardenMapImage).order_by(GardenMapImage.uploaded_at.desc())).first()


@router.get("/garden", response_class=HTMLResponse)
def garden_page(request: Request):
    with get_session() as session:
        plants = session.exec(select(Plant).order_by(Plant.created_at.desc())).all()
    map_image = _latest_map_image()
    return templates.TemplateResponse(
        "garden.html",
        {
            "request": request,
            "plants": plants,
            "map_image_path": map_image.image_path if map_image else None,
        },
    )


@router.post("/garden/map-image")
async def upload_map_image(photo: UploadFile):
    suffix = Path(photo.filename or "map.jpg").suffix or ".jpg"
    filename = f"{uuid.uuid4().hex}{suffix}"
    dest = settings.maps_dir / filename
    dest.write_bytes(await photo.read())

    with get_session() as session:
        session.add(GardenMapImage(image_path=filename))
        session.commit()

    return RedirectResponse(url="/garden", status_code=303)


@router.post("/plants")
async def create_plant(
    name: str = Form(...),
    scientific_name: str = Form(""),
    notes: str = Form(""),
    zone: str = Form(""),
    x_pct: str = Form(""),
    y_pct: str = Form(""),
    added_via: str = Form("manual"),
    photo: Optional[UploadFile] = None,
):
    photo_path = None
    if photo is not None and photo.filename:
        suffix = Path(photo.filename).suffix or ".jpg"
        filename = f"{uuid.uuid4().hex}{suffix}"
        dest = settings.photos_dir / filename
        dest.write_bytes(await photo.read())
        photo_path = filename

    with get_session() as session:
        session.add(
            Plant(
                name=name,
                scientific_name=scientific_name or None,
                notes=notes or None,
                zone=zone or None,
                photo_path=photo_path,
                x_pct=float(x_pct) if x_pct else None,
                y_pct=float(y_pct) if y_pct else None,
                added_via=added_via if added_via in ("manual", "ai") else "manual",
            )
        )
        session.commit()

    return RedirectResponse(url="/garden", status_code=303)


@router.post("/plants/{plant_id}/delete")
def delete_plant(plant_id: int):
    with get_session() as session:
        plant = session.get(Plant, plant_id)
        if plant:
            session.delete(plant)
            session.commit()
    return RedirectResponse(url="/garden", status_code=303)


@router.post("/plants/identify")
async def identify_plants(photo: UploadFile):
    """
    Wysyła zdjęcie do Gemini AI i zwraca listę rozpoznanych roślin (JSON,
    używane przez fetch() w garden.html). Nie zapisuje nic do bazy - to tylko
    sugestie, które użytkownik świadomo umieszcza na mapie (klik + "Dodaj").
    """
    client = GeminiClient()
    if not client.configured:
        return JSONResponse(
            {"error": "GEMINI_API_KEY nie jest ustawiony - dodaj go w Ustawieniach."},
            status_code=400,
        )

    image_bytes = await photo.read()
    mime_type = photo.content_type or "image/jpeg"
    try:
        suggestions = await client.identify_plants(image_bytes, mime_type=mime_type)
        return {"suggestions": suggestions}
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": f"Błąd Gemini API: {exc}"}, status_code=502)
