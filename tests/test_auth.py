"""Tests für den Zugangsschutz: Lehrpersonen-Login und Klassencode.

TEACHER_PASSWORD und CLASS_CODE werden zur Laufzeit aus der Umgebung gelesen,
darum lassen sie sich pro Test setzen und wieder entfernen.
"""

import os

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture
def auth_an(monkeypatch):
    monkeypatch.setenv("TEACHER_PASSWORD", "geheim123")
    yield
    client.cookies.clear()


@pytest.fixture
def code_an(monkeypatch):
    monkeypatch.setenv("CLASS_CODE", "BM2026")


@pytest.fixture
def alles_aus(monkeypatch):
    monkeypatch.delenv("TEACHER_PASSWORD", raising=False)
    monkeypatch.delenv("CLASS_CODE", raising=False)
    client.cookies.clear()


# ---------------------------------------------------------------- Teacher-Login

def test_teacher_ohne_login_gesperrt(auth_an):
    assert client.get("/api/teacher/sessions").status_code == 401
    r = client.get("/teacher", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert r.headers["location"] == "/teacher/login"


def test_login_falsches_passwort(auth_an):
    r = client.post("/api/teacher/login", json={"password": "falsch"})
    assert r.status_code == 401
    assert client.get("/api/teacher/sessions").status_code == 401


def test_login_und_logout(auth_an):
    r = client.post("/api/teacher/login", json={"password": "geheim123"})
    assert r.status_code == 200
    assert client.get("/api/teacher/sessions").status_code == 200
    r = client.get("/teacher", follow_redirects=False)
    assert r.status_code == 200
    # Logout macht das Cookie ungültig
    client.get("/teacher/logout", follow_redirects=False)
    assert client.get("/api/teacher/sessions").status_code == 401


def test_lektionserstellung_gesperrt(auth_an):
    r = client.post("/api/teacher/lessons", json={
        "titel": "X", "lernziele": ["z"], "material": "m" * 200})
    assert r.status_code == 401


def test_ohne_passwort_alles_offen(alles_aus):
    assert client.get("/api/teacher/sessions").status_code == 200
    r = client.get("/teacher", follow_redirects=False)
    assert r.status_code == 200


def test_passwortwechsel_macht_login_ungueltig(auth_an, monkeypatch):
    client.post("/api/teacher/login", json={"password": "geheim123"})
    assert client.get("/api/teacher/sessions").status_code == 200
    monkeypatch.setenv("TEACHER_PASSWORD", "neues-passwort")
    assert client.get("/api/teacher/sessions").status_code == 401


# ---------------------------------------------------------------- Klassencode

def test_start_ohne_code_abgelehnt(code_an):
    r = client.post("/api/session/start", json={"name": "Momo"})
    assert r.status_code == 403


def test_start_mit_falschem_code_abgelehnt(code_an):
    r = client.post("/api/session/start", json={"name": "Momo", "code": "falsch"})
    assert r.status_code == 403


def test_start_mit_code_ok(code_an):
    r = client.post("/api/session/start", json={"name": "Momo", "code": "bm2026"})
    assert r.status_code == 200   # Gross-/Kleinschreibung egal


def test_start_ohne_konfigurierten_code(alles_aus):
    r = client.post("/api/session/start", json={"name": "Momo"})
    assert r.status_code == 200


def test_access_info(code_an, monkeypatch):
    monkeypatch.setenv("TEACHER_PASSWORD", "x")
    d = client.get("/api/access").json()
    assert d == {"code_required": True, "teacher_login_required": True}
    # Der Code selbst darf nie im Response auftauchen
    assert "BM2026" not in client.get("/api/access").text
