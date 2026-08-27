"""Zugangsschutz für den Klassentest.

Zwei Mechanismen, beide über die .env konfiguriert:

- TEACHER_PASSWORD: Passwort für die Lehrpersonen-Sicht (/teacher).
  Leer = Schutz deaktiviert (nur für lokale Entwicklung gedacht).
  Beim Login wird ein signiertes Cookie gesetzt; der Signaturschlüssel wird
  einmalig erzeugt und in der DB abgelegt. Das Token bindet einen Hash des
  Passworts ein – ändert die Lehrperson das Passwort, sind alte Logins ungültig.

- CLASS_CODE: Zugangscode für Lernende. Leer = kein Code nötig.
  Wird beim Session-Start geprüft (Gross-/Kleinschreibung egal).

Bewusst schlank gehalten: kein Benutzerverzeichnis, keine Rollen – das genügt
für den Pilotbetrieb mit einer Klasse und bleibt nachvollziehbar.
"""

import hashlib
import hmac
import os
import secrets

from fastapi import HTTPException, Request

from . import store

COOKIE_NAME = "its_teacher"
COOKIE_MAX_AGE = 12 * 3600   # 12 Stunden – reicht für einen Unterrichtstag


def teacher_password() -> str:
    return (os.getenv("TEACHER_PASSWORD") or "").strip()


def class_code() -> str:
    return (os.getenv("CLASS_CODE") or "").strip()


def auth_enabled() -> bool:
    return bool(teacher_password())


def _secret() -> bytes:
    s = store.get_config("auth_secret")
    if not s:
        s = secrets.token_hex(32)
        store.set_config("auth_secret", s)
    return s.encode()


def make_token() -> str:
    pw_hash = hashlib.sha256(teacher_password().encode()).hexdigest()
    return hmac.new(_secret(), f"teacher:{pw_hash}".encode(), hashlib.sha256).hexdigest()


def is_teacher(request: Request) -> bool:
    if not auth_enabled():
        return True
    token = request.cookies.get(COOKIE_NAME, "")
    return bool(token) and hmac.compare_digest(token, make_token())


def require_teacher(request: Request):
    """FastAPI-Dependency: schützt Teacher-Endpoints."""
    if not is_teacher(request):
        raise HTTPException(401, "Login erforderlich")


def check_password(password: str | None) -> bool:
    return hmac.compare_digest((password or "").strip(), teacher_password())


def check_class_code(code: str | None) -> bool:
    needed = class_code()
    if not needed:
        return True
    return (code or "").strip().lower() == needed.lower()
