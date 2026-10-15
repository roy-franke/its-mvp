"""T-30: Lernmaterialien aus der Vektordatenbank im Tutor verwenden (RAG)."""

import pytest
from fastapi.testclient import TestClient

from app import llm, rag, tutor, vektoren
from app.main import app
from material_hilfen import HAFTUNG, hochladen, pdf

c = TestClient(app)

FUELL = ["Verjaehrung von Forderungen", "Kaufvertrag und Gewaehrleistung", "Mietrecht und Nebenkosten",
         "Arbeitsvertrag und Kuendigungsschutz", "Werkvertrag und Maengelruege", "Darlehen und Zinsen",
         "Buergschaft und Solidarhaftung", "Auftrag und Sorgfaltspflicht", "Gesellschaftsrecht und Aktien",
         "Wechselrecht und Checks"]


def _gross_pdf() -> bytes:
    """Etwa 40 Seiten: die drei Haftungsseiten und Fuellseiten mit eigenem Vokabular."""
    seiten = list(HAFTUNG)
    for i in range(37):
        thema = FUELL[i % len(FUELL)]
        seiten.append(f"{thema} Teil {i}\n" + (f"Dieser Abschnitt behandelt {thema} mit Regeln, Fristen und "
                                               f"Beispielen aus dem Alltag der Lernenden. " * 12))
    return pdf(seiten)


@pytest.fixture
def aufzeichnung(monkeypatch):
    """Zeichnet System- und Benutzerteil jedes LLM-Aufrufs auf."""
    aufrufe = []
    original = llm._PROVIDERS["mock"]

    def mock(system, user, json_mode=False):
        aufrufe.append((system, user))
        return original(system, user, json_mode)
    monkeypatch.setitem(llm._PROVIDERS, "mock", mock)
    return aufrufe


def _lektion(mids, titel="RAG-Lektion", einstellungen=None, material=""):
    r = c.post("/api/teacher/lessons", json={
        "titel": titel, "lernziele": ["Die Tierhalterhaftung erklaeren", "Die Haftung aus unerlaubter Handlung anwenden"],
        "material": material, "materialien": mids, "einstellungen": einstellungen or {}})
    assert r.status_code == 200, r.text
    return r.json()["id"], r.json()["kontext"]


def _grosses_material(monkeypatch):
    monkeypatch.setenv("ITS_CHUNK_GROESSE", "600")
    monkeypatch.setenv("ITS_CHUNK_OVERLAP", "150")
    m = hochladen(c, "or-gross.pdf", _gross_pdf(), name="OR gross", beschreibung="Obligationenrecht, Auszug")
    vektoren.warten()
    assert c.get(f"/api/teacher/materialien/{m['id']}").json()["index_status"] == "bereit"
    return m


def _sequenz(lid, name):
    s = TestClient(app)
    s.post("/api/learner/login", json={"name": name})
    sid = s.post("/api/session/start", json={"lesson_id": lid}).json()["session_id"]
    s.post(f"/api/session/{sid}/assess", json={"answers": ["a", "b", "c"]})
    return s, sid


def _events(sid, typ=None):
    ev = c.get(f"/api/teacher/sessions/{sid}").json()["events"]
    return [e for e in ev if typ is None or e["type"] == typ]


# ---------------------------------------------------------------- Modus

def test_modus_ohne_vektordb_und_ohne_ablage():
    assert rag.modus({"material": "x" * 50000, "materialien": []})[0] == "voll"
    assert rag.modus({"material": "x" * 50000, "materialien": ["mat-x"]}) == ("voll", "keine Vektordatenbank eingerichtet")


def test_modus_nach_groesse_und_einstellung(mit_vektordb, monkeypatch):
    klein = hochladen(c, "klein.pdf", pdf(HAFTUNG), name="Klein")
    vektoren.warten()
    lid, kontext = _lektion([klein["id"]], "Klein automatisch")
    lektion = c.get(f"/api/teacher/lessons/{lid}").json()
    modus, grund = rag.modus(lektion)
    assert modus == "voll" and "klein genug" in grund and kontext["rag"] is False
    assert rag.modus(dict(lektion, einstellungen={"materialzugriff": "auszuege"}))[0] == "rag"
    monkeypatch.setenv("ITS_RAG_AB_TOKENS", "50")
    assert rag.modus(lektion)[0] == "rag"
    assert rag.modus(dict(lektion, einstellungen={"materialzugriff": "ganz"}))[0] == "voll"
    monkeypatch.setenv("ITS_RAG", "aus")
    assert "ITS_RAG" in rag.modus(lektion)[1]


def test_nicht_indexiertes_material_fuehrt_zum_ganzen_material(mit_vektordb, monkeypatch):
    m = hochladen(c, "offen.pdf", pdf(HAFTUNG), name="Offen")
    vektoren.warten()
    monkeypatch.setenv("ITS_EMBED_MODEL", "neues-modell")         # Index jetzt veraltet
    modus, grund = rag.modus({"material": "x" * 40000, "materialien": [m["id"]],
                              "einstellungen": {"materialzugriff": "auszuege"}})
    assert modus == "voll" and "veraltet" in grund


# ---------------------------------------------------------------- Prompts

def test_systemprompt_ohne_volltext_und_auszuege_im_benutzerteil(mit_vektordb, monkeypatch, aufzeichnung):
    m = _grosses_material(monkeypatch)
    lid, kontext = _lektion([m["id"]], "Gross RAG", material="Eigener Merksatz der Lehrperson.")
    assert kontext["rag"] is True and kontext["material_tokens"] > 4000
    lektion = c.get(f"/api/teacher/lessons/{lid}").json()
    voll = tutor._system_prompt(lektion, voll=True)
    s, sid = _sequenz(lid, "RAG-Prompt")
    s.post(f"/api/session/{sid}/next")                 # Theorie
    s.post(f"/api/session/{sid}/next")                 # Aufgabe
    systeme = {sys for sys, _ in aufzeichnung}
    assert len(systeme) == 1, "Systemprompt pro Lektion konstant (Prompt-Cache)"
    system = systeme.pop()
    assert "Dieser Abschnitt behandelt" not in system and "«OR gross» (or-gross.pdf, 40 Seiten)" in system
    assert "EIGENER TEXT DER LEHRPERSON:\nEigener Merksatz der Lehrperson." in system
    assert len(system) < len(voll) / 5
    for _, user in aufzeichnung:
        assert user.startswith("AUFGABE: ") and rag.ABSCHNITT_KOPF in user
        kopf, auszug = user.split(rag.ABSCHNITT_KOPF, 1)
        assert "[1] Quelle: OR gross, S. " in auszug
        assert len(auszug) <= rag.max_zeichen() + 1000
    # Die Theorie zu den Lernzielen holt die Haftungsseiten, nicht die Fuellseiten
    theorie = next(u for _, u in aufzeichnung if u.startswith("AUFGABE: THEORIE_SCHRITT"))
    assert "Tierhalter" in theorie.split(rag.ABSCHNITT_KOPF)[1]


def test_ablauf_mit_fundstellen_und_protokoll(mit_vektordb, monkeypatch):
    m = _grosses_material(monkeypatch)
    lid, _ = _lektion([m["id"]], "Gross Ablauf")
    s, sid = _sequenz(lid, "RAG-Ablauf")
    t = s.post(f"/api/session/{sid}/next").json()["task"]
    assert t["typ"] == "theorie" and t["quelle"] == "OR gross" and t["fundstelle"].startswith("S. ")
    abrufe = _events(sid, "rag_abruf")
    schritte = [a["payload"]["schrittart"] for a in abrufe]
    assert schritte[:2] == ["EINSTUFUNGSFRAGEN", "EINSTUFUNG_BEWERTEN"] and "THEORIE_SCHRITT" in schritte
    th = next(a["payload"] for a in abrufe if a["payload"]["schrittart"] == "THEORIE_SCHRITT")
    assert th["verwendet"] == [1] and th["treffer"][0]["fundstelle"] == t["fundstelle"]
    assert th["anfragen"] == ["Gross Ablauf: Die Tierhalterhaftung erklaeren",
                              "Gross Ablauf: Die Haftung aus unerlaubter Handlung anwenden"]
    assert all(0 < x["aehnlichkeit"] <= 1 for x in th["treffer"]) and th["modell"] == "mock-wortstamm-256"
    s.post(f"/api/session/{sid}/next")
    r = s.post(f"/api/session/{sid}/answer", json={"answer": "Der Halter haftet, ausser er beweist die Sorgfalt "
                                                             "bei der Beaufsichtigung des Tieres.", "confidence": 6})
    assert r.status_code == 200
    assert any(a["payload"]["schrittart"] == "ANTWORT_BEWERTEN" for a in _events(sid, "rag_abruf"))
    chat = s.post(f"/api/session/{sid}/chat", json={"message": "Was ist ein Tierhalter genau?"}).json()
    assert chat["quellen"] and chat["quellen"][0].startswith("OR gross, S. ")
    reply = _events(sid, "chat_reply")[-1]["payload"]
    assert reply["quellen"] == chat["quellen"]
    # Lernende sehen Fundstellen in ihrem Verlauf, nicht aber das Protokoll der Abrufe
    verlauf = s.post(f"/api/session/{sid}/fortsetzen").json()["verlauf"]
    assert any(e.get("fundstelle") for e in verlauf if e["art"] == "theorie")
    assert any(e.get("quellen") for e in verlauf if e["art"] == "tutor")
    assert not any(e.get("art") == "rag_abruf" for e in verlauf)


def test_erfundene_auszugsnummer_wird_verworfen(mit_vektordb, monkeypatch):
    m = _grosses_material(monkeypatch)
    lid, _ = _lektion([m["id"]], "Gross erfunden")
    monkeypatch.setenv("ITS_MOCK_AUSZUG", "99")
    s, sid = _sequenz(lid, "RAG-Erfunden")
    t = s.post(f"/api/session/{sid}/next").json()["task"]
    assert "fundstelle" not in t
    th = [a["payload"] for a in _events(sid, "rag_abruf") if a["payload"]["schrittart"] == "THEORIE_SCHRITT"][0]
    assert th["verwendet"] == [] and th["verwendet_verworfen"] == "[99]"


def test_vorabruf_protokolliert_beim_uebernehmen(mit_vektordb, monkeypatch):
    m = _grosses_material(monkeypatch)
    lid, _ = _lektion([m["id"]], "Gross Vorabruf")
    s, sid = _sequenz(lid, "RAG-Vorabruf")
    vorher = len(_events(sid, "rag_abruf"))
    s.post(f"/api/session/{sid}/next?prefetch=true")
    assert len(_events(sid, "rag_abruf")) == vorher, "Vorabruf verändert den Lernverlauf nicht"
    s.post(f"/api/session/{sid}/next")
    assert any(a["payload"]["schrittart"] == "THEORIE_SCHRITT" for a in _events(sid, "rag_abruf")[vorher:])


def test_retrieval_faellt_aus_ganzes_material(mit_vektordb, monkeypatch, aufzeichnung):
    m = _grosses_material(monkeypatch)
    lid, _ = _lektion([m["id"]], "Gross Ausfall")
    s, sid = _sequenz(lid, "RAG-Ausfall")

    def kaputt(*a, **k):
        raise ConnectionError("Chroma weg")
    monkeypatch.setattr(vektoren, "suchen", kaputt)
    aufzeichnung.clear()
    t = s.post(f"/api/session/{sid}/next").json()["task"]
    assert t["typ"] == "theorie"
    assert "Dieser Abschnitt behandelt" in aufzeichnung[-1][0], "ganzes Material im Systemprompt"
    fehler = [a["payload"] for a in _events(sid, "rag_abruf") if a["payload"].get("modus") == "voll"]
    assert fehler and "Chroma weg" in fehler[-1]["fehler"]


def test_kleine_lektion_bleibt_unveraendert(mit_vektordb, aufzeichnung):
    m = hochladen(c, "klein2.pdf", pdf(HAFTUNG), name="Klein zwei")
    vektoren.warten()
    lid, _ = _lektion([m["id"]], "Klein unveraendert")
    s, sid = _sequenz(lid, "RAG-Klein")
    s.post(f"/api/session/{sid}/next")
    assert all(rag.ABSCHNITT_KOPF not in u and "Tierhalterhaftung" in sys for sys, u in aufzeichnung)
    assert _events(sid, "rag_abruf") == []


def test_editor_hilfen_mit_auszuegen_bei_grossem_material(mit_vektordb, monkeypatch, aufzeichnung):
    m = _grosses_material(monkeypatch)
    r = c.post("/api/teacher/lessons/check-material", json={
        "lernziele": ["Die Tierhalterhaftung erklaeren"], "material": "", "materialien": [m["id"]]})
    assert r.status_code == 200
    user = aufzeichnung[-1][1]
    assert user.startswith("AUFGABE: MATERIAL_PRUEFEN") and "### Quelle: OR gross (S. " in user
    assert "Tierhalter" in user and len(user) < 14000
