"""L-01 Lernmaterialien global mit Metadaten, L-02 Auswahl in der Lektion, L-03 Archivieren."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app import materialien
from app.main import app
from material_hilfen import HAFTUNG, docx, hochladen, pdf, png

c = TestClient(app)


def _lektion(titel, mids, material="", quellen=None):
    r = c.post("/api/teacher/lessons", json={
        "titel": titel, "lernziele": ["Haftungsarten unterscheiden"], "material": material,
        "materialien": mids, "quellen": quellen or []})
    assert r.status_code == 200, r.text
    return r.json()["id"]


# ---------------------------------------------------------------- L-01

def test_ak1_upload_mit_metadaten_und_datei_metadaten():
    m = hochladen(c, "haftung-or.pdf", pdf(HAFTUNG, "D:20260901120000"), name="Haftpflicht OR",
                  faecher=["Recht", "Wirtschaft"], niveau="BM 2. Lehrjahr", beschreibung="Art. 41 bis 56 OR",
                  tags=["Haftung", "OR"], hochgeladen_von="Frau Muster", datei_geaendert_am="1788000000000")
    assert m["http"] == 201
    assert (m["name"], m["faecher"], m["niveau"], m["beschreibung"], m["tags"]) == (
        "Haftpflicht OR", ["Recht", "Wirtschaft"], "BM 2. Lehrjahr", "Art. 41 bis 56 OR", ["Haftung", "OR"])
    assert m["dateiname"] == "haftung-or.pdf" and m["dateiformat"] == "pdf" and m["seiten"] == 3
    assert m["dateigroesse"] > 500 and m["hochgeladen_von"] == "Frau Muster"
    assert m["datei_geaendert_am"] == 1788000000          # vom Browser, in Millisekunden geschickt
    assert m["hochgeladen_am"] > 1.7e9 and m["zeichen"] > 200
    assert "datei_id" not in m and "sha256" not in m       # interne Angaben nicht ausliefern
    # Originaldatei liegt im Dateisystem (filedepot), nicht in der Datenbank
    roh = materialien.holen(m["id"])
    pfad = Path(materialien.material_dir()) / "depot" / roh["datei_id"] / "file"
    assert pfad.read_bytes()[:5] == b"%PDF-" and m["speicherort"].endswith(f"{roh['datei_id']}/file")
    meta = json.loads((pfad.parent / "metadata.json").read_text())
    assert meta["filename"] == "haftung-or.pdf"
    # Download der Originaldatei
    r = c.get(f"/api/teacher/materialien/{m['id']}/datei")
    assert r.status_code == 200 and r.content == pfad.read_bytes()
    assert "haftung-or.pdf" in r.headers["content-disposition"]


def test_ak1_aenderungsdatum_aus_der_datei_wenn_der_browser_keins_schickt():
    m = hochladen(c, "datum.pdf", pdf(["Seite mit genug Text fuer die Extraktion, damit sie gilt."] * 2,
                                     "D:20250102030405"))
    assert m["datei_geaendert_am"] == 1735787045
    w = hochladen(c, "notizen.docx", docx([("Heading 1", "Tierhalterhaftung"),
                                           ("Normal", "Der Halter haftet fuer Schaden durch sein Tier, "
                                                      "ausser er beweist die gebotene Sorgfalt.")]))
    assert w["http"] == 201 and w["dateiformat"] == "docx" and w["datei_geaendert_am"] == 1788249600
    assert w["seiten"] == 1
    assert c.get(f"/api/teacher/materialien/{w['id']}/text").json()["seiten"][0]["text"].startswith("# Tierhalter")


def test_ak1_beschreibung_hoechstens_128_zeichen_und_name_aus_dateiname():
    r = hochladen(c, "lang.pdf", pdf(["x" * 80]), beschreibung="b" * 129)
    assert r["http"] == 400 and "128" in r["detail"]
    m = hochladen(c, "Skript Brueche.txt", "Ein Bruch besteht aus Zaehler und Nenner. ".encode() * 5,
                  beschreibung="b" * 128)
    assert m["http"] == 201 and m["name"] == "Skript Brueche" and m["seiten"] is None and m["dateiformat"] == "txt"


def test_ak1_vorschlaege_und_keine_dubletten_durch_schreibweise():
    hochladen(c, "tiere1.txt", ("Tiere im Recht und der Tierhalter. " * 5).encode(),
              faecher=["Biologie"], tags=["Tiere"], niveau="Grundlagen")
    m = hochladen(c, "tiere2.txt", ("Noch ein Text ueber Tiere und Haftung. " * 5).encode(),
                  faecher=["biologie ", "Recht"], tags=["tiere", "TIERE", "Haustier"], niveau="grundlagen")
    assert m["faecher"] == ["Biologie", "Recht"] and m["tags"] == ["Tiere", "Haustier"] and m["niveau"] == "Grundlagen"
    w = c.get("/api/teacher/materialien/werte").json()
    assert "Tiere" in w["tags"] and "tiere" not in w["tags"] and "Haustier" in w["tags"]
    assert "Biologie" in w["faecher"] and "Grundlagen" in w["niveaus"] and "txt" in w["formate"]
    assert "Test" in w["lehrpersonen"]


def test_ak1_gleiche_datei_wird_erkannt():
    daten = pdf(["Eine Datei, die zweimal hochgeladen wird, mit genug Text fuer die Pruefung."])
    a = hochladen(c, "doppelt.pdf", daten, trotzdem="false")
    b = hochladen(c, "doppelt-kopie.pdf", daten, trotzdem="false")
    assert b["http"] == 409 and b["detail"]["vorhanden"]["id"] == a["id"]
    d = hochladen(c, "doppelt-kopie.pdf", daten, trotzdem="true")
    assert d["http"] == 201 and d["id"] != a["id"]


def test_ak1_formate_und_leerer_text():
    assert hochladen(c, "x.exe", b"MZ" * 100)["http"] == 400
    leer = hochladen(c, "scan.pdf", pdf([" "]))
    assert leer["http"] == 400 and "gescanntes PDF" in leer["detail"]


def test_ak1_bild_ohne_ocr_wird_abgelegt_aber_nicht_indexiert(monkeypatch):
    monkeypatch.setenv("ITS_TESSERACT", "gibt-es-nicht-xyz")
    m = hochladen(c, "tafelbild.png", png())
    assert m["http"] == 201 and m["dateiformat"] == "png" and m["seiten"] == 1
    assert m["index_status"] == "ohne_text" and "Tesseract" in m["extraktion"]["hinweis"]


def test_ak1_header_anmeldung_bestimmt_die_lehrperson(monkeypatch):
    monkeypatch.setenv("ITS_TRUST_PROXY_HEADERS", "true")
    r = c.post("/api/teacher/materialien", headers={"X-Forwarded-User": "anna.lehrer@schule.ch",
                                                    "X-User-Roles": "teacher"},
               files={"file": ("h.txt", ("Haftung im Strassenverkehr und Halterhaftung. " * 4).encode())},
               data={"hochgeladen_von": "Jemand anderes"})
    assert r.status_code == 201 and r.json()["hochgeladen_von"] == "anna.lehrer@schule.ch"


def test_ak1_metadaten_nachtraeglich_aendern():
    m = hochladen(c, "aendern.txt", ("Ein Text zum Aendern der Metadaten. " * 5).encode())
    r = c.put(f"/api/teacher/materialien/{m['id']}", json={"name": "Neuer Name", "tags": ["Neu"]}).json()
    assert r["name"] == "Neuer Name" and r["tags"] == ["Neu"] and r["lektionen"] == []
    assert c.put(f"/api/teacher/materialien/{m['id']}", json={"beschreibung": "x" * 200}).status_code == 400


def test_nur_lehrpersonen(monkeypatch):
    monkeypatch.setenv("TEACHER_PASSWORD", "geheim")
    assert TestClient(app).get("/api/teacher/materialien").status_code == 401


# ---------------------------------------------------------------- L-02

def test_l02_filter_nach_metadaten_und_datei_metadaten():
    a = hochladen(c, "filter-a.pdf", pdf(["Filtertest A mit genug Text fuer die Extraktion hier."]),
                  name="Filter Alpha", faecher=["Geschichte"], tags=["Rom"], niveau="Vertieft",
                  hochgeladen_von="Herr Filter")
    b = hochladen(c, "filter-b.txt", ("Filtertest B mit genug Text fuer die Extraktion. " * 3).encode(),
                  name="Filter Beta", faecher=["Geschichte", "Latein"], beschreibung="Quellen zu Caesar")

    def ids(**p):
        return {m["id"] for m in c.get("/api/teacher/materialien", params=p).json()}
    assert {a["id"], b["id"]} <= ids(fach="geschichte")
    assert ids(fach="Latein") == {b["id"]}
    assert ids(tag="rom") == {a["id"]}
    assert a["id"] in ids(niveau="Vertieft") and b["id"] not in ids(niveau="Vertieft")
    assert ids(format="txt") >= {b["id"]} and a["id"] not in ids(format="txt")
    assert ids(lehrperson="herr filter") == {a["id"]}
    assert ids(q="caesar") == {b["id"]} and ids(q="filter alpha") == {a["id"]}
    assert a["id"] in ids(von="2020-01-01") and not ids(bis="2020-01-01")


def test_l02_lektion_aus_materialien_zusammensetzen_und_bearbeiten():
    m1 = hochladen(c, "or-41.pdf", pdf(HAFTUNG), name="OR Haftpflicht")
    m2 = hochladen(c, "notiz.txt", ("Merksatz: Kausalhaftung braucht kein Verschulden. " * 3).encode(), name="Merksatz")
    lid = _lektion("Lektion aus Ablage", [m1["id"], m2["id"]], material="Eigener Hinweis der Lehrperson.")
    d = c.get(f"/api/teacher/lessons/{lid}").json()
    assert d["materialien"] == [m1["id"], m2["id"]]
    assert d["material"].startswith("### Quelle: OR Haftpflicht\n\nHaftung aus unerlaubter Handlung")
    assert "### Quelle: Merksatz" in d["material"] and d["material"].endswith("Eigener Hinweis der Lehrperson.")
    assert d["material_eigen"] == "Eigener Hinweis der Lehrperson."
    assert [q["material_id"] for q in d["quellen"]] == [m1["id"], m2["id"]]
    assert [i["name"] for i in d["materialien_info"]] == ["OR Haftpflicht", "Merksatz"]
    # Bearbeiten: ein Material entfernen, Version steigt
    r = c.put(f"/api/teacher/lessons/{lid}", json={"titel": "Lektion aus Ablage", "lernziele": ["Ziel"],
                                                   "material": "", "materialien": [m1["id"]]}).json()
    d = c.get(f"/api/teacher/lessons/{lid}").json()
    assert r["version"] == 2 and d["materialien"] == [m1["id"]] and "Merksatz" not in d["material"]
    assert c.get(f"/api/teacher/materialien/{m1['id']}").json()["lektionen"] == [
        {"id": lid, "titel": "Lektion aus Ablage", "archiviert": False}]


def test_l02_gleiche_namen_werden_unterschieden_und_alte_quellen_bleiben():
    m1 = hochladen(c, "skript1.txt", ("Erstes Skript ueber Haftung und Schaden. " * 4).encode(), name="Skript")
    m2 = hochladen(c, "skript2.txt", ("Zweites Skript ueber Vertraege und Pflichten. " * 4).encode(), name="Skript")
    alt = "### Quelle: altes.pdf\n\nText aus einer frueheren, lektionsinternen Quelle."
    lid = _lektion("Namen", [m1["id"], m2["id"]], material=alt, quellen=[{"name": "altes.pdf", "chars": 52}])
    d = c.get(f"/api/teacher/lessons/{lid}").json()
    from app import didaktik
    assert didaktik.quellen_der_lektion(d) == ["Skript", "Skript (2)", "altes.pdf"]


def test_l02_unbekanntes_oder_archiviertes_material_nicht_waehlbar():
    r = c.post("/api/teacher/lessons", json={"titel": "X", "lernziele": ["Z"], "material": "",
                                             "materialien": ["mat-gibtsnicht"]})
    assert r.status_code == 400
    m = hochladen(c, "weg.txt", ("Material, das archiviert wird, bevor es jemand nutzt. " * 3).encode())
    c.post(f"/api/teacher/materialien/{m['id']}/archivieren")
    r = c.post("/api/teacher/lessons", json={"titel": "Y", "lernziele": ["Z"], "material": "", "materialien": [m["id"]]})
    assert r.status_code == 409 and "archiviert" in r.json()["detail"]


def test_l02_lektion_laeuft_mit_materialien_aus_der_ablage():
    m = hochladen(c, "lauf.pdf", pdf(HAFTUNG), name="Lauf")
    lid = _lektion("Lauf mit Ablage", [m["id"]])
    s = TestClient(app)
    s.post("/api/learner/login", json={"name": "Ablage-Lernende"})
    r = s.post("/api/session/start", json={"lesson_id": lid}).json()
    sid = r["session_id"]
    s.post(f"/api/session/{sid}/assess", json={"answers": ["a", "b", "c"]})
    t = s.post(f"/api/session/{sid}/next").json()
    assert t["task"]["typ"] == "theorie" and t["task"].get("quelle") == "Lauf"


# ---------------------------------------------------------------- L-03

def test_l03_archivieren_nur_ohne_aktive_lektion_und_wiederherstellen():
    m = hochladen(c, "archiv.pdf", pdf(HAFTUNG + ["Zusatzseite fuer das Archiv."]), name="Archivtest")
    lid = _lektion("Archiv-Lektion", [m["id"]])
    r = c.post(f"/api/teacher/materialien/{m['id']}/archivieren")
    assert r.status_code == 409 and r.json()["detail"]["lektionen"][0]["id"] == lid
    assert "Archiv-Lektion" in r.json()["detail"]["message"]
    # Lektion archivieren, dann geht es
    c.delete(f"/api/teacher/lessons/{lid}")
    r = c.post(f"/api/teacher/materialien/{m['id']}/archivieren").json()
    assert r["status"] == "archiviert" and r["archiviert_am"]
    assert m["id"] not in {x["id"] for x in c.get("/api/teacher/materialien").json()}
    assert m["id"] in {x["id"] for x in c.get("/api/teacher/materialien", params={"archivierte": True}).json()}
    # Daten bleiben erhalten
    assert c.get(f"/api/teacher/materialien/{m['id']}/datei").status_code == 200
    assert "Tierhalterhaftung" in materialien.text(m["id"])
    # Wiederherstellen
    w = c.post(f"/api/teacher/materialien/{m['id']}/wiederherstellen").json()
    assert w["status"] == "aktiv" and w["archiviert_am"] is None


def test_l03_material_unbenutzt_direkt_archivierbar():
    m = hochladen(c, "frei.txt", ("Ein Material, das keine Lektion verwendet. " * 3).encode())
    assert c.post(f"/api/teacher/materialien/{m['id']}/archivieren").json()["status"] == "archiviert"


def test_l03_lektion_wiederherstellen_holt_archiviertes_material_zurueck():
    m = hochladen(c, "zurueck.txt", ("Material fuer die Wiederherstellung einer Lektion. " * 3).encode(), name="Zurück")
    lid = _lektion("Wiederherstellen mit Material", [m["id"]])
    c.delete(f"/api/teacher/lessons/{lid}")
    c.post(f"/api/teacher/materialien/{m['id']}/archivieren")
    r = c.post(f"/api/teacher/lessons/{lid}/wiederherstellen").json()
    assert r["materialien_wiederhergestellt"] == ["Zurück"]
    assert materialien.holen(m["id"])["status"] == "aktiv"
