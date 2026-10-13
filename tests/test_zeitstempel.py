"""T-26: Zeitstempel für die Liste der Lernsequenzen und den Kopf der Detailansicht."""

from fastapi.testclient import TestClient

from app.main import app


def test_liste_und_detail_liefern_start_und_letzte_aktivitaet():
    c = TestClient(app)
    c.post("/api/learner/login", json={"name": "Zeitstempel"})
    sid = c.post("/api/session/start", json={"lesson_id": "haftungsrecht"}).json()["session_id"]
    zeile = next(s for s in c.get("/api/teacher/sessions").json() if s["session_id"] == sid)
    assert zeile["created_at"] <= zeile["updated_at"]
    kopf = c.get(f"/api/teacher/sessions/{sid}").json()["session"]
    assert kopf["created_at"] == zeile["created_at"] and kopf["updated_at"] >= zeile["created_at"]


def test_oberflaeche_formatiert_zentral_im_schweizer_format():
    s = open("static/teacher.html", encoding="utf-8").read()
    assert 'toLocaleString("de-CH", ZEIT_FORMAT)' in s
    assert "Letzte Aktivität: " in s and "Start ${esc(zeitpunkt(s.created_at))}" in s
    assert "(b.created_at || 0) - (a.created_at || 0)" in s          # neueste zuoberst
