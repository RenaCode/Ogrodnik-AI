"""
BŁĄD 4: chart wstawiał do poda sidecar coleifer/sqlite-web bez hasła.

Kontener nasłuchiwał na porcie 8080 z zamontowanym PVC, więc dowolny inny pod w
klastrze mógł czytać i nadpisywać tabelę appsetting (token Home Assistanta,
klucze Gemini/Hydrawise) z pominięciem logowania. W docker-compose.yml ten sam
port jest przypięty do 127.0.0.1 - chart tę ochronę gubił.
"""

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

CHART = Path(__file__).resolve().parent.parent / "charts" / "ogrodnik"

pytestmark = pytest.mark.skipif(shutil.which("helm") is None, reason="helm niedostępny")


def _render(*set_args: str) -> list[dict]:
    cmd = ["helm", "template", "test-release", str(CHART)]
    for arg in set_args:
        cmd += ["--set", arg]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def _containers(docs: list[dict]) -> list[dict]:
    for doc in docs:
        if doc.get("kind") == "Deployment":
            return doc["spec"]["template"]["spec"]["containers"]
    pytest.fail("chart nie wyrenderował Deploymentu")


def test_sidecar_sqlite_web_jest_domyslnie_wylaczony():
    names = [c["name"] for c in _containers(_render())]
    assert names == ["ogrodnik-ai"], (
        "sqlite-web bez uwierzytelniania trafia do poda przy domyślnych values.yaml"
    )


def test_sidecar_da_sie_wlaczyc_swiadomie():
    names = [c["name"] for c in _containers(_render("dbWeb.enabled=true"))]
    assert "ogrodnik-db" in names


def test_obraz_sidecara_jest_przypiety():
    containers = _containers(_render("dbWeb.enabled=true"))
    image = next(c["image"] for c in containers if c["name"] == "ogrodnik-db")
    assert not image.endswith(":latest"), "obraz sidecara nie jest przypięty"
    assert "@sha256:" in image, f"oczekiwano przypięcia po digeście, jest: {image}"


def test_values_maja_wylaczony_dbweb():
    values = yaml.safe_load((CHART / "values.yaml").read_text())
    assert values["dbWeb"]["enabled"] is False
