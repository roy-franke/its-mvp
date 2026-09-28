"""N-03: Wissensstufen und Internetrecherche."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app import einstellungen, llm, tutor, websuche
from app.main import LESSONS_DIR, app

lp = TestClient(app)
MATERIAL = ("Die Verschuldenshaftung nach Art. 41 OR verlangt Schaden, Widerrechtlichkeit, "
            "Kausalzusammenhang und Verschulden. ") * 2


def _lektion(stufen):
    r = lp.post("/api/teacher/lessons", json={
        "titel": "Recherche Haftung", "lernziele": ["Haftung erklären"], "material": MATERIAL,
        "einstellungen": {"wissensstufen": stufen}})
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


@pytest.fixture
def lektionen():
    ids = {"alle": _lektion(["material", "allgemeinwissen", "internet"]),
           "nur_internet": _lektion(["material", "internet"])}
    yield ids
    for lid in ids.values():
        (LESSONS_DIR / f"{lid}.json").unlink(missing_ok=True)


class Aufrufe:
    """Zählt jeden Versuch, über httpx nach aussen zu gehen."""
    def __init__(self, antwort=None):
        self.urls = []
        self.params = []
        self.antwort = antwort

    def get(self, url, params=None, **kw):
        self.urls.append(url)
        self.params.append(params or {})
        if self.antwort is None:
            raise AssertionError("Aufruf nach aussen trotz ausgeschalteter Recherche")
        return httpx.Response(200, json=self.antwort, request=httpx.Request("GET", url))


TREFFER = {"results": [
    {"title": "Verschuldenshaftung – Übersicht", "url": "https://example.org/haftung",
     "content": "Die Verschuldenshaftung setzt ein Verschulden voraus, also Absicht oder Fahrlässigkeit."},
    {"title": "Art. 41 OR", "url": "https://example.org/or41", "content": "Wer einem andern widerrechtlich Schaden zufügt …"},
    {"title": "kaputt", "url": "javascript:alert(1)", "content": "x"},
]}


def _bis_ausgeschoepft(c, name, lid):
    sid = c.post("/api/session/start", json={"name": name, "lesson_id": lid}).json()["session_id"]
    c.post(f"/api/session/{sid}/assess", json={"answers": ["a", "b", "c"]})
    assert c.post(f"/api/session/{sid}/next").json()["task"]["typ"] == "theorie"
    for _ in range(3):
        r = c.post(f"/api/session/{sid}/chat", json={"message": "mehr", "art": "theorie"}).json()
    return sid, r


# ---------------------------------------------------------------- Einstellungen

def test_standard_ist_material_und_allgemeinwissen():
    assert einstellungen.settings({})["wissensstufen"] == ["material", "allgemeinwissen"]
    assert einstellungen.validate({"wissensstufen": ["material", "internet"]})["wissensstufen"] == [
        "material", "internet"]


def test_standardmaessig_aus(monkeypatch):
    monkeypatch.delenv("ITS_WEB_SEARCH", raising=False)
    monkeypatch.setenv("ITS_SEARXNG_URL", "http://searx.local")
    assert not websuche.aktiv()
    monkeypatch.setenv("ITS_WEB_SEARCH", "true")
    monkeypatch.delenv("ITS_SEARXNG_URL")
    assert not websuche.aktiv()          # ohne Suchdienst bleibt sie aus


# ---------------------------------------------------------------- AK 1

def test_allgemeinwissen_nach_ausgeschoepftem_material():
    """AK 1: Mit erlaubtem Allgemeinwissen erscheint nach ausgeschöpftem Material eine
    gekennzeichnete Ergänzung."""
    c = TestClient(app)
    sid, r = _bis_ausgeschoepft(c, "AK1 Allgemeinwissen", "haftungsrecht")
    assert r["angebot"] == "allgemeinwissen"
    r = c.post(f"/api/session/{sid}/chat", json={"message": "Ja", "art": "allgemeinwissen"}).json()
    assert r["ausserhalb_material"] is True and not r["internet"]


# ---------------------------------------------------------------- AK 2

def test_ausgeschaltet_kein_aufruf_nach_aussen(monkeypatch, lektionen):
    """AK 2: Mit ausgeschalteter Recherche findet kein Aufruf nach aussen statt,
    auch wenn die Lektion sie erlaubt und der Client sie direkt anfordert."""
    monkeypatch.setenv("ITS_WEB_SEARCH", "false")
    monkeypatch.setenv("ITS_SEARXNG_URL", "http://searx.local")
    aufrufe = Aufrufe()
    monkeypatch.setattr(websuche.httpx, "get", aufrufe.get)
    c = TestClient(app)
    sid, r = _bis_ausgeschoepft(c, "AK2 aus", lektionen["alle"])
    assert r["angebot"] == "allgemeinwissen"
    r = c.post(f"/api/session/{sid}/chat", json={"message": "Ja", "art": "allgemeinwissen"}).json()
    assert r["angebot"] is None                       # keine Internet-Stufe angeboten
    r = c.post(f"/api/session/{sid}/chat", json={"message": "Such", "art": "internet"}).json()
    assert not r["internet"] and not r["links"]
    assert websuche.suchen("Verschuldenshaftung") == []
    assert aufrufe.urls == []


# ---------------------------------------------------------------- eingeschaltet

@pytest.fixture
def recherche_an(monkeypatch):
    monkeypatch.setenv("ITS_WEB_SEARCH", "true")
    monkeypatch.setenv("ITS_SEARXNG_URL", "http://searx.local/")
    aufrufe = Aufrufe(TREFFER)
    monkeypatch.setattr(websuche.httpx, "get", aufrufe.get)
    return aufrufe


def test_internet_nach_allgemeinwissen(monkeypatch, lektionen, recherche_an):
    prompts = []

    def modell(system, user, json_mode=False):
        prompts.append(user)
        if "INTERNETRECHERCHE" in user:
            return json.dumps({"antwort": "Die Verschuldenshaftung verlangt ein Verschulden.",
                               "quellen": [1, 7]}), {}
        return llm._mock_text(system, user), {}
    monkeypatch.setitem(llm._PROVIDERS, "mock", modell)
    c = TestClient(app)
    sid, r = _bis_ausgeschoepft(c, "Internet Lina", lektionen["alle"])
    r = c.post(f"/api/session/{sid}/chat", json={"message": "Ja", "art": "allgemeinwissen"}).json()
    assert r["angebot"] == "internet"
    r = c.post(f"/api/session/{sid}/chat", json={"message": "Ja", "art": "internet"}).json()
    assert r["internet"] and r["ausserhalb_material"]
    assert r["links"] == [{"titel": "Verschuldenshaftung – Übersicht", "url": "https://example.org/haftung"}]
    assert "nicht von deiner Lehrperson geprüft" in r["hinweis"]
    # Datenschutz: nur die fachliche Anfrage geht nach aussen
    anfrage = recherche_an.params[-1]["q"]
    assert "Lina" not in anfrage and "Recherche Haftung" in anfrage
    assert recherche_an.urls == ["http://searx.local/search"]
    ev = [e for e in c.get(f"/api/teacher/sessions/{sid}").json()["events"] if e["type"] == "chat_reply"][-1]
    assert ev["payload"]["internet"] and ev["payload"]["suchanfrage"] == anfrage
    assert any("javascript:" in t["url"] for t in TREFFER["results"])
    assert "javascript" not in json.dumps(ev["payload"]["links"])


def test_nur_internet_wird_direkt_angeboten(lektionen, recherche_an):
    c = TestClient(app)
    sid, r = _bis_ausgeschoepft(c, "Nur Internet", lektionen["nur_internet"])
    assert r["angebot"] == "internet" and "Internet" in r["antwort"]


def test_suchdienst_nicht_erreichbar(monkeypatch, lektionen):
    monkeypatch.setenv("ITS_WEB_SEARCH", "true")
    monkeypatch.setenv("ITS_SEARXNG_URL", "http://searx.local")

    def kaputt(url, **kw):
        raise httpx.ConnectError("weg")
    monkeypatch.setattr(websuche.httpx, "get", kaputt)
    c = TestClient(app)
    sid, _ = _bis_ausgeschoepft(c, "Suchdienst weg", lektionen["alle"])
    r = c.post(f"/api/session/{sid}/chat", json={"message": "Ja", "art": "internet"}).json()
    assert not r["internet"] and r["angebot"] == "lehrperson" and "Lehrperson" in r["antwort"]


def test_suchanfrage_nur_fachlich():
    q = websuche.suchanfrage({"titel": "Haftpflichtrecht – Grundlagen (ABU/BM)"}, "Tierhalterhaftung")
    assert q == "Tierhalterhaftung Haftpflichtrecht Grundlagen"


def test_bewertung_bleibt_materialgebunden(monkeypatch, lektionen, recherche_an):
    """Die Bewertung ruft nie die Recherche auf."""
    lesson = json.loads((LESSONS_DIR / f"{lektionen['alle']}.json").read_text(encoding="utf-8"))
    tutor.evaluate_answer(lesson, tutor.new_profile(), {"inhalt": "x", "frage": "y"}, "Antwort")
    assert recherche_an.urls == []
