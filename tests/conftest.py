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
