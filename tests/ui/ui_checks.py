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
    """T-01 AK2: Scheitern beide Aufrufe, erscheint eine brauchbare Ausgabe."""
    with server(ITS_MOCK_FAIL="THEORIE_SCHRITT") as base:
        page = launch(pw).new_page()
        start_lernsequenz(page, base)
        theorie = page.locator(".msg.tutor.theory").last
        expect(theorie).to_be_visible(timeout=30000)
        text = theorie.inner_text()
        check("T-01 Theorie-Fallback zeigt Materialtext",
              "Lektionsmaterial" in text and "Art. 41 OR" in text, text[:120])
        check("T-01 keine leere Ankündigung", "folgenden Abschnitt" not in text)


@scenario("t01b")
def t01_button_nochmals_versuchen(pw):
    """T-01 AK2: Ohne bestimmbaren Abschnitt erscheint «Nochmals versuchen»."""
    leer = {"id": "leer", "titel": "Leere Lektion", "lernziele": ["Etwas verstehen"],
            "material": "Kurz.", "einstufungsfragen_fallback": ["a?", "b?", "c?"]}
    with server(extra_lessons={"leer": leer}, ITS_MOCK_FAIL="THEORIE_SCHRITT") as base:
        page = launch(pw).new_page()
        start_lernsequenz(page, base, lesson="leer")
        expect(page.locator(".msg.tutor.bad").last).to_contain_text("technischen Problems", timeout=30000)
        btn = page.locator("#btn-continue")
        check("T-01 Button «Nochmals versuchen» sichtbar",
              btn.is_visible() and "Nochmals versuchen" in btn.inner_text())
        reqs = api_requests(page, "/next")
        btn.click()
        expect(page.locator(".msg.tutor.bad")).to_have_count(2, timeout=30000)
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
