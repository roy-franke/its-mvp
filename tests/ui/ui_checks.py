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
import re
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
AKTUELLE_DB: Path | None = None       # Datenbank des zuletzt gestarteten Servers (T-26)
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
    global AKTUELLE_DB
    AKTUELLE_DB = tmp / "its.db"
    full_env = dict(os.environ)
    full_env.update({
        "LLM_PROVIDER": "mock", "ITS_DB_PATH": str(tmp / "its.db"),
        "ITS_LESSONS_DIR": str(lessons), "TEACHER_PASSWORD": "", "CLASS_CODE": "",
        "ITS_TOTAL_STEPS": "4", "ITS_MATERIAL_DIR": str(tmp / "materialien"), "ITS_VEKTOR_DB_URL": "",
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


# T-25 AK3: Die Legende nennt nie einen Button, der nicht sichtbar ist. Die
# Prüfung läuft in allen Szenarien bei jedem Schritt mit (zur_aufgabe, beantworte).
LEGENDE_JS = r"""() => {
  const leg = document.getElementById("legende");
  if (!leg || leg.classList.contains("hidden") || leg.closest(".hidden")) return {genannt: [], fehlt: []};
  const sicht = el => !el.classList.contains("hidden") && !el.closest(".hidden");
  const labels = [...document.querySelectorAll("#view-learn .btnrow button, #chat .wahlbox button")]
    .filter(sicht).map(b => b.textContent.replace(/[^\p{L}\p{N} ,.!?-]/gu, "").replace(/\s+/g, " ").trim());
  const genannt = [...leg.textContent.matchAll(/«([^»]+)»/g)].map(m => m[1].trim());
  return {genannt, fehlt: genannt.filter(n => !labels.includes(n)), text: leg.textContent};
}"""
LEGENDE_FEHLER: list[str] = []


def legende(page) -> dict:
    return page.evaluate(LEGENDE_JS)


def legende_pruefen(page, wo: str = ""):
    """Sammelt Abweichungen; jedes Szenario meldet sie am Ende (siehe run)."""
    try:
        r = legende(page)
    except Exception:          # Seite gerade im Wechsel oder geschlossen
        return
    if r["fehlt"]:
        LEGENDE_FEHLER.append(f"{wo}: nennt {r['fehlt']} – «{r.get('text', '')}»")


def zur_aufgabe(page):
    """Klickt sich durch Theorie-Schritte bis zu einer Aufgabe."""
    for _ in range(4):
        legende_pruefen(page, "zur_aufgabe")
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
    """T-07 AK1/AK2: Lektion ansehen, vorausgefüllt bearbeiten, archivieren."""
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
        page.locator(f"tr[data-id='{lid}'] button[data-act='archive']").click()
        expect(page.locator("#modal")).to_be_visible()
        page.click("#modal-ok")
        expect(page.locator(f"tr[data-id='{lid}']")).to_have_count(0, timeout=10000)
        ids = [l["id"] for l in httpx.get(base + "/api/lessons").json()]
        check("T-07 AK2 archivierte Lektion nicht mehr in der Auswahl", lid not in ids)


def beantworte(page, text: str, sicherheit: int | None = 7):
    legende_pruefen(page, "vor der Antwort")
    page.fill("#chat-input", text)
    page.click("#btn-answer")
    if sicherheit and page.locator("#confidence-box").is_visible():
        page.click(f"#confidence-buttons button[data-v='{sicherheit}']")
    page.wait_for_selector("#waiting", state="detached", timeout=30000)
    legende_pruefen(page, "nach der Bewertung")


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
        # Seit D-15 steht «Ich sehe das anders» als Zusatz in derselben Box
        knoepfe = page.locator(".wahlbox button:not([data-wahl='widerspruch'])")
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
        expect(p2.locator(".wahlbox button:not([data-wahl='widerspruch'])")).to_have_count(3, timeout=10000)
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


@scenario("t19")
def t19_material_pruefen(pw):
    """T-19 AK1/AK2: Nach Vorschlag und Prüfung nur die Meldung der Prüfung, Formular unverändert."""
    with server() as base:
        page = launch(pw).new_page()
        page.goto(base + "/teacher/lessons/new")
        page.click("#paste-box summary")
        page.fill("#material", "Die Verschuldenshaftung nach Art. 41 OR verlangt vier Voraussetzungen, "
                               "zum Beispiel beim Velounfall, weil das Gesetz alle vier verlangt. " * 4)
        page.fill("#titel", "Verschuldenshaftung")
        page.click("#btn-suggest")
        expect(page.locator("#result")).to_contain_text("Lernziele vorgeschlagen", timeout=10000)
        felder = ["#titel", "#ziele", "#material", "#hinweise", "#s-einsatzart", "#s-niveauanpassung",
                  "#s-bewertungsstrenge"]
        vorher = [page.input_value(f) for f in felder]
        page.click("#btn-check")
        expect(page.locator("#check-result")).to_be_visible(timeout=10000)
        meldung = page.inner_text("#result")
        check("T-19 AK1 nur die Meldung der Prüfung sichtbar",
              meldung.startswith("Prüfung abgeschlossen") and "vorgeschlagen" not in meldung
              and page.locator("#result").count() == 1, meldung)
        check("T-19 Kennzeichnung «experimentell» bei der Prüfung", page.locator("#exp-check").is_visible())
        check("T-19 AK2 Formularzustand unverändert", [page.input_value(f) for f in felder] == vorher)


@scenario("t20")
def t20_archivieren(pw):
    """T-20 AK1/AK4: Sequenzen einzeln und gemeinsam archivieren und wiederherstellen; Lektionen."""
    with server() as base:
        for name in ("Archiv Eins", "Archiv Zwei", "Archiv Drei"):
            c = httpx.Client(base_url=base)
            c.post("/api/learner/login", json={"name": name})
            c.post("/api/session/start", json={"lesson_id": "haftungsrecht"})
        page = launch(pw).new_page()
        fehler = []
        page.on("pageerror", lambda e: fehler.append(str(e)))
        page.goto(base + "/teacher")
        expect(page.locator(".seq-item")).to_have_count(3, timeout=10000)
        boxen = page.locator(".seq-wahl")
        boxen.nth(0).check()
        boxen.nth(1).check()
        page.click("#btn-archivieren-mehrere")
        expect(page.locator("#modal")).to_be_visible()
        check("T-20 Bestätigung mit eindeutigen Buttons", page.inner_text("#modal-ok") == "Ja, Sequenzen archivieren"
              and page.inner_text("#modal-cancel") == "Nein, zurück")
        page.click("#modal-ok")
        expect(page.locator(".seq-item")).to_have_count(1, timeout=10000)
        check("T-20 AK1 zwei Sequenzen gemeinsam archiviert und ausgeblendet", True)
        page.select_option("#f-status", "archiviert")
        expect(page.locator(".seq-item")).to_have_count(2)
        page.locator(".seq-item").first.click()
        expect(page.locator("#btn-detail-wiederherstellen")).to_be_visible(timeout=10000)
        page.click("#btn-detail-wiederherstellen")
        expect(page.locator(".seq-item")).to_have_count(1, timeout=10000)
        check("T-20 AK1 Wiederherstellen einer Sequenz", True)
        page.select_option("#f-status", "")
        expect(page.locator(".seq-item")).to_have_count(2, timeout=10000)
        page.locator(".seq-item").first.click()
        page.click("#btn-detail-archivieren")
        page.click("#modal-ok")
        expect(page.locator(".seq-item")).to_have_count(1, timeout=10000)
        check("T-20 AK1 Einzelne Sequenz archivieren", True)
        page.goto(base + "/teacher/lessons")
        check("T-20 AK4 kein «Löschen» in der Lektionsverwaltung", "Löschen" not in page.content())
        page.locator("tr[data-id='haftungsrecht'] button[data-act='archive']").click()
        page.click("#modal-ok")
        page.check("#show-archived")
        page.locator("tr[data-id='haftungsrecht'] button[data-act='restore']").click()
        expect(page.locator("#banner")).to_contain_text("wiederhergestellt", timeout=10000)
        ids = [l["id"] for l in httpx.get(base + "/api/lessons").json()]
        check("T-20 AK4 archivierte Lektion wiederhergestellt", "haftungsrecht" in ids)
        check("T-20 ohne Skriptfehler", not fehler, "; ".join(fehler))
        page.goto(base + "/teacher")
        label = page.locator("label.cb", has=page.locator("#show-tests"))
        check("T-21 AK1 Beschriftung und Tooltip sichtbar",
              label.inner_text().strip() == "Testläufe von Lehrpersonen anzeigen"
              and "zählen nicht in den Auswertungen" in (label.get_attribute("title") or ""))


@scenario("t22")
def t22_abmelden(pw):
    """T-22 AK1-3: Abmelden als Lehrperson und aus der laufenden Lernansicht."""
    with server(TEACHER_PASSWORD="geheim") as base:
        browser = launch(pw)
        page = browser.new_context().new_page()
        page.goto(base + "/teacher/login")
        page.fill("#pw", "geheim")
        page.click("#btn")
        page.wait_for_url(base + "/teacher")
        page.click("#link-abmelden")
        page.wait_for_url(base + "/teacher/login")
        page.goto(base + "/teacher")
        check("T-22 AK1 nach dem Abmelden führt /teacher zur Login-Seite", page.url.endswith("/teacher/login"),
              page.url)
        check("T-22 Login-Seite leer", page.input_value("#pw") == "")
        lern = browser.new_context().new_page()
        start_lernsequenz(lern, base, name="Abmelden")
        knopf = lern.locator("#btn-abmelden")
        check("T-22 Abmelden in der laufenden Lernansicht sichtbar", knopf.is_visible())
        knopf.click()
        expect(lern.locator("#view-start")).to_be_visible(timeout=10000)
        check("T-22 AK2 leere Anmeldemaske", lern.input_value("#name") == "" and lern.input_value("#pin") == "")
        r = lern.request.get(base + "/api/me/sequenzen")
        check("T-22 AK2 Sequenzen ohne neue Anmeldung nicht sichtbar", r.status == 401, str(r.status))
        lp = browser.new_context().new_page()
        lp.goto(base + "/teacher/login")
        lp.fill("#pw", "geheim")
        lp.click("#btn")
        lp.wait_for_url(base + "/teacher")
        seqs = lp.request.get(base + "/api/teacher/sessions?testlaeufe=true").json()
        status = [x["status"] for x in seqs if x["name"] == "Abmelden"]
        check("T-22 laufende Sequenz beim Abmelden pausiert", status == ["pausiert"], str(status))
        browser.close()
    with server() as base:
        page = launch(pw).new_page()
        page.goto(base + "/teacher")
        page.click("#link-abmelden")
        page.wait_for_url(base + "/teacher/login")
        page.goto(base + "/teacher")
        check("T-22 AK1 auch ohne TEACHER_PASSWORD wirksam", page.url.endswith("/teacher/login"), page.url)


@scenario("t23")
def t23_abmelden_header(pw):
    """T-23 AK1/E6: Abmelden bei Header-Anmeldung leitet auf die Adresse des Proxys."""
    with server(ITS_TRUST_PROXY_HEADERS="true") as base:
        browser = launch(pw)
        ctx = browser.new_context(extra_http_headers={"X-Forwarded-User": "mia.muster", "X-User-Roles": "teacher",
                                                      "X-Logout-Url": "/abgemeldet-beim-proxy"})
        page = ctx.new_page()
        page.goto(base + "/")
        expect(page.locator("#btn-abmelden")).to_be_visible(timeout=10000)
        check("T-23 AK1 Button in der Lernenden-Ansicht", True)
        page.goto(base + "/teacher")
        expect(page.locator("#link-abmelden")).to_be_visible()
        page.click("#link-abmelden")
        page.wait_for_url("**/abgemeldet-beim-proxy", timeout=10000)
        check("T-23 AK1 Weiterleitung auf die Adresse aus dem Header", page.url.endswith("/abgemeldet-beim-proxy"))
        ohne = browser.new_context(extra_http_headers={"X-Forwarded-User": "mia.muster"}).new_page()
        ohne.goto(base + "/")
        ohne.wait_for_load_state("networkidle")
        check("T-23 E6 ohne Abmeldeadresse kein Button",
              not ohne.locator("#btn-abmelden").is_visible() and not ohne.locator("#btn-logout").is_visible())
        browser.close()


# ---------------------------------------------------------------- Auftrag 3

@scenario("t25")
def t25_legende(pw):
    """T-25 AK1-AK4: Die Legende passt in jedem Zustand zu den sichtbaren Buttons."""
    with server() as base:
        browser = launch(pw)
        page = browser.new_context().new_page()
        start_lernsequenz(page, base, name="Legende")
        r = legende(page)
        check("T-25 Theorie: «Verstanden, weiter» erklärt, keine Antwort",
              "Verstanden, weiter" in r["genannt"] and "Antwort abschicken" not in r["genannt"], r["text"])
        zur_aufgabe(page)
        r = legende(page)
        check("T-25 Aufgabe offen: wie bisher",
              {"Antwort abschicken", "Frage stellen", "Theorie dazu"} <= set(r["genannt"]), r["text"])
        beantworte(page, "Anna haftet, weil Schaden da ist.", 6)          # teilweise
        expect(page.locator(".wahlbox button")).to_have_count(4, timeout=10000)
        r = legende(page)
        check("T-25 AK1 nach «teilweise» genau die sichtbaren Möglichkeiten",
              set(r["genannt"]) == {"Antwort ergänzen", "Lösung ansehen", "Weiter zur nächsten Aufgabe",
                                    "Ich sehe das anders", "Frage stellen"}, r["text"])
        check("T-25 AK1 weder «Antwort abschicken» noch «Theorie dazu»",
              "Antwort abschicken" not in r["text"] and "Theorie dazu" not in r["text"], r["text"])
        for i in range(3):
            page.click(".wahlbox button[data-wahl='ergaenzen']")
            page.wait_for_selector("#waiting", state="detached", timeout=30000)
            if i == 0:
                check("T-25 nach «Antwort ergänzen» nennt die Legende die gemeinsame Bewertung",
                      "zusammen mit deiner bisherigen Antwort" in legende(page)["text"], legende(page)["text"])
            beantworte(page, "Anna haftet, weil Schaden da ist.", None)
        r = legende(page)
        check("T-25 AK2 nach dem dritten Ergänzungsversuch kein «Antwort ergänzen»",
              "Antwort ergänzen" not in r["text"] and page.locator(".wahlbox button[data-wahl='ergaenzen']").count() == 0,
              r["text"])
        vorher = r["text"]
        page.click("#btn-pause")
        expect(page.locator("#home-banner")).to_be_visible(timeout=10000)
        p2 = browser.new_context().new_page()
        anmelden(p2, base, "Legende")
        p2.click("#seq-list button[data-act='resume']")
        expect(p2.locator(".wahlbox button").first).to_be_visible(timeout=10000)
        r2 = legende(p2)
        check("T-25 AK4 nach Pausieren und Fortsetzen stimmen Legende und Buttons",
              not r2["fehlt"] and r2["text"] == vorher, f"{r2['text']} | vorher: {vorher}")
        p2.click(".wahlbox button[data-wahl='weiter']")
        p2.wait_for_selector("#waiting", state="detached", timeout=30000)
        legende_pruefen(p2, "nach «Weiter»")
        browser.close()
    with server(ITS_MOCK_FAIL="ANTWORT_BEWERTEN") as base:
        page = launch(pw).new_page()
        start_lernsequenz(page, base, name="Legende2")
        zur_aufgabe(page)
        beantworte(page, GUT, 5)
        r = legende(page)
        check("T-25 nach gescheiterter Bewertung: passender Satz",
              r["genannt"][:1] == ["Nochmals bewerten lassen"] and not r["fehlt"], r["text"])
        page.click(".wahlbox button[data-wahl='nochmals_bewerten']")
        page.wait_for_selector("#waiting", state="detached", timeout=30000)
        r = legende(page)
        check("T-25 nach zweiter gescheiterter Bewertung: alle Wahlmöglichkeiten erklärt",
              {"Nochmals versuchen", "Ohne Bewertung weiter"} <= set(r["genannt"]) and not r["fehlt"], r["text"])
    with server(ITS_MOCK_FAIL="THEORIE_SCHRITT") as base:
        page = launch(pw).new_page()
        start_lernsequenz(page, base, name="Legende3")
        expect(page.locator(".wahlbox button").first).to_be_visible(timeout=30000)
        r = legende(page)
        check("T-25 nach einem Fallback: jede Möglichkeit mit kurzem Satz",
              {"Nochmals versuchen", "Witz zum Thema"} <= set(r["genannt"]) and not r["fehlt"], r["text"])
        page.click(".wahlbox button[data-wahl='witz']")
        page.wait_for_selector("#waiting", state="detached", timeout=30000)
        legende_pruefen(page, "nach dem Witz")


@scenario("t26")
def t26_zeitstempel(pw):
    """T-26 AK1-AK4: Startzeit in der Liste, neueste Sequenz oben, Tooltip, Datum beim Tageswechsel."""
    import sqlite3
    with server() as base:
        c = httpx.Client(base_url=base)
        c.post("/api/learner/login", json={"name": "Zeitreise"})
        alt = c.post("/api/session/start", json={"lesson_id": "haftungsrecht"}).json()["session_id"]
        c.post(f"/api/session/{alt}/assess", json={"answers": ["a", "b", "c"]})
        c.post(f"/api/session/{alt}/next")
        c.post(f"/api/session/{alt}/abbrechen")
        neu = c.post("/api/session/start", json={"lesson_id": "haftungsrecht", "neu_beginnen": True}).json()["session_id"]
        # Die ältere Sequenz begann gestern um 23:58 und lief über Mitternacht
        with sqlite3.connect(AKTUELLE_DB) as db:
            jetzt = db.execute("SELECT created_at FROM sessions WHERE id=?", (neu,)).fetchone()[0]
            import datetime
            heute = datetime.datetime.fromtimestamp(jetzt).replace(hour=0, minute=0, second=0, microsecond=0)
            start = (heute - datetime.timedelta(minutes=2)).timestamp()
            # «Neu beginnen» archiviert die alte Sequenz (T-05); für die Prüfung bleibt sie sichtbar,
            # wie Testläufe aus der Zeit vor T-05
            db.execute("UPDATE sessions SET created_at=?, updated_at=?, status='abgebrochen' WHERE id=?",
                       (start, start + 600, alt))
            ids = [r[0] for r in db.execute("SELECT id FROM events WHERE session_id=? ORDER BY id", (alt,))]
            for i, eid in enumerate(ids):
                db.execute("UPDATE events SET created_at=? WHERE id=?", (start + 60 * i, eid))
        page = launch(pw).new_page()
        page.goto(base + "/teacher")
        eintraege = page.locator(".seq-item")
        expect(eintraege).to_have_count(2, timeout=10000)
        texte = eintraege.all_inner_texts()
        check("T-26 AK1 jeder Eintrag zeigt Startdatum und Startzeit",
              all(re.search(r"Start \d{2}\.\d{2}\.\d{4}, \d{2}:\d{2}", t) for t in texte), str(texte))
        check("T-26 AK2 zwei Sequenzen zur selben Lektion unterscheidbar, die neuere oben",
              texte[0] != texte[1] and page.get_attribute(".seq-item >> nth=0", "data-sid") == neu, str(texte))
        tip = page.get_attribute(".seq-item >> nth=1", "title") or ""
        check("T-26 AK3 Tooltip zeigt die letzte Aktivität", tip.startswith("Letzte Aktivität: "), tip)
        page.locator(".seq-item").nth(1).click()
        expect(page.locator("#detail-events .event").first).to_be_visible(timeout=10000)
        zeiten = page.locator("#detail-events .event .t").all_inner_texts()
        mit_datum = [z for z in zeiten if re.match(r"\d{2}\.\d{2}\.\d{4}, ", z)]
        check("T-26 AK4 Datum beim ersten Ereignis und beim Tageswechsel", len(mit_datum) == 2, str(zeiten))
        check("T-26 Kopf der Detailansicht zeigt Start und letzte Aktivität",
              "Start " in page.inner_text("#detail-kopf") and "letzte Aktivität" in page.inner_text("#detail-kopf"))
        page.set_viewport_size({"width": 360, "height": 740})
        page.click("#btn-sidebar")
        breite = page.evaluate("() => [document.getElementById('sidebar').scrollWidth, document.getElementById('sidebar').clientWidth]")
        check("T-26 schmaler Bildschirm: Leiste scrollt nicht horizontal", breite[0] <= breite[1], str(breite))


@scenario("d15")
def d15_widerspruch(pw):
    """D-15 AK5: «Ich sehe das anders» einmal pro Aufgabe, zählt nicht als Versuch, Legende passt."""
    with server() as base:
        browser = launch(pw)
        page = browser.new_context().new_page()
        start_lernsequenz(page, base, name="Einwand")
        zur_aufgabe(page)
        beantworte(page, "Anna haftet, weil Schaden da ist.", 6)              # teilweise
        knopf = page.locator(".wahlbox button[data-wahl='widerspruch']")
        expect(knopf).to_be_visible(timeout=10000)
        check("D-15 «Ich sehe das anders» nach «teilweise» sichtbar", knopf.inner_text() == "Ich sehe das anders")
        knopf.click()
        check("D-15 Einwand: Begründung senden und Zurück, keine Wahl mehr offen",
              page.locator("#btn-einwand").is_visible() and page.locator("#btn-einwand-zurueck").is_visible()
              and page.locator(".wahlbox").count() == 0)
        r = legende(page)
        check("D-15 Legende erklärt den Einwand", "Begründung senden" in r["genannt"] and not r["fehlt"], r["text"])
        page.click("#btn-einwand-zurueck")
        expect(page.locator(".wahlbox button[data-wahl='widerspruch']")).to_be_visible(timeout=10000)
        check("D-15 Zurück stellt die Wahl wieder her", page.locator(".wahlbox button").count() == 4)
        page.click(".wahlbox button[data-wahl='widerspruch']")
        page.fill("#chat-input", "Ich finde, das reicht für den Fall.")
        page.click("#btn-einwand")
        page.wait_for_selector("#waiting", state="detached", timeout=30000)
        legende_pruefen(page, "nach dem Einwand")
        check("D-15 Tutor bleibt mit Begründung bei seinem Urteil",
              "Ich bleibe bei meiner Bewertung" in page.locator(".msg.tutor.mid").last.inner_text())
        check("D-15 zählt nicht als Versuch (Hinweis)", "nicht als zusätzlicher Versuch" in page.inner_text("#chat"))
        check("D-15 nur einmal pro Aufgabe",
              page.locator(".wahlbox button[data-wahl='widerspruch']").count() == 0
              and page.locator(".wahlbox button").count() == 3)
        check("D-15 Zählung unverändert: 1 teilweise", "1 teilweise" in page.inner_text("#prog-badges"))
        page.click(".wahlbox button[data-wahl='weiter']")
        page.wait_for_selector("#waiting", state="detached", timeout=30000)
        zur_aufgabe(page)
        beantworte(page, "weiss nicht", 3)                                       # falsch, zweiter Versuch offen
        expect(page.locator(".wahlbox.zusatz button[data-wahl='widerspruch']")).to_be_visible(timeout=10000)
        check("D-15 nach «falsch» bleibt die Antwort möglich, Widerspruch als Zusatz",
              page.locator("#btn-answer").is_enabled())
        page.click(".wahlbox button[data-wahl='widerspruch']")
        page.fill("#chat-input", "Das stimmt doch, der Fall lässt offen, ob sie vorsichtig war.")
        page.click("#btn-einwand")
        page.wait_for_selector("#waiting", state="detached", timeout=30000)
        check("D-15 berechtigter Einwand ändert das Urteil",
              "Richtig" in page.locator(".msg.tutor.good").last.inner_text()
              and "Die Bewertung ist neu" in page.inner_text("#chat"))
        check("D-15 kein Fehler gezählt", "0 falsch" in page.inner_text("#prog-badges"))
        page.goto(base + "/teacher")
        page.locator(".seq-item").first.click()
        expect(page.locator("#detail-events")).to_contain_text("Widerspruch der lernenden Person", timeout=10000)
        text = page.inner_text("#detail-events")
        check("D-15 Lernverlauf zeigt Widerspruch und vertretbare Alternative",
              "Urteil geändert" in text and "Vertretbare Alternative anerkannt" in text)
        browser.close()


@scenario("d17")
def d17_loesung(pw):
    """D-17 AK1/AK3: «Lösung ansehen» zeigt je Element Dimension, Erwartetes, eigene Antwort und Status."""
    with server() as base:
        browser = launch(pw)
        page = browser.new_context(viewport={"width": 390, "height": 844}).new_page()   # Handy
        start_lernsequenz(page, base, name="Loesung")
        zur_aufgabe(page)
        beantworte(page, "Anna haftet, weil Schaden da ist.", 5)
        page.click(".wahlbox button[data-wahl='loesung']")
        page.wait_for_selector("#waiting", state="detached", timeout=30000)
        msg = page.locator(".msg.tutor.loesung").last
        expect(msg).to_be_visible(timeout=10000)
        punkte = msg.locator("li").all_inner_texts()
        check("D-17 AK1 Vergleich mit der eigenen Antwort", "Vergleich mit deiner letzten Antwort" in msg.inner_text())
        check("D-17 AK1 pro Element Dimension, Erwartetes, eigene Antwort und Status",
              len(punkte) == 2 and all("erwartet:" in t and "du:" in t and "(" in t for t in punkte), str(punkte))
        check("D-17 AK1 eigene Antwort zitiert", "«Anna haftet" in punkte[0] if punkte else False, str(punkte))
        breite = page.evaluate("() => [document.documentElement.scrollWidth, window.innerWidth]")
        check("D-17 auf dem Handy als Liste ohne horizontales Scrollen", breite[0] <= breite[1], str(breite))
        page.screenshot(path=str(Path(tempfile.gettempdir()) / "its_d17_loesung.png"))     # zur Sichtkontrolle
        page.goto(base + "/teacher")
        page.locator(".seq-item").first.click()
        expect(page.locator("#detail-events")).to_contain_text("Lösung angezeigt", timeout=10000)
        check("D-17 AK3 Lernverlauf zeigt die Gegenüberstellung",
              "geschrieben: «Anna haftet" in page.inner_text("#detail-events"))
        browser.close()


@scenario("d18")
def d18_selbstkorrektur(pw):
    """D-18 AK2: Nach einer Selbstkorrektur im Chat erscheint «Antwort neu bewerten lassen», ohne neuen Versuch."""
    with server() as base:
        page = launch(pw).new_page()
        start_lernsequenz(page, base, name="Korrektur")
        zur_aufgabe(page)
        beantworte(page, "Anna haftet, weil Schaden da ist.", 5)
        page.fill("#chat-input", "Ist das wirklich nur teilweise richtig?")
        page.click("#btn-ask")
        page.wait_for_selector("#waiting", state="detached", timeout=30000)
        check("D-18 Der Tutor benennt den Irrtum ausdrücklich",
              "Da habe ich mich vorhin geirrt" in page.locator(".msg.tutor").last.inner_text())
        knopf = page.locator(".wahlbox button[data-wahl='neu_bewerten']")
        expect(knopf).to_be_visible(timeout=10000)
        check("D-18 «Antwort neu bewerten lassen» erscheint, die Wahl nach «teilweise» bleibt",
              page.locator(".wahlbox button[data-wahl='ergaenzen']").count() == 1)
        legende_pruefen(page, "nach der Selbstkorrektur")
        check("D-18 Legende erklärt die Neubewertung",
              "Antwort neu bewerten lassen" in legende(page)["genannt"])
        knopf.click()
        page.wait_for_selector("#waiting", state="detached", timeout=30000)
        check("D-18 Neubewertung zählt nicht als Versuch",
              "1 richtig" in page.inner_text("#prog-badges") and "teilweise" not in page.inner_text("#prog-badges")
              and "nicht als zusätzlicher Versuch" in page.inner_text("#chat"))
        page.goto(base + "/teacher")
        page.locator(".seq-item").first.click()
        expect(page.locator("#detail-events")).to_contain_text("korrigiert im Chat", timeout=10000)
        check("D-18 tutor_korrektur im Lernverlauf", "Neubewertung nach Selbstkorrektur" in page.inner_text("#detail-events"))



# ---------------------------------------------------------------- Auftrag 4 (Oktober 2026)

def _testdateien(ordner: Path) -> dict:
    sys.path.insert(0, str(ROOT / "tests"))
    from material_hilfen import HAFTUNG, pdf
    dateien = {"haftung.pdf": pdf(HAFTUNG), "brueche.txt": ("Ein Bruch besteht aus Zaehler und Nenner. " * 12).encode()}
    pfade = {}
    for name, daten in dateien.items():
        (ordner / name).write_bytes(daten)
        pfade[name] = str(ordner / name)
    return pfade


@scenario("t27")
def t27_t31_favicon_version(pw):
    """T-27/T-31: Favicon und Version mit Commit im Fuss jeder Seite."""
    with server() as base:
        page = launch(pw).new_page()
        v = httpx.get(base + "/api/version").json()
        for pfad in ["/", "/teacher", "/teacher/lessons", "/teacher/lessons/new", "/teacher/materialien"]:
            page.goto(base + pfad)
            fuss = page.locator("#its-version")
            expect(fuss).to_contain_text(v["version"], timeout=10000)
            check(f"T-31 Fuss mit Version und Commit auf {pfad}",
                  (v["commit"] or "") in fuss.inner_text() and fuss.get_attribute("data-version") == v["anzeige"],
                  fuss.inner_text())
            ok = page.evaluate("""async () => {
                const l = document.querySelector('link[rel=icon][type="image/svg+xml"]');
                if (!l) return false;
                const r = await fetch(l.href); return r.ok && (await r.text()).includes('<svg');
            }""")
            check(f"T-27 Favicon verlinkt und abrufbar auf {pfad}", ok)
        check("T-27 /favicon.ico", httpx.get(base + "/favicon.ico").status_code == 200)


@scenario("l01")
def l01_materialien_ablage(pw):
    """L-01/L-03: Upload mit Metadaten, Vorschläge gegen Dubletten, Filter, Archivieren."""
    with server() as base:
        pfade = _testdateien(Path(tempfile.mkdtemp(prefix="its_ui_dateien_")))
        page = launch(pw).new_page(viewport={"width": 1300, "height": 900})
        page.goto(base + "/teacher/materialien")
        page.set_input_files("#file", [pfade["haftung.pdf"]])
        expect(page.locator(".itsm-modal")).to_be_visible(timeout=10000)
        page.locator(".itsm-datei input[type=text]").first.fill("OR Haftpflicht")
        page.locator(".itsm-datei input[type=text]").nth(1).fill("x" * 140)
        check("L-01 Beschreibung höchstens 128 Zeichen",
              len(page.locator(".itsm-datei input[type=text]").nth(1).input_value()) == 128)
        page.locator(".itsm-datei input[type=text]").nth(1).fill("Art. 41 bis 56 OR")
        chips = page.locator(".itsm-chips input")
        chips.nth(0).fill("Recht"); chips.nth(0).press("Enter")
        page.locator(".itsm-feld input[list]").nth(1).fill("BM 2. Lehrjahr")
        chips.nth(1).fill("Haftung"); chips.nth(1).press("Enter")
        page.locator(".itsm-feld input[list]").last.fill("Frau Muster")
        page.click("#itsm-los")
        expect(page.locator(".itsm-modal")).to_have_count(0, timeout=15000)
        zeile = page.locator(".itsm-tabelle tbody tr").first
        expect(zeile).to_contain_text("OR Haftpflicht", timeout=10000)
        text = zeile.inner_text()
        check("L-01 Tabelle zeigt Metadaten und Datei-Metadaten",
              all(x in text for x in ("Recht", "BM 2. Lehrjahr", "Haftung", "pdf", "3", "Frau Muster")), text)
        # Zweiter Upload: Vorschlag aus bestehenden Werten, ähnlicher Tag wird gemeldet
        page.set_input_files("#file", [pfade["brueche.txt"]])
        expect(page.locator(".itsm-modal")).to_be_visible(timeout=10000)
        optionen = page.evaluate("() => Array.from(document.querySelectorAll('datalist option')).map(o => o.value)")
        check("L-01 bestehende Fächer und Tags als Vorschläge", "Recht" in optionen and "Haftung" in optionen, str(optionen))
        chips = page.locator(".itsm-chips input")
        chips.nth(1).fill("haftungen"); chips.nth(1).press("Enter")
        expect(page.locator(".itsm-aehnlich").filter(has_text="Haftung").first).to_be_visible(timeout=5000)
        page.locator(".itsm-aehnlich button").first.click()
        chips.nth(0).fill("recht"); chips.nth(0).press("Enter")
        chip_texte = page.locator(".itsm-chip").all_inner_texts()
        check("L-01 Schreibweise der bestehenden Werte übernommen («recht» → «Recht»)",
              any(c.startswith("Recht") for c in chip_texte) and any(c.startswith("Haftung") for c in chip_texte),
              str(chip_texte))
        page.click("#itsm-los")
        expect(page.locator(".itsm-modal")).to_have_count(0, timeout=15000)
        expect(page.locator(".itsm-tabelle tbody tr")).to_have_count(2, timeout=10000)
        page.select_option(".itsm-filter select[data-f=format]", "txt")
        expect(page.locator(".itsm-tabelle tbody tr")).to_have_count(1, timeout=5000)
        check("L-02 Filter nach Format wirkt sofort", "brueche" in page.locator(".itsm-tabelle tbody").inner_text())
        page.select_option(".itsm-filter select[data-f=format]", "")
        page.fill(".itsm-filter input[data-f=q]", "Art. 41")
        expect(page.locator(".itsm-tabelle tbody tr")).to_have_count(1, timeout=5000)
        page.fill(".itsm-filter input[data-f=q]", "")
        expect(page.locator(".itsm-tabelle tbody tr")).to_have_count(2, timeout=5000)
        # Details mit Textvorschau
        page.locator(".itsm-tabelle tbody tr", has_text="OR Haftpflicht").locator("button[data-a=details]").click()
        expect(page.locator("#itsm-text")).to_contain_text("Tierhalterhaftung", timeout=10000)
        check("L-01 Details zeigen Speicherort", "depot" in page.locator(".itsm-box").inner_text())
        page.click(".itsm-box button[data-a=zu]")
        # L-03: Archivieren ohne Lektion, danach unter «Archivierte anzeigen» wiederherstellen
        page.locator(".itsm-tabelle tbody tr", has_text="brueche").locator("button[data-a=archivieren]").click()
        page.click(".itsm-box button[data-a=ja]")
        expect(page.locator(".itsm-tabelle tbody tr")).to_have_count(1, timeout=10000)
        page.check(".itsm-filter input[data-f=archivierte]")
        expect(page.locator(".itsm-tabelle tbody tr.archiviert")).to_have_count(1, timeout=5000)
        page.locator(".itsm-tabelle tbody tr.archiviert button[data-a=wiederherstellen]").click()
        expect(page.locator(".itsm-tabelle tbody tr.archiviert")).to_have_count(0, timeout=5000)
        check("L-03 archivieren und wiederherstellen", page.locator(".itsm-tabelle tbody tr").count() == 2)


@scenario("l02")
def l02_auswahl_im_editor(pw):
    """L-02/L-03: Material aus der Ablage im Editor wählen, Lektion speichern, Archivieren blockiert."""
    with server() as base:
        pfade = _testdateien(Path(tempfile.mkdtemp(prefix="its_ui_dateien_")))
        c = httpx.Client(base_url=base)
        with open(pfade["haftung.pdf"], "rb") as f:
            m = c.post("/api/teacher/materialien", files={"file": ("haftung.pdf", f.read())},
                       data={"name": "OR Haftpflicht", "tags": '["Haftung"]', "faecher": '["Recht"]'}).json()
        page = launch(pw).new_page(viewport={"width": 1300, "height": 900})
        page.goto(base + "/teacher/lessons/new")
        page.click("#btn-ablage")
        expect(page.locator("#ablage-tabelle .itsm-tabelle tbody tr")).to_have_count(1, timeout=10000)
        page.select_option("#ablage-tabelle select[data-f=tag]", "Haftung")
        page.locator("#ablage-tabelle .itsm-tabelle tbody tr").first.click()
        expect(page.locator("#btn-ablage-uebernehmen")).to_be_enabled(timeout=5000)
        page.click("#btn-ablage-uebernehmen")
        expect(page.locator("#source-list")).to_contain_text("OR Haftpflicht", timeout=5000)
        check("L-02 Material als «Ablage» in der Lektion", "Ablage" in page.locator("#source-list").inner_text())
        page.fill("#titel", "Haftung aus der Ablage")
        page.fill("#ziele", "Haftungsarten unterscheiden")
        page.click("#btn-save")
        expect(page.locator("#result")).to_contain_text("veröffentlicht", timeout=10000)
        lektion = [l for l in c.get("/api/teacher/lessons").json() if l["titel"] == "Haftung aus der Ablage"][0]
        d = c.get(f"/api/teacher/lessons/{lektion['id']}").json()
        check("L-02 Lektion verweist auf das Material und enthält den Text",
              d["materialien"] == [m["id"]] and "Tierhalterhaftung" in d["material"], str(d.get("materialien")))
        # Bearbeiten zeigt das Material wieder als Eintrag aus der Ablage
        page.goto(base + f"/teacher/lessons/{lektion['id']}/edit")
        expect(page.locator("#source-list")).to_contain_text("OR Haftpflicht", timeout=10000)
        check("L-02 beim Bearbeiten kein doppelter Text", page.locator("#material").input_value() == "")
        # L-03: Archivieren blockiert, solange die Lektion aktiv ist
        page.goto(base + "/teacher/materialien")
        page.locator(".itsm-tabelle tbody tr").first.locator("button[data-a=archivieren]").click()
        page.click(".itsm-box button[data-a=ja]")
        expect(page.locator(".itsm-box .itsm-meldung")).to_contain_text("Haftung aus der Ablage", timeout=5000)
        check("L-03 Archivieren nennt die Lektion und bleibt blockiert",
              page.locator(".itsm-box button[data-a=ja]").is_disabled())


@scenario("l04")
def l04_archived_not_editable(pw):
    """L-04: Kein Weg in den Editor einer archivierten Lektion; Duplizieren und Wiederherstellen wie bisher."""
    with server() as base:
        files = _testdateien(Path(tempfile.mkdtemp(prefix="its_ui_dateien_")))
        client = httpx.Client(base_url=base)
        with open(files["haftung.pdf"], "rb") as f:
            material = client.post("/api/teacher/materialien", files={"file": ("haftung.pdf", f.read())},
                                   data={"name": "OR Haftpflicht"}).json()
        ids = {}
        for title in ("Aktiv L-04", "Archiv L-04"):
            ids[title] = client.post("/api/teacher/lessons", json={
                "titel": title, "lernziele": ["Haftung verstehen"], "material": "",
                "materialien": [material["id"]]}).json()["id"]
        archived = ids["Archiv L-04"]
        client.delete(f"/api/teacher/lessons/{archived}")
        page = launch(pw).new_page(viewport={"width": 1300, "height": 900})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(base + "/teacher/lessons")
        page.check("#show-archived")
        expect(page.locator(f"tr[data-id='{archived}']")).to_have_count(1, timeout=10000)
        archived_rows = page.locator("tr", has=page.locator(".pill", has_text="archiviert"))
        check("L-04 AK1 keine archivierte Lektion hat «Bearbeiten»", archived_rows.count() >= 1
              and archived_rows.locator("button[data-act='edit']").count() == 0)
        check("L-04 AK6 aktive Lektion hat weiterhin «Bearbeiten»",
              page.locator(f"tr[data-id='{ids['Aktiv L-04']}'] button[data-act='edit']").count() == 1)
        # AK 2: calling the editor URL directly
        page.goto(base + f"/teacher/lessons/{archived}/edit")
        expect(page.locator("#edit-notice")).to_contain_text("Die Lektion ist archiviert. Stelle sie zuerst wieder "
                                                             "her, um sie zu bearbeiten.", timeout=10000)
        check("L-04 AK2 kein bearbeitbares Formular", not page.locator("#titel").is_visible()
              and not page.locator("#btn-save").is_visible())
        check("L-04 AK2 Link zur Lektionsliste",
              page.locator("#edit-notice a").get_attribute("href") == "/teacher/lessons")
        # AK 4: details of a learning material
        page.goto(base + "/teacher/materialien")
        page.locator(".itsm-tabelle tbody tr").first.locator("button[data-a=details]").click()
        dialog = page.locator(".itsm-box")
        expect(dialog).to_contain_text("Archiv L-04 (archiviert)", timeout=10000)
        check("L-04 AK4 archivierte Lektion nicht in den Editor verlinkt",
              dialog.locator(f"a[href='/teacher/lessons/{archived}/edit']").count() == 0)
        check("L-04 AK6 aktive Lektion weiterhin verlinkt",
              dialog.locator(f"a[href='/teacher/lessons/{ids['Aktiv L-04']}/edit']").count() == 1)
        # AK 5: editor open, the lesson gets archived meanwhile, then save
        active = ids["Aktiv L-04"]
        page.goto(base + f"/teacher/lessons/{active}/edit")
        expect(page.locator("#titel")).to_have_value("Aktiv L-04", timeout=10000)
        client.delete(f"/api/teacher/lessons/{active}")
        page.fill("#titel", "Aktiv L-04 geändert")
        page.click("#btn-save")
        expect(page.locator("#result")).to_contain_text("archiviert", timeout=10000)
        detail = client.get(f"/api/teacher/lessons/{active}").json()
        check("L-04 AK5 Speichern nach dem Archivieren abgelehnt, Version unverändert",
              detail["version"] == 1 and detail["titel"] == "Aktiv L-04", f"Version {detail['version']}, {detail['titel']}")
        # AK 6: duplicating and restoring as before
        page.goto(base + "/teacher/lessons")
        page.check("#show-archived")
        page.locator(f"tr[data-id='{archived}'] button[data-act='duplicate']").click()
        expect(page.locator("#edit-notice")).to_contain_text("Kopie angelegt", timeout=10000)
        check("L-04 AK6 Kopie einer archivierten Lektion ist bearbeitbar", page.locator("#titel").is_visible())
        page.goto(base + "/teacher/lessons")
        page.check("#show-archived")
        page.locator(f"tr[data-id='{archived}'] button[data-act='restore']").click()
        expect(page.locator("#banner")).to_contain_text("wiederhergestellt", timeout=10000)
        page.goto(base + f"/teacher/lessons/{archived}/edit")
        expect(page.locator("#titel")).to_have_value("Archiv L-04", timeout=10000)
        check("L-04 AK6 nach dem Wiederherstellen wieder bearbeitbar", page.locator("#btn-save").is_visible())
        check("L-04 ohne Skriptfehler", not errors, "; ".join(errors))


def _assessment_to_learning(page):
    """Answers the three placement questions and waits for the first step."""
    expect(page.locator("#view-assess")).to_be_visible(timeout=30000)
    for _ in range(3):
        page.fill("#assess-answer", "weiss ich nicht")
        page.click("#btn-assess")
    expect(page.locator("#view-learn")).to_be_visible(timeout=60000)
    page.wait_for_selector("#waiting", state="detached", timeout=60000)


@scenario("n06")
def n06_teaching_mode(pw):
    """N-06: Teaching Mode starten, «Teach the Tutor» in jedem Schritt, Anweisungen im Verlauf und im Editor."""
    with server() as base:
        httpx.delete(base + "/api/teacher/lessons/bruchbegriff-verstehen-und-anwenden")
        page = launch(pw).new_page(viewport={"width": 1300, "height": 900})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(base + "/teacher/lessons")
        page.check("#show-archived")
        expect(page.locator("tr[data-id='bruchbegriff-verstehen-und-anwenden']")).to_have_count(1, timeout=10000)
        check("N-06 AK1 Start nur bei nicht archivierten Lektionen",
              page.locator("tr[data-id='haftungsrecht'] button[data-act='teaching']").count() == 1
              and page.locator("tr[data-id='bruchbegriff-verstehen-und-anwenden'] button[data-act='teaching']").count() == 0)
        page.locator("tr[data-id='haftungsrecht'] button[data-act='teaching']").click()
        page.fill("#name", "LP Teaching")
        page.click("#btn-login")
        _assessment_to_learning(page)
        zur_aufgabe(page)
        tutor_messages = page.locator(".msg.tutor:not(.waiting)")
        without_button = [
            i for i in range(tutor_messages.count())
            if tutor_messages.nth(i).locator(".teach-btn").count() == 0
            and not tutor_messages.nth(i).evaluate(
                "e => !!(e.nextElementSibling && e.nextElementSibling.matches('.msg.tutor.question'))")]
        check("N-06 AK2 jeder Schritt des Tutors zeigt «Teach the Tutor»",
              tutor_messages.count() > 0 and not without_button,
              f"{len(without_button)} ohne Knopf von {tutor_messages.count()}")
        # instruction only for this topic (at the question of the task)
        question = page.locator(".msg.tutor.question").last
        question.locator(".teach-btn").click()
        form = question.locator(".teach")
        form.locator("textarea.teach-text").fill("Verlange den Gesetzesartikel.")
        check("N-06 Thema ist vorgewählt, wenn das Konzept bekannt ist",
              form.locator("input[value='topic']").is_checked())
        form.locator(".teach-ok").click()
        expect(question.locator(".teach-message")).to_contain_text("zum Thema", timeout=10000)
        # instruction for the whole lesson: see the suggestion, change it, confirm it
        theory = page.locator(".msg.tutor.theory").first
        theory.locator(".teach-btn").click()
        form = theory.locator(".teach")
        form.locator("textarea.teach-text").fill("Hier fehlt ein Beispiel aus dem Berufsalltag.")
        form.locator("input[value='lesson']").check()
        check("N-06 AK4 zuerst verallgemeinern", form.locator(".teach-ok").inner_text() == "Verallgemeinern")
        form.locator(".teach-ok").click()
        rule = form.locator("textarea.teach-rule")
        expect(rule).to_be_visible(timeout=10000)
        check("N-06 AK4 verallgemeinerte Fassung wird angezeigt",
              rule.input_value().startswith("In dieser Lektion gilt allgemein"), rule.input_value())
        rule.fill("Gib zu jeder Erklärung ein Beispiel aus dem Berufsalltag.")
        check("N-06 AK4 Bestätigung verlangt", form.locator(".teach-ok").inner_text() == "Bestätigen und speichern")
        form.locator(".teach-ok").click()
        expect(theory.locator(".teach-message")).to_contain_text("für die ganze Lektion", timeout=10000)
        lesson = httpx.get(base + "/api/teacher/lessons/haftungsrecht").json()
        texts = [i["text"] for i in lesson.get("tutor_instructions") or []]
        check("N-06 AK4/AK5 bestätigte Fassung gespeichert",
              texts == ["Verlange den Gesetzesartikel.", "Gib zu jeder Erklärung ein Beispiel aus dem Berufsalltag."],
              str(texts))
        # AK 6: learning history of the teaching session
        page.goto(base + "/teacher")
        page.check("#show-tests")
        page.locator(".seq-item").first.click()
        expect(page.locator("#detail-events")).to_contain_text("Anweisung an den Tutor", timeout=10000)
        check("N-06 AK6 beide Anweisungen im Lernverlauf",
              page.locator("#detail-events").inner_text().count("Anweisung an den Tutor") == 2)
        # AK 5: the editor lists the instructions and deletes single ones
        page.goto(base + "/teacher/lessons/haftungsrecht/edit")
        expect(page.locator("#instructions-list li")).to_have_count(2, timeout=10000)
        page.locator("#instructions-list button[data-a='delete-instruction']").first.click()
        expect(page.locator("#instructions-list li")).to_have_count(1, timeout=10000)
        check("N-06 AK5 Löschen im Editor", "gelöscht" in page.locator("#result").inner_text()
              and len(httpx.get(base + "/api/teacher/lessons/haftungsrecht").json()["tutor_instructions"]) == 1)
        # AK 2: no "Teach the Tutor" in a normal test run
        page.goto(base + "/")
        expect(page.locator("#view-home")).to_be_visible(timeout=10000)
        page.select_option("#lesson-select", "haftungsrecht")
        page.click("#btn-start")
        page.locator("#modal-ok").click()            # existing sequence: start again
        _assessment_to_learning(page)
        check("N-06 AK2 kein «Teach the Tutor» im normalen Testlauf",
              page.locator(".msg.tutor").count() > 0 and page.locator(".teach-btn").count() == 0)
        check("N-06 ohne Skriptfehler", not errors, "; ".join(errors))
    with server(TEACHER_PASSWORD="geheim") as base:
        page = launch(pw).new_page()
        page.goto(base + "/?teaching=haftungsrecht")
        page.fill("#name", "Lernende Teaching")
        page.click("#btn-login")
        expect(page.locator("#start-error")).to_contain_text("nur Lehrpersonen", timeout=10000)
        check("N-06 AK1 Lernende können den Teaching Mode nicht starten",
              page.locator("#view-learn").is_hidden() and page.locator(".teach-btn").count() == 0)
        page.select_option("#lesson-select", "haftungsrecht")
        page.click("#btn-start")
        _assessment_to_learning(page)
        check("N-06 AK2 kein «Teach the Tutor» in Sequenzen von Lernenden",
              page.locator(".msg.tutor").count() > 0 and page.locator(".teach-btn").count() == 0)


@scenario("t28")
def t28_stoppen(pw):
    """T-28: «Stoppen» während der Tutor arbeitet; die Nachricht steht wieder im Feld."""
    with server(ITS_MOCK_DELAY="1.5") as base:
        page = launch(pw).new_page()
        start_lernsequenz(page, base, name="Stopp-UI")
        # Verständnisfrage stoppen
        page.fill("#chat-input", "Was ist eigentlich ein Schaden?")
        page.click("#btn-ask")
        expect(page.locator("#btn-stopp")).to_be_visible(timeout=5000)
        check("T-28 Stopp-Button bleibt klickbar, während die Aktionsbuttons gesperrt sind",
              page.locator("#btn-stopp").is_enabled() and page.locator("#btn-ask").is_disabled())
        page.click("#btn-stopp")
        page.wait_for_selector("#waiting", state="detached", timeout=10000)
        tutor_vorher = page.locator(".msg.tutor").count()
        check("T-28 Frage steht wieder im Eingabefeld",
              page.locator("#chat-input").input_value() == "Was ist eigentlich ein Schaden?")
        check("T-28 gestoppte Nachricht markiert, Hinweis im Chat",
              page.locator(".msg.user.gestoppt").count() == 1 and "Gestoppt" in page.locator(".note").last.inner_text())
        page.wait_for_timeout(2500)
        check("T-28 keine verspätete Antwort im Chat", page.locator(".msg.tutor").count() == tutor_vorher,
              f"{tutor_vorher} -> {page.locator('.msg.tutor').count()}")
        # Antwort stoppen: Sie zählt nicht und lässt sich danach ohne neue Sicherheitsfrage senden
        page.click("#btn-continue")
        page.wait_for_selector("#waiting", state="detached", timeout=30000)
        page.fill("#chat-input", "Eine Antwort, die ich zu früh abgeschickt habe, mit genug Text.")
        page.click("#btn-answer")
        page.locator("#confidence-buttons button[data-v='6']").click()
        expect(page.locator("#btn-stopp")).to_be_visible(timeout=5000)
        page.click("#btn-stopp")
        page.wait_for_selector("#waiting", state="detached", timeout=10000)
        check("T-28 Antwort zurück im Feld",
              page.locator("#chat-input").input_value().startswith("Eine Antwort, die ich zu früh"))
        check("T-28 gestoppte Antwort zählt nicht", "0 richtig" in page.inner_text("#prog-badges")
              or "richtig" not in page.inner_text("#prog-badges"), page.inner_text("#prog-badges"))
        page.click("#btn-answer")
        check("T-28 keine zweite Sicherheitsfrage", page.locator("#confidence-box").is_hidden())
        page.wait_for_selector("#waiting", state="detached", timeout=30000)
        expect(page.locator(".msg.tutor.good, .msg.tutor.mid, .msg.tutor.bad").last).to_be_visible(timeout=10000)
        page.goto(base + "/teacher")
        page.locator(".seq-item").first.click()
        expect(page.locator("#detail-events")).to_contain_text("Bearbeitung gestoppt", timeout=10000)
        check("T-28 Lehrperson sieht beide Stopps",
              page.locator("#detail-events").inner_text().count("Bearbeitung gestoppt") == 2)


@scenario("t30")
def t30_rag(pw):
    """T-29/T-30: Mit ChromaDB: Index im Katalog, Fundstelle unter der Theorie, Abrufe im Lernverlauf."""
    try:
        import chromadb  # noqa: F401
    except ImportError:
        check("T-30 übersprungen (chromadb fehlt)", True)
        return
    port = _free_port()
    pfad = tempfile.mkdtemp(prefix="its_ui_chroma_")
    chroma = Path(sys.executable).parent / "chroma"
    proc = subprocess.Popen([str(chroma), "run", "--path", pfad, "--port", str(port)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(150):
            try:
                if httpx.get(f"http://127.0.0.1:{port}/api/v2/heartbeat", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.1)
        with server(ITS_VEKTOR_DB_URL=f"http://127.0.0.1:{port}", ITS_CHUNK_GROESSE="300",
                    ITS_CHUNK_OVERLAP="60") as base:
            pfade = _testdateien(Path(tempfile.mkdtemp(prefix="its_ui_dateien_")))
            c = httpx.Client(base_url=base)
            with open(pfade["haftung.pdf"], "rb") as f:
                m = c.post("/api/teacher/materialien", files={"file": ("haftung.pdf", f.read())},
                           data={"name": "OR Haftpflicht"}).json()
            for _ in range(50):
                if c.get(f"/api/teacher/materialien/{m['id']}").json()["index_status"] == "bereit":
                    break
                time.sleep(0.2)
            lid = c.post("/api/teacher/lessons", json={
                "titel": "RAG im Browser", "lernziele": ["Die Tierhalterhaftung erklaeren"], "material": "",
                "materialien": [m["id"]], "einstellungen": {"materialzugriff": "auszuege"}}).json()["id"]
            page = launch(pw).new_page(viewport={"width": 1300, "height": 900})
            page.goto(base + "/teacher/materialien")
            expect(page.locator(".itsm-index.bereit")).to_be_visible(timeout=10000)
            check("T-29 Stand «Index bereit» in der Ablage", True)
            page.locator("button[data-a=details]").first.click()
            box = page.locator(".itsm-box")
            expect(box).to_contain_text("mock-wortstamm-256", timeout=10000)
            check("T-29 Details nennen Modell, Chunks und Overlap",
                  "Overlap 60 Zeichen" in box.inner_text() and "Chunks" in box.inner_text(), box.inner_text()[:400])
            page.goto(base + "/")
            start_lernsequenz(page, base, name="RAG-UI", lesson=lid)
            quelle = page.locator(".msg.tutor.theory .quelle").last
            expect(quelle).to_contain_text("OR Haftpflicht, S.", timeout=10000)
            check("T-30 Fundstelle mit Seite unter der Theorie", True)
            page.fill("#chat-input", "Wer haftet für ein Tier?")
            page.click("#btn-ask")
            page.wait_for_selector("#waiting", state="detached", timeout=30000)
            check("T-30 Quellen unter der Chat-Antwort",
                  "OR Haftpflicht, S." in page.locator(".msg.tutor").last.inner_text())
            page.goto(base + "/teacher")
            page.locator(".seq-item").first.click()
            expect(page.locator("#detail-events")).to_contain_text("Auszüge", timeout=10000)
            check("T-30 Abrufe mit Ähnlichkeit im Lernverlauf",
                  "Ähnlichkeit" in page.locator("#detail-events").inner_text())
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        shutil.rmtree(pfad, ignore_errors=True)

def run(names):
    with sync_playwright() as pw:
        for name in names:
            print(f"Szenario {name}: {SCENARIOS[name].__doc__.strip().splitlines()[0]}")
            LEGENDE_FEHLER.clear()
            try:
                SCENARIOS[name](pw)
            except Exception as e:   # Szenario abgebrochen = Fehler
                check(f"{name} lief durch", False, f"{type(e).__name__}: {e}")
            check(f"T-25 AK3 Legende nennt in «{name}» nur sichtbare Buttons", not LEGENDE_FEHLER,
                  "; ".join(LEGENDE_FEHLER[:3]))
    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(failed)} von {len(RESULTS)} Prüfungen bestanden.")
    return 1 if failed else 0


if __name__ == "__main__":
    wanted = sys.argv[1:] or list(SCENARIOS)
    sys.exit(run(wanted))
