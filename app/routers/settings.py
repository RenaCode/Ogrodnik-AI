from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .. import runtime_settings as rs
from ..templates import templates

router = APIRouter(prefix="/settings", tags=["settings"])


def _fields_for_form() -> list[dict]:
    """
    Buduje listę pól do formularza. Dla pól typu "password" (klucze API,
    tokeny) NIE wstawiamy zapisanej wartości do <input value=...> - tylko
    informację, że jest ustawiona. Zostaw pole puste, żeby zachować obecną
    wartość; wpisz nową, żeby ją zmienić.
    """
    fields = []
    for f in rs.OVERRIDABLE_FIELDS:
        current = rs.get_value(f["key"])
        fields.append(
            {
                **f,
                "value": "" if f["type"] == "password" else (current or ""),
                "configured": bool(current),
            }
        )
    return fields


@router.get("", response_class=HTMLResponse)
def settings_page(request: Request, saved: bool = False):
    return templates.TemplateResponse(
        "settings.html",
        {"request": request, "fields": _fields_for_form(), "saved": saved},
    )


@router.post("")
async def save_settings(request: Request):
    form = await request.form()
    # Puste pole = "nie zmieniaj" (ważne dla pól typu password, które nigdy nie
    # są pre-wypełniane zapisaną wartością w formularzu).
    values = {key: str(form.get(key, "")) for key in rs.OVERRIDABLE_KEYS}
    rs.set_all(values)
    return RedirectResponse(url="/settings?saved=1", status_code=303)
