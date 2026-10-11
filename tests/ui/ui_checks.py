"""Oberflächenprüfungen mit Playwright gegen eine laufende Instanz.

Läuft nicht in der normalen Testsuite (braucht Playwright und Chromium).
Jedes Szenario startet einen eigenen Server mit Mock-Provider, temporärer
Datenbank und Kopie der Lektionen, bei Bedarf mit verzögertem oder
scheiterndem Mock.

    pip install playwright && python -m playwright install chromium
    python tests/ui/ui_checks.py            # alle Szenarien
    python tests/ui/ui_checks.py t02 t06    # nur ausgewählte

Das Skript beendet sich mit Exit-Code 1, wenn eine Prüfung scheitert.
"""

import contextlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
SCENARIOS: dict = {}
RESULTS: list[tuple[str, bool, str]] = []


def scenario(name):
    def deco(fn):
        SCENARIOS[name] = fn
        return fn
    return deco


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextlib.contextmanager
def server(extra_lessons: dict | None = None, **env):
    """Startet uvicorn mit Mock-Provider in einem temporären Datenordner."""
    tmp = Path(tempfile.mkdtemp(prefix="its_ui_"))
    lessons = tmp / "lessons"
    shutil.copytree(ROOT / "app" / "lessons", lessons)
    for lid, data in (extra_lessons or {}).items():
        (lessons / f"{lid}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    port = _free_port()
    full_env = dict(os.environ)
    full_env.update({
        "LLM_PROVIDER": "mock", "ITS_DB_PATH": str(tmp / "its.db"),
        "ITS_LESSONS_DIR": str(lessons), "TEACHER_PASSWORD": "", "CLASS_CODE": "",
        "ITS_TOTAL_STEPS": "4",
    })
    full_env.update({k: str(v) for k, v in env.items()})
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)],
        cwd=ROOT, env=full_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                httpx.get(base + "/api/info", timeout=1)
                break
            except httpx.HTTPError:
                time.sleep(0.1)
        yield base
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        shutil.rmtree(tmp, ignore_errors=True)


def launch(pw):
    # KaTeX vom CDN ist für diese Prüfungen unwichtig; ohne Netz sofort abbrechen
    return pw.chromium.launch(args=["--host-resolver-rules=MAP cdn.jsdelivr.net 127.0.0.1:9"])


def check(name: str, cond: bool, detail: str = ""):
    RESULTS.append((name, bool(cond), detail))
    print(("  OK   " if cond else "  FEHLER ") + name + (f" – {detail}" if detail and not cond else ""))


def api_requests(page, pattern: str) -> list:
    """Sammelt alle Anfragen, deren URL das Muster enthält."""
    seen = []
    page.on("request", lambda r: seen.append(r.url) if pattern in r.url else None)
    return seen


# ---------------------------------------------------------------- Hilfen

def abmelden(page):
    page.click("#btn-logout")
    expect(page.locator("#view-start")).to_be_visible(timeout=10000)


def anmelden(page, base: str, name: str):
    if not page.locator("#view-start").is_visible():
        page.goto(base + "/")
    page.fill("#name", name)
    page.click("#btn-login")
    expect(page.locator("#view-home")).to_be_visible(timeout=10000)


def start_lernsequenz(page, base: str, name: str = "UI-Test", lesson: str = "haftungsrecht"):
    """Meldet sich an, startet eine Lektion und beantwortet die Einstufung."""
    anmelden(page, base, name)
    page.select_option("#lesson-select", lesson)
    page.click("#btn-start")
    expect(page.locator("#view-assess")).to_be_visible(timeout=30000)
    for _ in range(3):
        page.fill("#assess-answer", "weiss ich nicht")
        page.click("#btn-assess")
    expect(page.locator("#view-learn")).to_be_visible(timeout=60000)
    page.wait_for_selector("#waiting", state="detached", timeout=60000)


# ---------------------------------------------------------------- Szenarien

@scenario("t01")
def t01_nochmals_versuchen(pw):
    """T-01/T-12: Scheitern beide Aufrufe, erscheint eine Wahl mit echtem Materialabschnitt."""
    with server(ITS_MOCK_FAIL="THEORIE_SCHRITT") as base:
        page = launch(pw).new_page()
        start_lernsequenz(page, base)
        expect(page.locator(".wahlbox button[data-wahl='abschnitt']")).to_be_visible(timeout=30000)
        page.click(".wahlbox button[data-wahl='abschnitt']")
        page.wait_for_selector("#waiting", state="detached", timeout=30000)
        theorie = page.locator(".msg.tutor.theory").last
        expect(theorie).to_be_visible(timeout=30000)
        text = theorie.inner_text()
        check("T-01 Theorie-Fallback zeigt Materialtext",
              "Lektionsmaterial" in text and "Art. 41 OR" in text, text[:120])
        check("T-01 keine leere Ankündigung", "folgenden Abschnitt" not in text)


@scenario("t01b")
def t01_button_nochmals_versuchen(pw):
    """T-01/T-12: Ohne bestimmbaren Abschnitt erscheint die Wahl ohne «Abschnitt»."""
    leer = {"id": "leer", "titel": "Leere Lektion", "lernziele": ["Etwas verstehen"],
            "material": "Kurz.", "einstufungsfragen_fallback": ["Frage a zum Thema?", "Frage b zum Thema?",
                                                               "Frage c zum Thema?"]}
    with server(extra_lessons={"leer": leer}, ITS_MOCK_FAIL="THEORIE_SCHRITT") as base:
        page = launch(pw).new_page()
        start_lernsequenz(page, base, lesson="leer")
        expect(page.locator(".msg.tutor.fallback").last).to_contain_text("keine gute Erklärung", timeout=30000)
        labels = page.locator(".wahlbox button").all_inner_texts()
        check("T-12 ohne Abschnitt keine Ankündigung eines Abschnitts",
              labels == ["Nochmals versuchen", "Direkt zur Aufgabe", "Witz zum Thema"], str(labels))
        reqs = api_requests(page, "/wahl")
        page.click(".wahlbox button[data-wahl='nochmals']")
        expect(page.locator(".msg.tutor.fallback")).to_have_count(2, timeout=30000)
        check("T-01 «Nochmals versuchen» fordert den Schritt neu an", len(reqs) == 1, str(reqs))


AKTIONEN = ["#btn-answer", "#btn-ask", "#btn-theory", "#btn-deeper", "#btn-continue"]


def zur_aufgabe(page):
    """Klickt sich durch Theorie-Schritte bis zu einer Aufgabe."""
    for _ in range(4):
        if page.locator("#btn-answer").is_visible() and page.locator("#btn-answer").is_enabled():
            return
        page.click("#btn-continue")
        page.wait_for_selector("#waiting", state="detached", timeout=60000)
    raise AssertionError("Keine Aufgabe erreicht")


def sichtbare_aktionen_deaktiviert(page) -> bool:
    for sel in AKTIONEN:
        loc = page.locator(sel)
        if loc.is_visible() and loc.is_enabled():
            return False
    return True


@scenario("t02")
def t02_wartezustand(pw):
    """T-02 AK1-4: Warteanzeige, deaktivierte Buttons, Eingabe bleibt erhalten."""
    with server(ITS_MOCK_DELAY="5") as base:
        page = launch(pw).new_page()
        start_lernsequenz(page, base)
        page.wait_for_selector("#waiting", state="detached", timeout=60000)
        # Nach dem Theorie-Schritt läuft der Vorabruf im Hintergrund (5 s)
        check("T-02 Vorabruf blockiert die Oberfläche nicht",
              page.locator("#btn-continue").is_enabled() and page.locator("#waiting").count() == 0)
        zur_aufgabe(page)
        answers = api_requests(page, "/answer")
        chats = api_requests(page, "/chat")
        page.fill("#chat-input", "Anna haftet, weil alle vier Voraussetzungen erfüllt sind.")
        page.click("#btn-answer")
        page.click("#confidence-buttons button[data-v='7']")
        waiting = page.locator("#waiting")
        expect(waiting).to_be_visible()
        check("T-02 AK1 Warteanzeige sichtbar", "denkt nach" in waiting.inner_text())
        check("T-02 AK1 alle Aktionsbuttons deaktiviert", sichtbare_aktionen_deaktiviert(page))
        check("T-02 AK1 Sicherheitsbuttons deaktiviert oder ausgeblendet",
              not page.locator("#confidence-box").is_visible())
        # Während der Wartezeit tippen, Ctrl+Enter drücken, deaktivierte Buttons anklicken
        page.fill("#chat-input", "Vorbereiteter Text für später")
        page.press("#chat-input", "Control+Enter")
        page.press("#chat-input", "Enter")
        page.locator("#btn-ask").dispatch_event("click")
        page.locator("#btn-answer").dispatch_event("click")
        check("T-02 Eingabefeld bleibt beschreibbar", page.locator("#chat-input").is_editable())
        page.wait_for_selector("#waiting", state="detached", timeout=30000)
        wert = page.input_value("#chat-input")
        check("T-02 AK2 Text bleibt unverändert", wert.startswith("Vorbereiteter Text für später"), repr(wert))
        check("T-02 AK2/3 keine zusätzliche Anfrage", len(answers) == 1 and len(chats) == 0,
              f"answer={len(answers)} chat={len(chats)}")
        check("T-02 AK4 Buttons nach Ende wieder aktiv",
              any(page.locator(s).is_visible() and page.locator(s).is_enabled() for s in AKTIONEN))

        # AK4 mit fehlgeschlagener Anfrage: Verständnisfrage wird abgebrochen
        page.route("**/chat", lambda route: route.abort())
        page.fill("#chat-input", "Was heisst adäquat?")
        page.click("#btn-ask")
        expect(page.locator(".msg.tutor.error")).to_have_count(1, timeout=30000)
        page.wait_for_selector("#waiting", state="detached", timeout=30000)
        check("T-02 AK4 Buttons nach Fehler wieder aktiv", page.locator("#btn-ask").is_enabled())
        check("T-02 Fehlermeldung im Chat", page.locator(".msg.tutor.error").count() == 1)

        # Hinweis nach 20 Sekunden (mit längerer Verzögerung simuliert)
        page.unroute("**/chat")
        page.evaluate("SLOW_AFTER_MS")  # Konstante existiert
    with server(ITS_MOCK_DELAY="23") as base:
        page = launch(pw).new_page()
        page.goto(base + "/")
        page.evaluate("""() => { document.getElementById('view-learn').classList.remove('hidden');
                                  setChatBusy(true); }""")
        page.wait_for_timeout(20800)
        check("T-02 beruhigender Hinweis nach 20 Sekunden",
              "etwas länger" in page.locator("#waiting").inner_text())


@scenario("t04")
def t04_rollen(pw):
    """T-04 AK2/AK4: Startseite ohne Lehrpersonen-Elemente, Header-Name fest."""
    with server(TEACHER_PASSWORD="geheim", CLASS_CODE="BM2026") as base:
        browser = launch(pw)
        page = browser.new_page()
        page.goto(base + "/")
        page.wait_for_load_state("networkidle")
        body = page.locator("body").inner_text()
        check("T-04 AK2 kein Link zur Lehrpersonen-Sicht",
              not page.locator("#teacher-link").is_visible() and "Lehrpersonen-Sicht" not in body)
        check("T-04 AK2 kein Link zum Erfassen von Lektionen",
              page.locator("a[href*='/teacher']:visible").count() == 0)
        r = page.goto(base + "/teacher/lessons/new")
        check("T-04 direkter Aufruf führt zum Login", page.url.endswith("/teacher/login"), page.url)
        r = page.goto(base + "/static/teacher.html")
        check("T-04 statische Seite gesperrt", r.status == 404, str(r.status))
        # Als Lehrperson angemeldet: Link sichtbar
        page.goto(base + "/teacher/login")
        page.fill("#pw", "geheim")
        page.click("#btn")
        page.wait_for_url(base + "/teacher")
        page.goto(base + "/")
        expect(page.locator("#teacher-link")).to_be_visible()
        check("T-04 Lehrperson sieht den Link", True)
        browser.close()
    with server(ITS_TRUST_PROXY_HEADERS="true") as base:
        browser = launch(pw)
        ctx = browser.new_context(extra_http_headers={"X-Forwarded-User": "mia.muster",
                                                       "X-User-Roles": "student"})
        page = ctx.new_page()
        page.goto(base + "/")
        expect(page.locator("#name")).to_have_value("mia.muster")
        check("T-04 AK4 Namensfeld vorausgefüllt und schreibgeschützt",
              not page.locator("#name").is_editable())
        check("T-04 AK4 Rolle lernend: kein Lehrpersonen-Link",
              not page.locator("#teacher-link").is_visible())
        browser.close()


@scenario("t05")
def t05_sequenzen(pw):
    """T-05 AK1-3: Fortsetzen in Browser B, getrennte Namen, Neu beginnen archiviert."""
    with server() as base:
        browser = launch(pw)
        a = browser.new_context().new_page()
        start_lernsequenz(a, base, name="Lina")
        zur_aufgabe(a)
        frage_a = a.locator(".msg.tutor.question").last.inner_text()

        b = browser.new_context().new_page()     # anderer Browser
        anmelden(b, base, "  lina ")
        seqs = b.locator("#seq-list .seq")
        expect(seqs).to_have_count(1, timeout=10000)
        check("T-05 AK1 Sequenz in Browser B sichtbar", seqs.count() == 1)
        b.click("#seq-list button[data-act='resume']")
        expect(b.locator("#view-learn")).to_be_visible()
        frage_b = b.locator(".msg.tutor.question").last.inner_text()
        check("T-05 AK1 gleiche Stelle (gleiche Aufgabe)", frage_a == frage_b, f"{frage_a!r} / {frage_b!r}")
        check("T-05 AK1 Antwort möglich", b.locator("#btn-answer").is_enabled())

        # AK2: anderer Name im selben Browser sieht nichts von Lina
        b.goto(base + "/")
        expect(b.locator("#view-home")).to_be_visible()
        abmelden(b)
        anmelden(b, base, "Noah")
        expect(b.locator("#seq-empty")).to_be_visible(timeout=10000)
        check("T-05 AK2 Noah sieht keine fremden Sequenzen", b.locator("#seq-list .seq").count() == 0)

        # AK3: Neu beginnen archiviert nach Bestätigung
        abmelden(b)
        anmelden(b, base, "Lina")
        b.click("#seq-list button[data-act='restart']")
        expect(b.locator("#modal")).to_be_visible()
        b.click("#modal-ok")
        expect(b.locator("#view-assess")).to_be_visible(timeout=30000)
        b.goto(base + "/")
        expect(b.locator("#view-home")).to_be_visible()
        expect(b.locator("#seq-list .seq")).to_have_count(1, timeout=10000)
        check("T-05 AK3 nur noch die neue Sequenz in der Liste", b.locator("#seq-list .seq").count() == 1)
        rows = httpx.get(base + "/api/teacher/sessions").json()
        status = sorted(r["status"] for r in rows if r["name"].strip().lower() == "lina")
        check("T-05 AK3 Lehrperson sieht die archivierte Sequenz",
              status == ["aktiv", "archiviert"], str(status))
        browser.close()


@scenario("t06")
def t06_pausieren_abbrechen(pw):
    """T-06 AK1-3: Pausieren führt zur gleichen Stelle, Abbrechen mit Bestätigung."""
    with server(ITS_MOCK_DELAY="2") as base:
        browser = launch(pw)
        page = browser.new_context().new_page()
        start_lernsequenz(page, base, name="Pia")
        zur_aufgabe(page)
        frage = page.locator(".msg.tutor.question").last.inner_text()
        # Während einer Wartezeit sind beide Buttons deaktiviert
        page.fill("#chat-input", "Was heisst Widerrechtlichkeit?")
        page.click("#btn-ask")
        expect(page.locator("#waiting")).to_be_visible()
        check("T-06 Buttons während Wartezeit deaktiviert",
              page.locator("#btn-pause").is_disabled() and page.locator("#btn-abort").is_disabled())
        page.wait_for_selector("#waiting", state="detached", timeout=30000)
        page.click("#btn-pause")
        expect(page.locator("#home-banner")).to_contain_text("Gespeichert", timeout=10000)
        check("T-06 Status pausiert in der Übersicht",
              "pausiert" in page.locator("#seq-list").inner_text())
        # Erneut anmelden (neuer Browser) und fortsetzen
        p2 = browser.new_context().new_page()
        anmelden(p2, base, "Pia")
        p2.click("#seq-list button[data-act='resume']")
        expect(p2.locator(".msg.tutor.question").last).to_contain_text(frage.split("❓")[-1].strip(), timeout=10000)
        check("T-06 AK1 gleiche Stelle nach erneutem Anmelden", True)
        # Abbrechen verlangt Bestätigung
        p2.click("#btn-abort")
        expect(p2.locator("#modal")).to_be_visible()
        p2.click("#modal-cancel")
        check("T-06 AK2 Abbrechen ohne Bestätigung ändert nichts",
              p2.locator("#view-learn").is_visible())
        p2.click("#btn-abort")
        p2.click("#modal-ok")
        expect(p2.locator("#home-banner")).to_contain_text("abgebrochen", timeout=10000)
        rows = [r for r in httpx.get(base + "/api/teacher/sessions").json() if r["name"] == "Pia"]
        check("T-06 AK2 Lehrperson sieht Status abgebrochen",
              rows and rows[0]["status"] == "abgebrochen", str(rows))
        check("T-06 abgebrochene Sequenz ohne «Fortsetzen»",
              p2.locator("#seq-list button[data-act='resume']").count() == 0)
        ev = httpx.get(base + f"/api/teacher/sessions/{rows[0]['session_id']}").json()["events"]
        nach = [e["payload"]["nach"] for e in ev if e["type"] == "status_geaendert"]
        check("T-06 AK3 Events im Lernverlauf", nach == ["pausiert", "aktiv", "abgebrochen"], str(nach))
        browser.close()


@scenario("t07")
def t07_lektionen(pw):
    """T-07 AK1/AK2: Lektion ansehen, vorausgefüllt bearbeiten, löschen."""
    with server() as base:
        material = ("### Quelle: skript.pdf\n\n" + "Die Tierhalterhaftung nach Art. 56 OR. " * 5 +
                    "\n\n---\n\n### Quelle: notizen.docx\n\n" + "Eigene Notizen zur Haftung. " * 5 +
                    "\n\n---\n\nFreitext der Lehrperson.")
        r = httpx.post(base + "/api/teacher/lessons", json={
            "titel": "UI Lektion", "lernziele": ["Ziel A", "Ziel B"], "material": material,
            "quellen": [{"name": "skript.pdf", "chars": 195}, {"name": "notizen.docx", "chars": 140}],
            "einstellungen": {"bewertungsstrenge": "streng", "einsatzart": "vertiefung"}}).json()
        lid = r["id"]
        page = launch(pw).new_page()
        page.goto(base + "/teacher/lessons")
        row = page.locator(f"tr[data-id='{lid}']")
        expect(row).to_be_visible()
        row.locator("button[data-act='view']").click()
        expect(page.locator("#detail")).to_be_visible()
        detail = page.locator("#detail").inner_text()
        check("T-07 Ansehen zeigt Quellen, Material und Einstellungen",
              "skript.pdf" in detail and "Freitext der Lehrperson" in detail and "streng" in detail)
        row.locator("button[data-act='edit']").click()
        page.wait_for_url(f"**/teacher/lessons/{lid}/edit")
        expect(page.locator("#titel")).to_have_value("UI Lektion")
        namen = page.locator(".src-name").all_inner_texts()
        check("T-07 Editor mit Quellenliste vorausgefüllt", namen == ["skript.pdf", "notizen.docx"], str(namen))
        check("T-07 Freitext und Einstellungen vorausgefüllt",
              page.input_value("#material") == "Freitext der Lehrperson."
              and page.input_value("#s-bewertungsstrenge") == "streng"
              and page.input_value("#s-einsatzart") == "vertiefung")
        page.fill("#titel", "UI Lektion geändert")
        page.click("#btn-save")
        expect(page.locator("#result")).to_contain_text("Version 2", timeout=10000)
        d = httpx.get(base + f"/api/teacher/lessons/{lid}").json()
        check("T-07 AK1 Änderung gespeichert, Material unverändert",
              d["titel"] == "UI Lektion geändert" and d["material"] == material, d["titel"])
        page.goto(base + "/teacher/lessons")
        page.locator(f"tr[data-id='{lid}'] button[data-act='delete']").click()
        expect(page.locator("#modal")).to_be_visible()
        page.click("#modal-ok")
        expect(page.locator(f"tr[data-id='{lid}']")).to_have_count(0, timeout=10000)
        ids = [l["id"] for l in httpx.get(base + "/api/lessons").json()]
        check("T-07 AK2 gelöschte Lektion nicht mehr in der Auswahl", lid not in ids)


def beantworte(page, text: str, sicherheit: int | None = 7):
    page.fill("#chat-input", text)
    page.click("#btn-answer")
    if sicherheit and page.locator("#confidence-box").is_visible():
        page.click(f"#confidence-buttons button[data-v='{sicherheit}']")
    page.wait_for_selector("#waiting", state="detached", timeout=30000)


GUT = "Anna haftet, weil Schaden, Widerrechtlichkeit, Kausalzusammenhang und Verschulden vorliegen."


@scenario("d04")
def d04_niveau(pw):
    """D-04: Frage nach drei richtigen Antworten, Niveau selbst festhalten, Chat-Wunsch."""
    with server(ITS_TOTAL_STEPS="8") as base:
        page = launch(pw).new_page()
        start_lernsequenz(page, base, name="Nina")
        for _ in range(3):
            zur_aufgabe(page)
            beantworte(page, GUT)
            check("D-04 Niveau bleibt ohne Zustimmung", "Fortgeschritten" in page.inner_text("#prog-level"))
        frage = page.locator(".levelq")
        expect(frage).to_be_visible()
        check("D-04 Frage nach anspruchsvolleren Aufgaben", "anspruchsvollere" in frage.inner_text())
        frage.locator("button[data-a='hoeher_ja']").click()
        expect(page.locator("#prog-level")).to_contain_text("Vertieft", timeout=10000)
        check("D-04 «Ja, gerne» erhöht um eine Stufe", True)
        page.select_option("#level-control", "basic")
        expect(page.locator("#prog-level")).to_contain_text("Grundlagen", timeout=10000)
        check("D-04 Bedienelement hält das Niveau fest", page.input_value("#level-control") == "basic")
        page.fill("#chat-input", "Ich möchte auf dem Grundniveau bleiben.")
        page.click("#btn-ask")
        page.wait_for_selector("#waiting", state="detached", timeout=30000)
        check("D-04 Chat-Wunsch wird bestätigt",
              "bleiben auf dem Niveau" in page.locator(".msg.tutor").last.inner_text())


@scenario("lp")
def lp_lernverlauf(pw):
    """Lehrpersonen-Sicht: Lernverlauf mit allen neuen Event-Typen ohne Skriptfehler."""
    with server(ITS_MOCK_FAIL="EINSTUFUNG_BEWERTEN") as base:
        page = launch(pw).new_page()
        fehler = []
        page.on("pageerror", lambda e: fehler.append(str(e)))
        start_lernsequenz(page, base, name="Verlauf")
        zur_aufgabe(page)
        beantworte(page, "Anna haftet, weil Schaden da ist.")        # teilweise
        page.click(".wahlbox button[data-wahl='ergaenzen']")          # D-07
        page.wait_for_selector("#waiting", state="detached", timeout=30000)
        beantworte(page, "Dazu Widerrechtlichkeit, Kausalzusammenhang, Verschulden.", None)
        page.fill("#chat-input", "Ich möchte auf dem Grundniveau bleiben.")
        page.click("#btn-ask")
        page.wait_for_selector("#waiting", state="detached", timeout=30000)
        page.click("#btn-pause")
        expect(page.locator("#home-banner")).to_be_visible()
        page.goto(base + "/teacher")
        page.locator(".seq-item").first.click()
        detail = page.locator("#detail-events")
        expect(detail).to_contain_text("Status", timeout=10000)
        text = detail.inner_text()
        for stichwort in ("Fallback", "Einstufung", "Theorie", "Aufgabe", "Erwartet:", "teilweise richtig",
                          "Versuch 2", "Niveau", "pausiert", "Wahl nach teilweise richtiger Antwort"):
            check(f"Lernverlauf zeigt «{stichwort}»", stichwort in text)
        check("Lernverlauf ohne Skriptfehler", not fehler, "; ".join(fehler))
        page.click(".tabs button[data-tab='zeiten']")
        expect(page.locator("#timing-rows")).to_contain_text("Einstufung bewerten", timeout=10000)
        check("Messübersicht mit Fallback-Spalte (eigener Bereich)", True)


# ---------------------------------------------------------------- Phase 4

QUELLEN_LEKTION = {
    "id": "quellen", "titel": "Haftung mit Quellen", "lernziele": ["Haftung erklären"],
    "material": "### Quelle: Skript_Haftpflicht.pdf\n\n" + "Wer widerrechtlich Schaden zufügt, haftet nach "
                "Art. 41 OR, wenn Schaden, Widerrechtlichkeit, Kausalzusammenhang und Verschulden vorliegen. " * 4
                + "\n\n---\n\n### Quelle: Merkblatt.docx\n\n" + "Der Tierhalter haftet ohne Verschulden. " * 5,
    "einstufungsfragen_fallback": ["a?", "b?", "c?"],
}


def bis_zum_abschluss(page):
    for _ in range(20):
        if page.locator("#view-done").is_visible():
            return
        if page.locator(".wahlbox button[data-wahl='weiter']").count():
            page.click(".wahlbox button[data-wahl='weiter']")
            page.wait_for_selector("#waiting", state="detached", timeout=60000)
        elif page.locator("#btn-answer").is_visible() and page.locator("#btn-answer").is_enabled():
            beantworte(page, GUT, 8)
        elif page.locator("#btn-continue").is_visible():
            page.click("#btn-continue")
            page.wait_for_selector("#waiting", state="detached", timeout=60000)
        else:
            page.wait_for_timeout(200)
    raise AssertionError("Abschluss nicht erreicht")


@scenario("n01")
def n01_quellen(pw):
    """N-01: Theorieschritte zeigen eine Quellenzeile, ohne Quellenliste keine."""
    with server(extra_lessons={"quellen": QUELLEN_LEKTION}) as base:
        page = launch(pw).new_page()
        start_lernsequenz(page, base, name="Quellen", lesson="quellen")
        zeile = page.locator(".msg.tutor.theory .quelle").first
        expect(zeile).to_be_visible(timeout=30000)
        check("N-01 Quellenzeile unter der Theorie", zeile.inner_text() == "Quelle: Skript_Haftpflicht.pdf",
              zeile.inner_text())
        page2 = launch(pw).new_page()
        start_lernsequenz(page2, base, name="Ohne Quellen")
        expect(page2.locator(".msg.tutor.theory").first).to_be_visible(timeout=30000)
        check("N-01 ohne Quellenliste keine Zeile", page2.locator(".msg .quelle").count() == 0)


@scenario("n04")
def n04_selbsteinschaetzung(pw):
    """N-04: Rückmeldung nur bei deutlicher Abweichung, Kalibrierung in der Zusammenfassung."""
    with server() as base:
        page = launch(pw).new_page()
        start_lernsequenz(page, base, name="Kalibrierung")
        zur_aufgabe(page)
        beantworte(page, "weiss nicht", 9)
        expect(page.locator(".msg.tutor.selbst")).to_have_count(1, timeout=10000)
        check("N-04 Satz bei sicher und falsch", "sehr sicher" in page.locator(".msg.tutor.selbst").inner_text())
        beantworte(page, GUT, None)
        check("N-04 keine Rückmeldung ohne Abweichung", page.locator(".msg.tutor.selbst").count() == 1)
        bis_zum_abschluss(page)
        k = page.locator("#done-kalib")
        expect(k).to_be_visible()
        text = k.inner_text()
        check("N-04 Zusammenfassung zeigt beide Durchschnitte",
              "bei richtigen Antworten" in text and "teilweise richtigen" in text and "9 von 10" in text, text)


@scenario("n05")
def n05_eigener_verlauf(pw):
    """N-05: Lernende öffnen den eigenen Verlauf mit Schwächenliste und Sprung."""
    with server() as base:
        page = launch(pw).new_page()
        fehler = []
        page.on("pageerror", lambda e: fehler.append(str(e)))
        start_lernsequenz(page, base, name="Mein Verlauf")
        zur_aufgabe(page)
        beantworte(page, "weiss nicht", 9)
        beantworte(page, GUT, None)
        page.click("#btn-pause")
        expect(page.locator("#view-home")).to_be_visible(timeout=10000)
        page.locator(".seq button[data-act='verlauf']").click()
        expect(page.locator("#view-verlauf")).to_be_visible(timeout=10000)
        text = page.locator("#v-eintraege").inner_text()
        check("N-05 Verlauf zeigt Aufgabe, Antwort und Bewertung",
              "Deine Antwort" in text and "weiss nicht" in text and "Falsch" in text, text[:200])
        check("N-05 keine internen Angaben", "Adaption" not in text and "Erwartet" not in text)
        link = page.locator("#v-schwaechen a").first
        expect(link).to_be_visible()
        link.click()
        expect(page.locator("#v-eintraege .msg.markiert")).to_have_count(1, timeout=3000)
        check("N-05 Sprung zur Aufgabe markiert die Stelle", True)
        check("N-05 ohne Skriptfehler", not fehler, "; ".join(fehler))


@scenario("n02")
def n02_seitenleiste(pw):
    """N-02: Seitenleiste mit Filtern, Verlauf ohne Seitenwechsel, einklappbar."""
    with server() as base:
        for name, lektion in (("Anna Leiste", "haftungsrecht"), ("Ben Leiste", "bruchbegriff-verstehen-und-anwenden")):
            c = httpx.Client(base_url=base)
            c.post("/api/learner/login", json={"name": name})
            c.post("/api/session/start", json={"lesson_id": lektion})
        page = launch(pw).new_page()
        fehler = []
        page.on("pageerror", lambda e: fehler.append(str(e)))
        page.goto(base + "/teacher")
        expect(page.locator(".seq-item")).to_have_count(2, timeout=10000)
        url = page.url
        page.evaluate("window.__ohneNeuladen = true")   # verschwindet bei jedem Seitenwechsel
        page.locator(".seq-item").first.click()
        expect(page.locator("#detail-title")).to_contain_text("Lernverlauf von", timeout=10000)
        page.locator(".seq-item").nth(1).click()
        expect(page.locator("#detail-title")).to_contain_text("Ben Leiste", timeout=10000)
        check("N-02 AK1 Verlauf ohne Seitenwechsel",
              page.evaluate("window.__ohneNeuladen === true") and page.url.split("#")[0] == url, page.url)
        page.select_option("#f-lektion", "haftungsrecht")
        check("N-02 AK1 Lektionsfilter wirkt sofort", page.locator(".seq-item").count() == 1)
        page.select_option("#f-lektion", "")
        page.fill("#f-name", "ben")
        check("N-02 Namenssuche wirkt sofort", page.locator(".seq-item").count() == 1)
        page.fill("#f-name", "")
        page.select_option("#f-status", "abgeschlossen")
        check("N-02 Statusfilter wirkt sofort", page.locator(".seq-item").count() == 0)
        page.select_option("#f-status", "")
        page.set_viewport_size({"width": 400, "height": 800})
        check("N-02 Knopf für die Seitenleiste auf schmalen Bildschirmen", page.locator("#btn-sidebar").is_visible())
        page.click("#btn-sidebar")
        zu = not page.locator("#sidebar").is_visible()
        page.click("#btn-sidebar")
        auf = page.locator("#sidebar").is_visible()
        page.locator(".seq-item").first.click()
        expect(page.locator("#detail-title")).to_contain_text("Anna Leiste", timeout=10000)
        check("N-02 Seitenleiste klappt ein und nach der Auswahl wieder zu",
              zu and auf and not page.locator("#sidebar").is_visible())
        check("N-02 ohne Skriptfehler", not fehler, "; ".join(fehler))


# ---------------------------------------------------------------- Auftrag 2

def neue_lektion_im_editor(page, base, titel, material, ziele="Ziel A\nZiel B"):
    page.goto(base + "/teacher/lessons/new")
    page.click("#paste-box summary")
    page.fill("#material", material)
    page.fill("#titel", titel)
    page.fill("#ziele", ziele)
    page.click("#btn-save")
    expect(page.locator("#result")).to_contain_text("veröffentlicht", timeout=15000)


@scenario("t08")
def t08_kontext(pw):
    """T-08 AK2/AK4: Editor warnt bei zu grossem Material, Lernverlauf zeigt die Kontextwerte."""
    gross = ("Die Kausalhaftung gilt ohne Verschulden, etwa für Tierhalter nach Art. 56 OR. " * 400)
    with server(LLM_PROVIDER="ollama", OLLAMA_NUM_CTX="4096", OLLAMA_BASE_URL="http://127.0.0.1:9") as base:
        page = launch(pw).new_page()
        neue_lektion_im_editor(page, base, "Sehr grosse Lektion", gross)
        warnung = page.locator("#kontext-warnung")
        check("T-08 AK4 Editor warnt beim Speichern", warnung.is_visible() and "Kontextfensters" in warnung.inner_text(),
              page.locator("#result").inner_text()[:200])
        ids = [l["id"] for l in httpx.get(base + "/api/lessons").json()]
        check("T-08 AK4 Lektion trotzdem gespeichert", "sehr-grosse-lektion" in ids, str(ids))
        page.goto(base + "/teacher/lessons")
        zeile = page.locator("tr[data-id='sehr-grosse-lektion'] .groesse")
        expect(zeile).to_contain_text("Kontextfensters")
        check("T-08 Lektionsverwaltung zeigt die Grösse", "⚠️" in zeile.inner_text())
        # Fallback mit Kontextangaben (Ollama nicht erreichbar, Prompt zu gross)
        c = httpx.Client(base_url=base, timeout=30)
        c.post("/api/learner/login", json={"name": "Kontext"})
        sid = c.post("/api/session/start", json={"lesson_id": "sehr-grosse-lektion"}).json()["session_id"]
        c.post(f"/api/session/{sid}/assess", json={"answers": ["a", "b", "c"]})
        c.post(f"/api/session/{sid}/next")
        page.goto(base + f"/teacher#{sid}")
        detail = page.locator("#detail-events")
        expect(detail).to_contain_text("Kontext zu gross", timeout=10000)
        text = detail.inner_text()
        check("T-08 AK2 Lernverlauf zeigt Länge, Maximum und Überschreitung",
              "Maximum 4096" in text and "Überschreitung" in text, text[:300])


@scenario("t10")
def t10_einstufung(pw):
    """T-10: Die Einstufung zeigt nie «[object Object]»."""
    with server() as base:
        page = launch(pw).new_page()
        page.goto(base + "/")
        page.evaluate("""() => { show('view-assess');
            questions = [{Frage: 'Was weisst du über Haftung?', Schwierigkeit: 'leicht'}, {x: 1}, 'Normale Frage?'];
            qIndex = 0; renderAssess(); }""")
        t1 = page.inner_text("#assess-question")
        page.evaluate("() => { qIndex = 1; renderAssess(); }")
        t2 = page.inner_text("#assess-question")
        check("T-10 Objekt mit Fragefeld wird als Text gezeigt", t1 == "Was weisst du über Haftung?", t1)
        check("T-10 unbrauchbares Objekt: verständliche Meldung statt [object Object]",
              "object" not in t2 and "nicht angezeigt" in t2, t2)


@scenario("t11")
def t11_bewertungsschleife(pw):
    """T-11 AK1-3: Nochmals bewerten ohne Neueingabe, Wahl nach dem zweiten Fehler, auch nach Pause."""
    with server(ITS_MOCK_FAIL="ANTWORT_BEWERTEN") as base:
        browser = launch(pw)
        page = browser.new_context().new_page()
        start_lernsequenz(page, base, name="Schleife")
        zur_aufgabe(page)
        beantworte(page, GUT, 6)
        knopf = page.locator(".wahlbox button[data-wahl='nochmals_bewerten']")
        expect(knopf).to_be_visible(timeout=10000)
        check("T-11 AK1 Button «Nochmals bewerten lassen»", knopf.inner_text() == "Nochmals bewerten lassen")
        reqs = []
        page.on("request", lambda r: reqs.append(r.post_data or "") if "/wahl" in r.url else None)
        knopf.click()
        page.wait_for_selector("#waiting", state="detached", timeout=30000)
        check("T-11 AK1 erneut eingereicht ohne neu zu tippen", reqs and "nochmals_bewerten" in reqs[0], str(reqs))
        labels = page.locator(".wahlbox button").all_inner_texts()
        check("T-11 AK2 drei Möglichkeiten nach dem zweiten Fehler",
              labels == ["Nochmals versuchen", "Musterlösung ansehen und weiter", "Ohne Bewertung weiter"], str(labels))
        meldungen = [m for m in page.locator(".msg.tutor.mid").all_inner_texts() if "⚠️" in m]
        check("T-11 keine identische Meldung hintereinander", len(set(meldungen)) == len(meldungen), str(meldungen))
        page.click("#btn-pause")
        expect(page.locator("#home-banner")).to_be_visible(timeout=10000)
        p2 = browser.new_context().new_page()
        anmelden(p2, base, "Schleife")
        p2.click("#seq-list button[data-act='resume']")
        expect(p2.locator(".wahlbox button")).to_have_count(3, timeout=10000)
        check("T-11 AK3 Wahl nach dem Fortsetzen wieder da", True)
        anzahl = p2.locator(".msg.tutor").count()
        p2.click(".wahlbox button[data-wahl='ohne_bewertung']")
        p2.wait_for_selector("#waiting", state="detached", timeout=30000)
        expect(p2.locator(".msg.tutor")).not_to_have_count(anzahl, timeout=10000)
        check("T-11 AK2 «Ohne Bewertung weiter» führt zum nächsten Schritt",
              p2.locator(".msg.tutor").count() > anzahl and "0 falsch" in p2.inner_text("#prog-badges"),
              p2.inner_text("#prog-badges"))
        browser.close()


@scenario("t12")
def t12_fallback_wahl(pw):
    """T-12 AK1/AK3: Vier Möglichkeiten bei der Aufgabe, Witz aus der Liste, Buttons gesperrt beim Warten."""
    with server(ITS_MOCK_FAIL="NAECHSTE_AUFGABE,WITZ", ITS_MOCK_DELAY="1") as base:
        page = launch(pw).new_page()
        start_lernsequenz(page, base, name="Fallback")
        page.click("#btn-continue")                                   # Theorie gelesen
        expect(page.locator(".wahlbox button")).to_have_count(4, timeout=30000)
        labels = page.locator(".wahlbox button").all_inner_texts()
        check("T-12 AK1 vier Möglichkeiten", labels == ["Nochmals versuchen",
              "Abschnitt in eigenen Worten zusammenfassen", "Zum nächsten Thema", "Witz zum Thema"], str(labels))
        check("T-12 freundlicher Text", "keine gute Aufgabe eingefallen" in page.locator(".msg.tutor.fallback").last.inner_text())
        page.click(".wahlbox button[data-wahl='witz']")
        check("T-12 Buttons während der Anfrage deaktiviert",
              page.locator("#waiting").is_visible() and all(b.is_disabled() for b in page.locator(".wahlbox button").all()))
        expect(page.locator(".msg.tutor.witz")).to_have_count(1, timeout=30000)
        check("T-12 AK3 Witz aus der hinterlegten Liste", "Mock-Witz" not in page.locator(".msg.tutor.witz").inner_text())
        labels = page.locator(".wahlbox button").all_inner_texts()
        check("T-12 danach die übrigen Möglichkeiten", len(labels) == 3 and "Witz zum Thema" not in labels, str(labels))
        page.click(".wahlbox button[data-wahl='abschnitt']")
        page.wait_for_selector("#waiting", state="detached", timeout=30000)
        check("T-12 Abschnitt wird als Aufgabe angezeigt",
              "eigenen Worten" in page.locator(".msg.tutor.question").last.inner_text()
              and page.locator("#btn-answer").is_visible())


KATEX_DIR = os.getenv("ITS_KATEX_DIR")   # optional: lokal entpacktes npm-Paket katex@0.16.11


def katex_lokal(page) -> bool:
    """Bedient die KaTeX-Dateien vom CDN aus einem lokalen Ordner (für AK zu Formeln)."""
    if not KATEX_DIR or not Path(KATEX_DIR, "dist", "katex.min.js").exists():
        return False
    page.route("https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/**", lambda route: route.fulfill(
        path=str(Path(KATEX_DIR, "dist", route.request.url.split("/dist/", 1)[1]))))
    return True


FORMAT_TEXT = ("### Grundlagen und Einstieg\nFür den Einstieg sind folgende Konzepte wichtig:\n\n"
               "- Welle-Teilchen-Dualismus\n- **Superposition** mit $x^2$\n\n"
               "1. Zuerst messen\n2. Dann auswerten\n\nSchluss <script>window.__xss = 1</script>"
               "<img src=x onerror=\"window.__xss = 2\">")


@scenario("t13")
def t13_formatierung(pw):
    """T-13 AK1-3: Titel, Absatz, Listen, Fettdruck; kein eingeschleustes HTML; Formeln mit KaTeX."""
    with server() as base:
        page = launch(pw).new_page()
        mit_katex = katex_lokal(page)
        page.goto(base + "/")
        page.wait_for_load_state("networkidle")
        page.evaluate("""t => { show('view-learn'); addMsg('tutor theory', t, 'Tutor – Theorie'); }""", FORMAT_TEXT)
        msg = page.locator(".msg.tutor.theory").last
        check("T-13 AK1 Zwischentitel als eigenes Element",
              msg.locator("h4.fmt-titel").inner_text() == "Grundlagen und Einstieg")
        check("T-13 AK1 Absatz nach dem Titel", msg.locator(".fmt p").first.inner_text().startswith("Für den Einstieg"))
        check("T-13 AK1 Aufzählung als Liste", msg.locator(".fmt ul > li").count() == 2)
        check("T-13 AK1 nummerierte Liste", msg.locator(".fmt ol > li").count() == 2)
        check("T-13 AK1 Fettdruck", msg.locator(".fmt strong").inner_text() == "Superposition")
        check("T-13 AK2 kein Skript ausgeführt", page.evaluate("window.__xss") is None)
        check("T-13 AK2 kein img-Element, Text sichtbar",
              msg.locator("img, script").count() == 0 and "<script>" in msg.inner_text())
        if mit_katex:
            expect(msg.locator(".katex")).to_have_count(1, timeout=5000)
            check("T-13 AK3 Formel nach der Formatierung von KaTeX gesetzt", True)
        else:
            print("  HINWEIS KaTeX lokal nicht verfügbar (ITS_KATEX_DIR), AK3 nicht geprüft")
        # Gleiche Darstellung im Lernverlauf der Lehrperson
        page.goto(base + "/teacher")
        html = page.evaluate("t => ITSFormat.html(t)", FORMAT_TEXT)
        check("T-13 Lehrpersonen-Sicht nutzt dieselbe Formatierung",
              "<h4 class=\"fmt-titel\">" in html and "&lt;script&gt;" in html and "<img" not in html)


@scenario("t14")
def t14_verlauf_fortsetzen(pw):
    """T-14 AK1-3: Nach Pausieren und Fortsetzen im zweiten Browser steht der ganze Dialog im Chat."""
    with server() as base:
        browser = launch(pw)
        a = browser.new_context().new_page()
        start_lernsequenz(a, base, name="Verlauf")
        a.fill("#chat-input", "Was heisst adäquat?")
        a.click("#btn-ask")
        a.wait_for_selector("#waiting", state="detached", timeout=30000)
        zur_aufgabe(a)
        beantworte(a, "Schaden ist da.", 4)                    # teilweise
        vorher = [m for m in a.locator("#chat .msg").all_inner_texts()]
        a.click("#btn-pause")
        expect(a.locator("#home-banner")).to_be_visible(timeout=10000)
        b = browser.new_context().new_page()
        llm_anfragen = api_requests(b, "/next")
        anmelden(b, base, "Verlauf")
        b.click("#seq-list button[data-act='resume']")
        expect(b.locator("#view-learn")).to_be_visible(timeout=10000)
        nachher = b.locator("#chat .msg").all_inner_texts()
        eigene = [m for m in nachher if m.startswith("Du (Antwort)")]
        check("T-14 AK1 eigene Antwort wieder im Chat", any("Schaden ist da." in m for m in eigene), str(eigene))
        check("T-14 AK1 Verständnisfrage und Antwort wieder im Chat",
              any("Was heisst adäquat?" in m for m in nachher) and len(nachher) >= len(vorher) - 1,
              f"{len(nachher)} / {len(vorher)}")
        reihen = [m.split("\n")[0] for m in nachher]
        check("T-14 AK2 Reihenfolge: Theorie vor Aufgabe vor Antwort vor Feedback",
              reihen.index("Tutor – Theorie") < reihen.index("Du (Antwort)")
              < max(i for i, r in enumerate(reihen) if r == "Tutor"), str(reihen))
        check("T-14 Trennlinie mit Datum", "fortgesetzt am" in b.locator(".trenner").inner_text())
        text = b.locator("#chat").inner_text()
        check("T-14 AK3 keine internen Einträge", "Regelverstoss" not in text and "Vorbereiteter" not in text)
        check("T-14 AK4 kein neuer Schritt beim Fortsetzen", llm_anfragen == [], str(llm_anfragen))
        check("T-14 offener Schritt mit passenden Buttons",
              b.locator(".wahlbox button").count() > 0 or b.locator("#btn-answer").is_visible())
        browser.close()


@scenario("t15")
def t15_dialoge(pw):
    """T-15/T-16: Eindeutige Dialogbuttons, Niveau-Auswahl ohne «festhalten»."""
    with server() as base:
        page = launch(pw).new_page()
        start_lernsequenz(page, base, name="Dialog")
        page.click("#btn-abort")
        expect(page.locator("#modal")).to_be_visible()
        ok, zurueck = page.inner_text("#modal-ok"), page.inner_text("#modal-cancel")
        check("T-15 AK1 Abbrechen-Dialog beschriftet", ok == "Ja, Lektion abbrechen" and zurueck == "Nein, weiterlernen",
              f"{ok} / {zurueck}")
        check("T-15 sichere Wahl als Hauptbutton, Handlung rot umrandet",
              "danger" in page.get_attribute("#modal-ok", "class")
              and "secondary" not in (page.get_attribute("#modal-cancel", "class") or ""))
        page.click("#modal-cancel")
        check("T-15 «Nein, weiterlernen» bleibt in der Lektion", page.locator("#view-learn").is_visible())
        optionen = page.locator("#level-control option").all_inner_texts()
        check("T-16 AK1 Niveau-Einträge ohne «festhalten»",
              optionen == ["Automatisch (empfohlen)", "Grundlagen", "Fortgeschritten", "Vertieft"], str(optionen))
        check("T-16 Hilfetext beim Dropdown", "bis du wieder" in page.inner_text("#level-box"))


@scenario("d07")
def d07_teilweise(pw):
    """D-07 AK1/AK2/AK4: Drei Möglichkeiten nach «teilweise», Ergänzen mit bisheriger Antwort, Pause."""
    with server() as base:
        browser = launch(pw)
        page = browser.new_context().new_page()
        start_lernsequenz(page, base, name="Teilweise")
        zur_aufgabe(page)
        beantworte(page, "Anna haftet, weil Schaden da ist.", 9)
        knoepfe = page.locator(".wahlbox button")
        expect(knoepfe).to_have_count(3, timeout=10000)
        check("D-07 AK1 drei Möglichkeiten",
              knoepfe.all_inner_texts() == ["Antwort ergänzen", "Lösung ansehen", "Weiter zur nächsten Aufgabe"],
              str(knoepfe.all_inner_texts()))
        check("D-07 AK1 «Antwort ergänzen» ist Hauptbutton",
              "secondary" not in page.get_attribute(".wahlbox button[data-wahl='ergaenzen']", "class"))
        check("D-07 AK1 keine automatische Weiterleitung",
              not page.locator("#btn-continue").is_visible() and "Der Kern stimmt" not in page.inner_text("#chat"))
        page.click("#btn-pause")
        expect(page.locator("#home-banner")).to_be_visible(timeout=10000)
        p2 = browser.new_context().new_page()
        anmelden(p2, base, "Teilweise")
        p2.click("#seq-list button[data-act='resume']")
        expect(p2.locator(".wahlbox button")).to_have_count(3, timeout=10000)
        check("D-07 AK4 nach dem Fortsetzen wieder drei Möglichkeiten", True)
        p2.click(".wahlbox button[data-wahl='ergaenzen']")
        p2.wait_for_selector("#waiting", state="detached", timeout=30000)
        check("D-07 AK2 bisherige Antwort steht zur Bearbeitung bereit",
              p2.input_value("#chat-input") == "Anna haftet, weil Schaden da ist." and p2.locator("#btn-answer").is_enabled())
        p2.fill("#chat-input", GUT)
        p2.click("#btn-answer")
        p2.wait_for_selector("#waiting", state="detached", timeout=30000)
        check("D-07 AK2 Ergänzung ohne erneute Sicherheitsfrage bewertet",
              "Richtig" in p2.locator(".msg.tutor.good").last.inner_text())
        browser.close()


@scenario("d11")
def d11_kopie(pw):
    """D-11 AK1/AK4: Kopierte Theorie wird nicht bewertet, die Lehrperson sieht das Event."""
    with server() as base:
        page = launch(pw).new_page()
        start_lernsequenz(page, base, name="Kopie")
        theorie = page.locator(".msg.tutor.theory .fmt").first.inner_text()
        zur_aufgabe(page)
        beantworte(page, theorie, 8)
        meldung = page.locator(".msg.tutor.mid").last.inner_text()
        check("D-11 AK1 Hinweis statt Bewertung", "eigenen Worten" in meldung
              and page.locator(".msg.tutor.good, .msg.tutor.bad").count() == 0, meldung)
        check("D-11 Antwort bleibt zum Umformulieren stehen", page.input_value("#chat-input").strip() != "")
        page.goto(base + "/teacher")
        page.locator(".seq-item").first.click()
        expect(page.locator("#detail-events")).to_contain_text("Kopie erkannt", timeout=10000)
        check("D-11 AK4 Event im Lernverlauf der Lehrperson", True)


@scenario("t17")
def t17_duplizieren(pw):
    """T-17 AK3: Button «Duplizieren», Weiterleitung in den Editor, Titel der Kopie."""
    with server() as base:
        page = launch(pw).new_page()
        page.goto(base + "/teacher/lessons")
        page.locator("tr[data-id='haftungsrecht'] button[data-act='duplicate']").click()
        page.wait_for_url("**/edit?dupliziert=1", timeout=10000)
        titel = page.locator("#titel")
        expect(titel).to_have_value("Haftpflichtrecht – Grundlagen (ABU/BM) (Kopie)", timeout=10000)
        check("T-17 AK3 Kopie öffnet sich im Editor mit Titel «(Kopie)»", "/teacher/lessons/" in page.url)
        check("T-17 Hinweis auf die Kopie", "Kopie angelegt" in page.inner_text("#edit-notice"))
        ids = [l["id"] for l in httpx.get(base + "/api/lessons").json()]
        check("T-17 AK2 Kopie sofort in der Lektionsauswahl", any(i.endswith("-kopie") for i in ids), str(ids))


@scenario("t18")
def t18_titel_lernziele(pw):
    """T-18 AK1/AK3: Ohne Titel weder Vorschlag noch Speichern, Kennzeichnung «experimentell»."""
    with server() as base:
        page = launch(pw).new_page()
        page.goto(base + "/teacher/lessons/new")
        page.click("#paste-box summary")
        page.fill("#material", "Die Verschuldenshaftung nach Art. 41 OR verlangt vier Voraussetzungen. " * 4)
        check("T-18 AK1 Vorschlag ohne Titel gesperrt", page.locator("#btn-suggest").is_disabled())
        page.fill("#ziele", "Ziel A")
        vorher = len(httpx.get(base + "/api/lessons").json())
        page.click("#btn-save")
        page.wait_for_timeout(500)
        check("T-18 AK1 Speichern ohne Titel abgelehnt", "Titel" in page.inner_text("#result")
              and len(httpx.get(base + "/api/lessons").json()) == vorher)
        check("T-18 AK3 Kennzeichnung «experimentell» sichtbar", page.locator("#exp-ziele").is_visible())
        page.fill("#titel", "Verschuldenshaftung")
        check("T-18 Vorschlag mit Titel möglich", page.locator("#btn-suggest").is_enabled())
        page.click("#btn-suggest")
        expect(page.locator("#result")).to_contain_text("experimentell", timeout=10000)
        check("T-18 Titel bleibt der eigene", page.input_value("#titel") == "Verschuldenshaftung"
              and page.input_value("#ziele").count("\n") >= 2)


def run(names):
    with sync_playwright() as pw:
        for name in names:
            print(f"Szenario {name}: {SCENARIOS[name].__doc__.strip().splitlines()[0]}")
            try:
                SCENARIOS[name](pw)
            except Exception as e:   # Szenario abgebrochen = Fehler
                check(f"{name} lief durch", False, f"{type(e).__name__}: {e}")
    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(failed)} von {len(RESULTS)} Prüfungen bestanden.")
    return 1 if failed else 0


if __name__ == "__main__":
    wanted = sys.argv[1:] or list(SCENARIOS)
    sys.exit(run(wanted))
