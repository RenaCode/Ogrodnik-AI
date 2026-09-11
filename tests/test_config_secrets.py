"""
BŁĄD 1: hasło administratora miało w kodzie wartość domyślną.

Repo jest publiczne (MIT), więc domyślne hasło było znane każdemu, a żadna
dokumentacja nie skłaniała operatora do ustawienia ADMIN_PASSWORD. Sprawdzamy,
że pola nie mają już wartości domyślnych i że brak zmiennej zatrzymuje start z
czytelnym komunikatem, zamiast po cichu wpuścić kogokolwiek do "Ustawień".
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("field", ["admin_password", "secret_key"])
def test_sekret_nie_ma_wartosci_domyslnej(field):
    from app.config import Settings

    assert Settings.model_fields[field].is_required(), (
        f"{field.upper()} ma wartość domyślną - w publicznym repo oznacza to "
        f"sekret znany wszystkim"
    )


@pytest.mark.parametrize("missing", ["ADMIN_PASSWORD", "SECRET_KEY"])
def test_brak_zmiennej_zatrzymuje_start_z_komunikatem(missing):
    if (ROOT / ".env").exists():
        pytest.skip("lokalny .env mógłby dostarczyć brakującą zmienną")

    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(ROOT),
        "ADMIN_PASSWORD": "x",
        "SECRET_KEY": "y",
    }
    del env[missing]

    result = subprocess.run(
        [sys.executable, "-c", "import app.config"],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0, "aplikacja wystartowała mimo braku sekretu"
    assert missing in result.stderr, result.stderr
    # Komunikat ma mówić, co ustawić, a nie tylko że coś jest nie tak.
    assert ".env" in result.stderr
