"""Rollen, Anmeldung und Zugangsschutz.

Es gibt zwei Rollen: «lernend» und «lehrperson». Die Rolle wird serverseitig
durchgesetzt; das Ausblenden von Elementen in der Oberfläche ist nur Komfort.

Identität und Rolle entstehen auf einem von zwei Wegen (Entscheid E2):

1. Anmeldung über Header eines vorgelagerten Proxys (ITS_TRUST_PROXY_HEADERS=true).
   Der Benutzername kommt aus ITS_USER_HEADER (Standard X-Forwarded-User),
   die Rollen aus ITS_ROLES_HEADER (Standard X-User-Roles). Enthält die
   Rollenliste ITS_TEACHER_ROLE (Standard teacher), gilt die Person als
   Lehrperson. Der Name ist dann fest und in der Oberfläche nicht änderbar.
   Achtung: Den Headern darf nur vertraut werden, wenn der Proxy gleichnamige
   Header aus eingehenden Anfragen entfernt und selbst setzt (siehe
   docs/DEPLOYMENT-CLOUDFLARE.md). Standard ist deshalb «aus».

2. Rückfall ohne Header (bisheriges Verfahren):
   - TEACHER_PASSWORD: Passwort für die Lehrpersonen-Sicht. Beim Login wird
     ein signiertes Cookie gesetzt; das Token bindet einen Hash des Passworts
     ein, ein Passwortwechsel macht alte Logins ungültig. Leer = Lehrpersonen-
     Seiten sind ohne Login offen (nur für lokale Entwicklung).
   - Lernende melden sich mit Name (Pseudonym) plus CLASS_CODE an, optional
     mit einer vierstelligen PIN (Entscheid E7). Der Name steckt signiert in
     einem Cookie; er ist die Grundlage für die Zuordnung der Lernsequenzen.

Ein gültiges Lehrpersonen-Cookie macht auch bei Header-Anmeldung zur
Lehrperson. So funktioniert zum Beispiel Cloudflare Access, das nur die
E-Mail-Adresse, aber keine Rollen liefert: Lehrpersonen melden sich
zusätzlich mit dem Passwort an.
"""

import base64
import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass

from fastapi import HTTPException, Request

from . import store

COOKIE_NAME = "its_teacher"
LEARNER_COOKIE = "its_learner"
COOKIE_MAX_AGE = 12 * 3600             # 12 Stunden – reicht für einen Unterrichtstag
LEARNER_COOKIE_MAX_AGE = 30 * 24 * 3600

LEHRPERSON = "lehrperson"
LERNEND = "lernend"


# ---------------------------------------------------------------- Konfiguration

def teacher_password() -> str:
    return (os.getenv("TEACHER_PASSWORD") or "").strip()


def class_code() -> str:
    return (os.getenv("CLASS_CODE") or "").strip()


def auth_enabled() -> bool:
    return bool(teacher_password())


def trust_headers() -> bool:
    return (os.getenv("ITS_TRUST_PROXY_HEADERS") or "false").strip().lower() in ("1", "true", "yes", "ja")


def user_header() -> str:
    return (os.getenv("ITS_USER_HEADER") or "X-Forwarded-User").strip()


def roles_header() -> str:
    return (os.getenv("ITS_ROLES_HEADER") or "X-User-Roles").strip()


def teacher_role() -> str:
    return (os.getenv("ITS_TEACHER_ROLE") or "teacher").strip().lower()


def normalize_user(name: str | None) -> str:
    """Schlüssel für den Vergleich von Namen: Gross-/Kleinschreibung und
    Leerzeichen am Rand spielen keine Rolle."""
    return (name or "").strip().casefold()


# ---------------------------------------------------------------- Signaturen

def _secret() -> bytes:
    s = store.get_config("auth_secret")
    if not s:
        s = secrets.token_hex(32)
        store.set_config("auth_secret", s)
    return s.encode()


def _sign(msg: str) -> str:
    return hmac.new(_secret(), msg.encode(), hashlib.sha256).hexdigest()


def make_token() -> str:
    pw_hash = hashlib.sha256(teacher_password().encode()).hexdigest()
    return _sign(f"teacher:{pw_hash}")


def _learner_msg(b: str) -> str:
    # Der Klassencode fliesst in die Signatur ein: Ändert die Lehrperson den
    # Code, müssen sich alle Lernenden neu anmelden.
    code_hash = hashlib.sha256(class_code().lower().encode()).hexdigest()[:16]
    return f"learner:{code_hash}:{b}"


def make_learner_token(name: str) -> str:
    b = base64.urlsafe_b64encode(name.strip().encode()).decode()
    return f"{b}.{_sign(_learner_msg(b))}"


def read_learner_token(token: str | None) -> str | None:
    if not token or "." not in token:
        return None
    b, sig = token.rsplit(".", 1)
    if not hmac.compare_digest(sig, _sign(_learner_msg(b))):
        return None
    try:
        return base64.urlsafe_b64decode(b.encode()).decode()
    except Exception:
        return None


# ---------------------------------------------------------------- Identität

@dataclass
class Identity:
    name: str | None = None
    rolle: str | None = None
    via: str | None = None          # "header" | "cookie" | None
    teacher_cookie: bool = False

    @property
    def key(self) -> str | None:
        return normalize_user(self.name) if self.name else None

    @property
    def is_teacher(self) -> bool:
        return self.rolle == LEHRPERSON


def has_teacher_cookie(request: Request) -> bool:
    token = request.cookies.get(COOKIE_NAME, "")
    return bool(token) and hmac.compare_digest(token, make_token())


def _header_identity(request: Request) -> tuple[str, set[str]] | None:
    if not trust_headers():
        return None
    name = (request.headers.get(user_header()) or "").strip()
    if not name:
        return None
    raw = request.headers.get(roles_header()) or ""
    roles = {r.strip().lower() for r in raw.replace(";", ",").replace(" ", ",").split(",") if r.strip()}
    return name, roles


def identity(request: Request) -> Identity:
    teacher_cookie = has_teacher_cookie(request)
    hdr = _header_identity(request)
    if hdr:
        name, roles = hdr
        rolle = LEHRPERSON if (teacher_role() in roles or teacher_cookie) else LERNEND
        return Identity(name=name, rolle=rolle, via="header", teacher_cookie=teacher_cookie)
    learner = read_learner_token(request.cookies.get(LEARNER_COOKIE))
    if teacher_cookie:
        return Identity(name=learner, rolle=LEHRPERSON, via="cookie", teacher_cookie=True)
    if learner:
        return Identity(name=learner, rolle=LERNEND, via="cookie")
    return Identity()


def is_teacher(request: Request) -> bool:
    """Zugang zu Lehrpersonen-Seiten und -Endpunkten."""
    ident = identity(request)
    if ident.via == "header":
        return ident.is_teacher          # Header entscheidet, auch ohne Passwort
    if not auth_enabled():
        return True                      # lokale Entwicklung ohne Passwort
    return ident.teacher_cookie


def require_teacher(request: Request):
    """FastAPI-Dependency für /api/teacher/…: 401 ohne Lehrpersonen-Login."""
    if not is_teacher(request):
        raise HTTPException(401, "Login als Lehrperson erforderlich")


def require_teacher_page(request: Request):
    """FastAPI-Dependency für /teacher/…: Weiterleitung auf den Login."""
    if not is_teacher(request):
        raise HTTPException(307, "Login erforderlich", headers={"Location": "/teacher/login"})


def check_password(password: str | None) -> bool:
    return hmac.compare_digest((password or "").strip(), teacher_password())


def check_class_code(code: str | None) -> bool:
    needed = class_code()
    if not needed:
        return True
    return (code or "").strip().lower() == needed.lower()


# ---------------------------------------------------------------- PIN (Entscheid E7)

def hash_pin(pin: str) -> str:
    salt = secrets.token_hex(8)
    h = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt.encode(), 100_000).hex()
    return f"{salt}${h}"


def verify_pin(pin: str, stored: str) -> bool:
    try:
        salt, h = stored.split("$", 1)
    except ValueError:
        return False
    test = hashlib.pbkdf2_hmac("sha256", (pin or "").encode(), salt.encode(), 100_000).hex()
    return hmac.compare_digest(test, h)


def valid_pin_format(pin: str | None) -> bool:
    return bool(pin) and len(pin) == 4 and pin.isdigit()
