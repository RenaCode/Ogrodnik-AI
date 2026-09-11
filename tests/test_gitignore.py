"""
BŁĄD 3: repo nie miało .gitignore.

app/config.py tworzy katalog data/ przy starcie, a w bazie SQLite (tabela
AppSetting) leżą czystym tekstem token Home Assistanta i klucze API. Bez
.gitignore jedno "git add -A" wciągało tę bazę do historii i na push - plik .env
chronił wyłącznie prywatny ~/.gitignore_global właściciela, którego nie ma ani
na świeżym klonie, ani w CI.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git niedostępny")


@pytest.mark.parametrize(
    "sciezka",
    [
        "data/ogrodnik.db",
        "data/photos/zdjecie.jpg",
        ".env",
        "app/__pycache__/main.cpython-312.pyc",
        ".venv/bin/python",
        ".DS_Store",
    ],
)
def test_wrazliwe_sciezki_sa_ignorowane(sciezka):
    result = subprocess.run(
        # core.excludesFile=/dev/null wyłącza prywatny ~/.gitignore_global -
        # chodzi o to, żeby test przechodził dzięki plikowi w repo, tak jak na
        # świeżym klonie i w CI. --no-index: pytamy o samą regułę, niezależnie
        # od tego, czy plik akurat istnieje.
        ["git", "-c", "core.excludesFile=/dev/null",
         "check-ignore", "--no-index", "-q", sciezka],
        cwd=ROOT,
        capture_output=True,
    )
    assert result.returncode == 0, f"{sciezka} nie jest ignorowane"


def test_repo_ma_wlasny_gitignore():
    """Reguły muszą być w repo, a nie w prywatnym ~/.gitignore_global."""
    tresc = (ROOT / ".gitignore").read_text()
    for wzorzec in ("data/", ".env", "*.db", "__pycache__/", ".venv/", ".DS_Store"):
        assert wzorzec in tresc, f"brak wzorca {wzorzec} w .gitignore"
