"""Test-Setup: Mock-Provider, Temp-DB und Temp-Lektionenordner.

Läuft vor dem Import der Testmodule, damit app.main mit Testpfaden startet.
"""

import os
import shutil
import tempfile
from pathlib import Path

os.environ["LLM_PROVIDER"] = "mock"
# Zugangsschutz in Tests standardmässig aus – eine lokale .env (load_dotenv
# überschreibt gesetzte Variablen nicht) darf die Tests nicht beeinflussen.
os.environ["TEACHER_PASSWORD"] = ""
os.environ["CLASS_CODE"] = ""
# Frische Datenbank pro Testlauf: Seit T-05 gibt es pro Person und Lektion
# nur eine offene Sequenz, Reste eines früheren Laufs würden stören.
_db_tmp = Path(tempfile.mkdtemp(prefix="its_db_"))
os.environ["ITS_DB_PATH"] = str(_db_tmp / "its_test.db")

_lessons_tmp = Path(tempfile.mkdtemp(prefix="its_lessons_"))
_default = Path(__file__).resolve().parent.parent / "app" / "lessons" / "haftungsrecht.json"
shutil.copy(_default, _lessons_tmp / _default.name)
os.environ["ITS_LESSONS_DIR"] = str(_lessons_tmp)
# L-01: Ablage der Lernmaterialien und T-29: keine Vektordatenbank, ausser ein
# Test richtet eine ein
os.environ["ITS_MATERIAL_DIR"] = str(Path(tempfile.mkdtemp(prefix="its_material_")))
os.environ["ITS_VEKTOR_DB_URL"] = ""


import json  # noqa: E402

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _neue_lektionen_archivieren():
    """Von einem Test angelegte Lektionen danach archivieren.

    Sonst ändert sich die Standardlektion (die erste in alphabetischer
    Reihenfolge) für die folgenden Tests, etwa durch «duplikat-…».
    """
    vorher = {p.name for p in _lessons_tmp.glob("*.json")}
    yield
    for p in _lessons_tmp.glob("*.json"):
        if p.name not in vorher:
            data = json.loads(p.read_text(encoding="utf-8"))
            data["archiviert"] = True
            p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
