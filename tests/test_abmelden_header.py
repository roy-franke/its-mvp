"""T-23: Abmelden bei Header-Anmeldung."""

import logging

import pytest
from fastapi.testclient import TestClient

from app import auth
from app.main import app

H = {"X-Forwarded-User": "mia.muster", "X-User-Roles": "student"}
URL = "https://tutor.example.ch/cdn-cgi/access/logout"


@pytest.fixture
def header_an(monkeypatch):
    monkeypatch.setenv("ITS_TRUST_PROXY_HEADERS", "true")
    monkeypatch.delenv("ITS_LOGOUT_HEADER", raising=False)
    monkeypatch.delenv("ITS_LOGOUT_URL", raising=False)
    monkeypatch.setattr(auth, "_warnung_ohne_logout", False)


def test_ak1_button_und_weiterleitung_nach_dem_loeschen_der_cookies(header_an):
    c = TestClient(app)
    h = dict(H, **{"X-Logout-Url": URL})
    assert c.get("/api/me", headers=h).json()["abmelden"] is True
    c.post("/api/teacher/login", json={"password": ""})
    r = c.get("/logout", headers=h, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == URL
    gesetzt = r.headers.get_list("set-cookie")
    assert any(x.startswith("its_teacher=\"\"") for x in gesetzt) and any(x.startswith("its_learner=\"\"") for x in gesetzt)


def test_ak2_anderer_header_name(header_an, monkeypatch):
    monkeypatch.setenv("ITS_LOGOUT_HEADER", "X-Abmelden")
    c = TestClient(app)
    assert c.get("/api/me", headers=dict(H, **{"X-Logout-Url": URL})).json()["abmelden"] is False
    r = c.get("/logout", headers=dict(H, **{"X-Abmelden": "/abmelden"}), follow_redirects=False)
    assert r.headers["location"] == "/abmelden"


@pytest.mark.parametrize("wert", ["javascript:alert(1)", "//boese.example.com/", "data:text/html,x", "ftp://x"])
def test_ak3_unsichere_adressen_werden_verworfen(header_an, wert, caplog):
    c = TestClient(app)
    with caplog.at_level(logging.WARNING, logger="its.auth"):
        me = c.get("/api/me", headers=dict(H, **{"X-Logout-Url": wert})).json()
    assert me["abmelden"] is False
    assert any("verworfen" in r.getMessage() for r in caplog.records)
    r = c.get("/logout", headers=dict(H, **{"X-Logout-Url": wert}), follow_redirects=False)
    assert r.headers["location"] == "/"


def test_ak4_ohne_header_anmeldung_keine_wirkung(monkeypatch):
    monkeypatch.delenv("ITS_TRUST_PROXY_HEADERS", raising=False)
    c = TestClient(app)
    c.post("/api/learner/login", json={"name": "Ohne Header"})
    r = c.get("/logout?ziel=lernend", headers={"X-Logout-Url": URL}, follow_redirects=False)
    assert r.headers["location"] == "/"


def test_e6_ohne_header_kein_button_mit_warnung_und_rueckfalladresse(header_an, monkeypatch, caplog):
    c = TestClient(app)
    with caplog.at_level(logging.WARNING, logger="its.auth"):
        assert c.get("/api/me", headers=H).json()["abmelden"] is False
    assert any("Abmeldeadresse" in r.getMessage() for r in caplog.records)
    monkeypatch.setenv("ITS_LOGOUT_URL", "/cdn-cgi/access/logout")
    assert c.get("/api/me", headers=H).json()["abmelden"] is True
    assert c.get("/logout", headers=H, follow_redirects=False).headers["location"] == "/cdn-cgi/access/logout"
