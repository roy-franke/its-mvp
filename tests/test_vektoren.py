"""T-29: Chunking mit Overlap, Embeddings und Ablage in ChromaDB."""

import httpx
from fastapi.testclient import TestClient

from app import materialien, vektoren
from app.main import app
from material_hilfen import HAFTUNG, hochladen, pdf

c = TestClient(app)


# ---------------------------------------------------------------- Chunking

def _seiten(*texte):
    return [{"seite": i + 1, "text": t} for i, t in enumerate(texte)]


def test_saetze_nicht_nach_abkuerzungen_teilen():
    assert vektoren.saetze("Er haftet (Art. 41 Abs. 1 OR). Das gilt z.B. bei Hunden. Am 3. Mai kam er.") == [
        "Er haftet (Art. 41 Abs. 1 OR).", "Das gilt z.B. bei Hunden.", "Am 3. Mai kam er."]


def test_chunks_haben_overlap_aus_ganzen_saetzen():
    saetze = [f"Satz Nummer {i} erklärt einen Teil der Haftung im Alltag." for i in range(40)]
    chunks = vektoren.zerlegen(_seiten(" ".join(saetze)), groesse=400, overlap=120)
    assert len(chunks) > 5 and all(len(ch["text"]) <= 400 for ch in chunks)
    for vorher, nachher in zip(chunks, chunks[1:]):
        letzte = vektoren.saetze(vorher["text"])[-1]
        assert nachher["text"].startswith(vektoren.saetze(nachher["text"])[0])
        assert letzte in nachher["text"], "der letzte Satz des Chunks steht im nächsten (Overlap)"
        geteilt = sum(len(s) + 1 for s in vektoren.saetze(vorher["text"]) if s in nachher["text"])
        assert 0 < geteilt <= 120 + 1
    # ohne Overlap keine Wiederholung
    ohne = vektoren.zerlegen(_seiten(" ".join(saetze)), groesse=400, overlap=0)
    assert sum(len(ch["text"]) for ch in ohne) < sum(len(ch["text"]) for ch in chunks)
    assert len(ohne) < len(chunks)


def test_jeder_satz_ist_in_einem_chunk_vollstaendig():
    text = " ".join(f"Dies ist der Satz {i} mit etwas {'mehr ' * (i % 7)}Inhalt." for i in range(120))
    chunks = vektoren.zerlegen(_seiten(text), groesse=500, overlap=100)
    for s in vektoren.saetze(text):
        assert any(s in ch["text"] for ch in chunks), s


def test_ueberschriften_seiten_und_abschnitte():
    art41 = "Art. 41\n" + "Wer einem andern widerrechtlich Schaden zufügt, wird ihm zum Ersatze verpflichtet. " * 3
    art56 = "Art. 56\n" + "Für den von einem Tier angerichteten Schaden haftet, wer dasselbe hält. " * 3
    chunks = vektoren.zerlegen([{"seite": 3, "text": art41}, {"seite": 4, "text": art56}], groesse=300, overlap=100)
    assert chunks[0]["abschnitt"] == "Art. 41" and chunks[0]["seite_von"] == 3
    neu = [ch for ch in chunks if ch["abschnitt"] == "Art. 56"]
    assert neu and neu[0]["text"].startswith("Art. 56") and neu[0]["seite_von"] == 4
    assert "Ersatze" not in neu[0]["text"], "kein Overlap über eine neue Überschrift hinweg"
    # kurze Artikel teilen sich einen Chunk, der Abschnitt nennt beide
    zusammen = vektoren.zerlegen([{"seite": 3, "text": "Art. 41\nKurz eins."}, {"seite": 4, "text": "Art. 42\nKurz zwei."}],
                                 groesse=1200, overlap=100)
    assert len(zusammen) == 1 and zusammen[0]["abschnitt"] == "Art. 41; Art. 42"
    assert (zusammen[0]["seite_von"], zusammen[0]["seite_bis"]) == (3, 4)
    assert vektoren.chunk_dokument({"text": "Fortsetzung des Artikels.", "abschnitt": "Art. 41"}) == \
        "[Art. 41] Fortsetzung des Artikels."


def test_umbrochene_pdf_zeilen_sind_keine_ueberschriften():
    text = ("Tierhalterhaftung\nWer einem andern widerrechtlich Schaden zufügt, wird ihm zum\n"
            "Ersatze verpflichtet, sei es mit Absicht, sei es aus Fahrlässigkeit oder\n"
            "Unvorsichtigkeit gegenüber anderen Personen im Alltag.")
    chunks = vektoren.zerlegen(_seiten(text), groesse=800, overlap=100)
    assert len(chunks) == 1 and chunks[0]["abschnitt"] == "Tierhalterhaftung"
    assert "zum Ersatze verpflichtet" in chunks[0]["text"]


def test_sehr_langer_satz_wird_geteilt():
    chunks = vektoren.zerlegen(_seiten("wort " * 600), groesse=500, overlap=100)
    assert len(chunks) >= 6 and all(len(ch["text"]) <= 500 for ch in chunks)


def test_mock_embedding_aehnlich_bei_gleichen_staemmen():
    a, b, z = vektoren.einbetten(["Der Tierhalter haftet für sein Tier", "Haftung des Tierhalters",
                                  "Brüche kürzen und erweitern"])
    sim = lambda x, y: sum(p * q for p, q in zip(x, y))
    assert sim(a, b) > sim(a, z) and len(a) == vektoren.MOCK_DIMENSION


def test_anbieter_folgt_dem_chat_anbieter(monkeypatch):
    monkeypatch.setenv("ITS_EMBED_PROVIDER", "auto")
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    assert vektoren.anbieter() == "ollama" and vektoren.modell() == "qwen3-embedding:0.6b"
    assert vektoren.abfrage_praefix().startswith("Instruct:")
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    assert vektoren.anbieter() is None             # Anthropic bietet keine Embeddings an
    monkeypatch.setenv("ITS_EMBED_PROVIDER", "ollama")
    monkeypatch.setenv("ITS_EMBED_MODEL", "bge-m3")
    assert vektoren.modell() == "bge-m3" and vektoren.abfrage_praefix() == ""
    assert vektoren.sammlung_name() == "its-ollama-bge-m3"


def test_ollama_embed_aufruf(monkeypatch):
    monkeypatch.setenv("ITS_EMBED_PROVIDER", "ollama")
    monkeypatch.delenv("ITS_EMBED_MODEL", raising=False)
    gesehen = []

    def post(url, json=None, timeout=None, **kw):
        gesehen.append((url, json))
        return httpx.Response(200, json={"embeddings": [[0.1, 0.2]] * len(json["input"])},
                              request=httpx.Request("POST", url))
    monkeypatch.setattr(vektoren.httpx, "post", post)
    v = vektoren.einbetten(["a"] * 40, art="abfrage")
    assert len(v) == 40 and len(gesehen) == 2               # Stapel zu 32
    assert gesehen[0][0].endswith("/api/embed") and gesehen[0][1]["model"] == "qwen3-embedding:0.6b"
    assert gesehen[0][1]["input"][0].startswith("Instruct:") and gesehen[0][1]["input"][0].endswith("Query: a")


def test_ohne_vektordb_wird_nicht_indexiert():
    m = hochladen(c, "ohne.pdf", pdf(HAFTUNG))
    assert m["index_status"] == "aus"
    assert c.get("/api/teacher/vektordb").json()["aktiv"] is False
    assert c.post(f"/api/teacher/materialien/{m['id']}/indexieren").status_code == 409


# ---------------------------------------------------------------- mit ChromaDB

def test_upload_wird_indexiert_mit_allen_angaben(mit_vektordb):
    m = hochladen(c, "or-auszug.pdf", pdf(HAFTUNG), name="OR Auszug", tags=["Haftung"])
    vektoren.warten()
    d = c.get(f"/api/teacher/materialien/{m['id']}").json()
    assert d["index_status"] == "bereit", d["index_info"]
    info = d["index_info"]
    # a) Modell und Parameter
    assert info["anbieter"] == "mock" and info["modell"] == "mock-wortstamm-256" and info["dimension"] == 256
    assert info["chunk_groesse"] == vektoren.chunk_groesse() and info["overlap"] == vektoren.chunk_overlap()
    assert info["distanz"] == "cosine" and info["anzahl_chunks"] >= 1 and info["indexiert_am"] > 0
    # b)-d) Metadaten, Speicherort und Embeddings in Chroma
    sammlung = vektoren._sammlung(info["sammlung"])
    r = sammlung.get(where={"material_id": m["id"]}, include=["metadatas", "documents", "embeddings"])
    assert len(r["ids"]) == info["anzahl_chunks"]
    md = r["metadatas"][0]
    assert md["material_name"] == "OR Auszug" and md["dateiname"] == "or-auszug.pdf"
    assert md["embed_modell"] == "mock-wortstamm-256" and md["speicherort"] == d["speicherort"]
    assert md["seite_von"] >= 1 and len(r["embeddings"][0]) == 256
    st = c.get("/api/teacher/vektordb").json()
    assert st["aktiv"] and st["erreichbar"] and st["sammlung"] == info["sammlung"]


def test_suche_findet_die_passende_seite(mit_vektordb, monkeypatch):
    monkeypatch.setenv("ITS_CHUNK_GROESSE", "200")
    monkeypatch.setenv("ITS_CHUNK_OVERLAP", "40")
    m = hochladen(c, "suche.pdf", pdf(HAFTUNG), name="Suchtest")
    vektoren.warten()
    treffer = vektoren.suchen("Wer haftet für den Schaden eines Tieres, Tierhalter?", [m["id"]], k=2)
    assert treffer[0]["material_id"] == m["id"] and treffer[0]["seite_von"] == 2
    assert "Tier" in treffer[0]["text"] and treffer[0]["aehnlichkeit"] > treffer[-1]["aehnlichkeit"] - 1e-9
    # nur in den genannten Materialien
    andere = hochladen(c, "andere.txt", ("Brüche kürzen und erweitern, Zähler und Nenner. " * 5).encode())
    vektoren.warten()
    assert {t["material_id"] for t in vektoren.suchen("Tierhalter", [andere["id"]], k=3)} == {andere["id"]}


def test_neu_indexieren_ersetzt_und_modellwechsel_wird_erkannt(mit_vektordb, monkeypatch):
    m = hochladen(c, "neu.pdf", pdf(HAFTUNG))
    vektoren.warten()
    vorher = materialien.holen(m["id"])["index_info"]["anzahl_chunks"]
    monkeypatch.setenv("ITS_CHUNK_GROESSE", "200")
    monkeypatch.setenv("ITS_CHUNK_OVERLAP", "50")
    c.post(f"/api/teacher/materialien/{m['id']}/indexieren")
    vektoren.warten()
    info = materialien.holen(m["id"])["index_info"]
    assert info["anzahl_chunks"] > vorher and info["chunk_groesse"] == 200
    r = vektoren._sammlung().get(where={"material_id": m["id"]})
    assert len(r["ids"]) == info["anzahl_chunks"], "alte Chunks wurden ersetzt"
    monkeypatch.setenv("ITS_EMBED_MODEL", "anderes-modell")
    assert c.get(f"/api/teacher/materialien/{m['id']}").json()["index_status"] == "veraltet"
    assert c.post("/api/teacher/materialien/indexieren").json()["angestossen"] >= 1
    vektoren.warten()
    assert c.get(f"/api/teacher/materialien/{m['id']}").json()["index_status"] == "bereit"


def test_archivieren_behaelt_embeddings(mit_vektordb):
    m = hochladen(c, "bleibt.pdf", pdf(HAFTUNG))
    vektoren.warten()
    c.post(f"/api/teacher/materialien/{m['id']}/archivieren")
    assert len(vektoren._sammlung().get(where={"material_id": m["id"]})["ids"]) > 0


def test_fehler_bei_der_indexierung_wird_gemeldet(mit_vektordb, monkeypatch):
    def kaputt(*a, **k):
        raise vektoren.VektorFehler("Embedding-Modell fehlt")
    monkeypatch.setattr(vektoren, "einbetten", kaputt)
    m = hochladen(c, "kaputt.pdf", pdf(HAFTUNG))
    vektoren.warten()
    d = c.get(f"/api/teacher/materialien/{m['id']}").json()
    assert d["index_status"] == "fehler" and "Embedding-Modell fehlt" in d["index_info"]["fehler"]


def test_vektordb_nicht_erreichbar(monkeypatch):
    monkeypatch.setenv("ITS_VEKTOR_DB_URL", "http://127.0.0.1:9")
    vektoren._erreichbar.update(zeit=0.0)
    assert vektoren.erreichbar(neu=True) is False and vektoren.status()["fehler"]
    vektoren._erreichbar.update(zeit=0.0)
