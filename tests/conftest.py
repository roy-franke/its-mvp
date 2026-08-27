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
os.environ["ITS_DB_PATH"] = os.path.join(tempfile.gettempdir(), "its_test.db")

_lessons_tmp = Path(tempfile.mkdtemp(prefix="its_lessons_"))
_default = Path(__file__).resolve().parent.parent / "app" / "lessons" / "haftungsrecht.json"
shutil.copy(_default, _lessons_tmp / _default.name)
os.environ["ITS_LESSONS_DIR"] = str(_lessons_tmp)
