"""T-04: Rollen, Anmeldung über Header und rollenabhängiger Zugang."""

import re

import pytest
from fastapi.testclient import TestClient
from starlette.routing import Route

from app.main import app

AUSNAHMEN = {"/teacher/login", "/teacher/logout", "/api/teacher/login"}


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def passwort(monkeypatch):
    monkeypatch.setenv("TEACHER_PASSWORD", "geheim123")


@pytest.fixture
def header_an(monkeypatch):
    monkeypatch.setenv("ITS_TRUST_PROXY_HEADERS", "true")


def _alle_routen(routes):
    """Flacht die Routen ab; neuere FastAPI-Versionen kapseln eingebundene Router."""
    for r in routes:
        inner = getattr(r, "original_router", None)
        if inner is not None:
            yield from _alle_routen(inner.routes)
        else:
            yield r


def _geschuetzte_routen():
    for r in _alle_routen(app.routes):
        if not isinstance(r, Route) or r.path in AUSNAHMEN:
            continue
        if r.path == "/teacher" or r.path.startswith(("/teacher/", "/api/teacher")):
            for m in sorted(r.methods - {"HEAD"}):
                yield m, re.sub(r"\{[^}]+\}", "x", r.path)


def test_es_gibt_geschuetzte_routen():
    routen = list(_geschuetzte_routen())
    assert len(routen) >= 8
    assert ("GET", "/api/teacher/sessions") in routen


@pytest.mark.parametrize("methode,pfad", list(_geschuetzte_routen()))
def test_jede_lehrpersonen_route_ohne_login_gesperrt(client, passwort, methode, pfad):
    r = client.request(methode, pfad, json={}, follow_redirects=False)
    if pfad.startswith("/api/"):
        assert r.status_code == 401, (methode, pfad, r.status_code)
    else:
        assert r.status_code in (302, 307), (methode, pfad, r.status_code)
        assert r.headers["location"] == "/teacher/login"


@pytest.mark.parametrize("pfad", ["/static/teacher.html", "/static/lesson_editor.html",
                                  "/static/index.html"])
def test_html_nicht_ueber_static_erreichbar(client, passwort, pfad):
    assert client.get(pfad).status_code == 404


def test_llm_test_nur_fuer_lehrpersonen(client, passwort):
    assert client.get("/api/llm-test").status_code == 401


def test_lernende_duerfen_keine_lehrpersonen_endpunkte(client, passwort):
    client.post("/api/learner/login", json={"name": "Mia"})
    assert client.get("/api/me").json()["rolle"] == "lernend"
    assert client.get("/api/teacher/sessions").status_code == 401
    assert client.post("/api/teacher/lessons", json={}).status_code == 401


# ---------------------------------------------------------------- AK 3 Testlauf

def test_lehrpersonen_durchlauf_ist_testlauf(client, passwort):
    client.post("/api/teacher/login", json={"password": "geheim123"})
    sid = client.post("/api/session/start", json={"name": "LP-Test"}).json()["session_id"]
    me = client.get("/api/me").json()
    assert me["lehrperson"] is True
    standard = [r["session_id"] for r in client.get("/api/teacher/sessions").json()]
    mit = client.get("/api/teacher/sessions?testlaeufe=true").json()
    assert sid not in standard
    row = next(r for r in mit if r["session_id"] == sid)
    assert row["testlauf"] is True
    assert client.get(f"/api/teacher/sessions/{sid}").json()["session"]["testlauf"] is True


def test_lernenden_durchlauf_ist_kein_testlauf(client, passwort):
    sid = client.post("/api/session/start", json={"name": "Echte Lernende"}).json()["session_id"]
    client.post("/api/teacher/login", json={"password": "geheim123"})
    standard = [r["session_id"] for r in client.get("/api/teacher/sessions").json()]
    assert sid in standard


# ---------------------------------------------------------------- AK 4 Header

def test_header_anmeldung_lernend(client, header_an):
    h = {"X-Forwarded-User": "mia.muster", "X-User-Roles": "student"}
    me = client.get("/api/me", headers=h).json()
    assert me["name"] == "mia.muster" and me["name_fixiert"] is True
    assert me["rolle"] == "lernend" and me["code_required"] is False
    # Header entscheidet auch ohne Passwort: keine Lehrpersonen-Endpunkte
    assert client.get("/api/teacher/sessions", headers=h).status_code == 401
    assert client.get("/teacher", headers=h, follow_redirects=False).status_code == 307
    # Ein anderer Name im Formular wird ignoriert
    d = client.post("/api/session/start", headers=h, json={"name": "Jemand anders"}).json()
    detail = client.get(f"/api/session/{d['session_id']}/state", headers=h).json()
    assert detail["name"] == "mia.muster"


def test_header_anmeldung_lehrperson(client, header_an, passwort):
    h = {"X-Forwarded-User": "frau.lehrer", "X-User-Roles": "staff, teacher"}
    assert client.get("/api/me", headers=h).json()["rolle"] == "lehrperson"
    assert client.get("/api/teacher/sessions", headers=h).status_code == 200


def test_header_namen_konfigurierbar(client, header_an, monkeypatch):
    monkeypatch.setenv("ITS_USER_HEADER", "Cf-Access-Authenticated-User-Email")
    monkeypatch.setenv("ITS_ROLES_HEADER", "X-Gruppen")
    monkeypatch.setenv("ITS_TEACHER_ROLE", "lp")
    h = {"Cf-Access-Authenticated-User-Email": "lp@schule.ch", "X-Gruppen": "LP"}
    me = client.get("/api/me", headers=h).json()
    assert me["name"] == "lp@schule.ch" and me["rolle"] == "lehrperson"
    # Standard-Header wirken dann nicht mehr
    assert client.get("/api/me", headers={"X-Forwarded-User": "x"}).json()["name"] is None


def test_header_plus_passwort_macht_zur_lehrperson(client, header_an, passwort):
    """Cloudflare Access liefert keine Rollen: Lehrpersonen melden sich zusätzlich an."""
    h = {"X-Forwarded-User": "lp@schule.ch"}
    assert client.get("/api/me", headers=h).json()["rolle"] == "lernend"
    client.post("/api/teacher/login", json={"password": "geheim123"})
    assert client.get("/api/me", headers=h).json()["rolle"] == "lehrperson"


# ---------------------------------------------------------------- AK 5

def test_ohne_option_haben_header_keine_wirkung(client, passwort, monkeypatch):
    monkeypatch.delenv("ITS_TRUST_PROXY_HEADERS", raising=False)
    h = {"X-Forwarded-User": "hacker", "X-User-Roles": "teacher"}
    me = client.get("/api/me", headers=h).json()
    assert me["name"] is None and me["rolle"] is None and me["name_fixiert"] is False
    assert client.get("/api/teacher/sessions", headers=h).status_code == 401
    assert client.get("/teacher", headers=h, follow_redirects=False).status_code == 307


# ---------------------------------------------------------------- Lernenden-Login

def test_lernenden_login_braucht_klassencode(client, monkeypatch):
    monkeypatch.setenv("CLASS_CODE", "BM2026")
    assert client.post("/api/learner/login", json={"name": "Mia"}).status_code == 403
    assert client.post("/api/learner/login", json={"name": "Mia", "code": "bm2026"}).status_code == 200
    assert client.get("/api/me").json()["name"] == "Mia"


def test_codewechsel_meldet_lernende_ab(client, monkeypatch):
    monkeypatch.setenv("CLASS_CODE", "ALT")
    client.post("/api/learner/login", json={"name": "Mia", "code": "ALT"})
    assert client.get("/api/me").json()["name"] == "Mia"
    monkeypatch.setenv("CLASS_CODE", "NEU")
    assert client.get("/api/me").json()["name"] is None


def test_gefaelschtes_lernenden_cookie_wirkt_nicht(client):
    client.cookies.set("its_learner", "TWlh.falschesignatur")
    assert client.get("/api/me").json()["name"] is None
