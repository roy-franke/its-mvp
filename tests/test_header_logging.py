"""T-24: Debug-Logging der Request-Header."""

import logging

import pytest
from fastapi.testclient import TestClient

from app import auth, main
from app.main import app

H = {"X-Forwarded-User": "mia.muster", "X-User-Roles": "student",
     "Cookie": "its_learner=abcdefghijklmnopqrstuvwxyz", "Authorization": "Bearer 1234567890abcdef",
     "Cf-Access-Jwt-Assertion": "eyJhbGciOiJSUzI1NiIsImtpZCI6"}


@pytest.fixture
def header_an(monkeypatch):
    monkeypatch.setenv("ITS_TRUST_PROXY_HEADERS", "true")
    monkeypatch.delenv("ITS_LOG_HEADERS_UNMASKED", raising=False)


def _logzeilen(caplog, stufe):
    logging.getLogger("its.auth").setLevel(stufe)
    try:
        with caplog.at_level(stufe, logger="its.auth"):
            TestClient(app).get("/api/me", headers=H)
    finally:
        logging.getLogger("its.auth").setLevel(logging.NOTSET)
    return [r.getMessage() for r in caplog.records if r.getMessage().startswith("Request headers")]


def test_ak1_mit_debug_alle_header_einmal_pro_request(header_an, caplog):
    meldungen = _logzeilen(caplog, logging.DEBUG)
    assert len(meldungen) == 1
    zeilen = meldungen[0].splitlines()[1:]
    namen = [z[2:].split(":", 1)[0] for z in zeilen]
    assert namen == sorted(namen)                                    # sortiert, ein Header pro Zeile
    assert "- x-forwarded-user: mia.muster" in zeilen and "- x-user-roles: student" in zeilen


def test_ak1_mit_info_nichts(header_an, caplog):
    assert _logzeilen(caplog, logging.INFO) == []


def test_ak2_vertrauliche_werte_maskiert(header_an, caplog):
    text = _logzeilen(caplog, logging.DEBUG)[0]
    assert "- cookie: its_lear… (Länge " in text
    assert "- authorization: Bearer 1… (Länge 23)" in text
    assert "- cf-access-jwt-assertion: eyJhbGci… (Länge 28)" in text
    assert "abcdefghijklmnop" not in text and "1234567890abcdef" not in text


def test_ak2_unmaskiert_mit_schalter(header_an, caplog, monkeypatch):
    monkeypatch.setenv("ITS_LOG_HEADERS_UNMASKED", "true")
    assert "Bearer 1234567890abcdef" in _logzeilen(caplog, logging.DEBUG)[0]


def test_ak3_ohne_header_anmeldung_nichts(monkeypatch, caplog):
    monkeypatch.delenv("ITS_TRUST_PROXY_HEADERS", raising=False)
    assert _logzeilen(caplog, logging.DEBUG) == []


def test_log_stufen_aus_der_umgebung(monkeypatch):
    monkeypatch.setenv("ITS_LOG_LEVEL", "WARNING")
    monkeypatch.setenv("ITS_LOG_LEVELS", "its.auth=DEBUG, its.test=quatsch")
    try:
        text = main._log_stufen_einrichten()
        assert text.startswith("alle WARNING") and "its.auth=DEBUG" in text and "ungültig" in text
        assert logging.getLogger("its.auth").isEnabledFor(logging.DEBUG)
    finally:
        monkeypatch.setenv("ITS_LOG_LEVEL", "INFO")
        monkeypatch.setenv("ITS_LOG_LEVELS", "")
        main._log_stufen_einrichten()
        logging.getLogger("its.auth").setLevel(logging.NOTSET)
