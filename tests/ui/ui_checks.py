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


def check(name: str, cond: bool, detail: str = ""):
    RESULTS.append((name, bool(cond), detail))
    print(("  OK   " if cond else "  FEHLER ") + name + (f" – {detail}" if detail and not cond else ""))


def api_requests(page, pattern: str) -> list:
    """Sammelt alle Anfragen, deren URL das Muster enthält."""
    seen = []
    page.on("request", lambda r: seen.append(r.url) if pattern in r.url else None)
    return seen


# ---------------------------------------------------------------- Hilfen

def start_lernsequenz(page, base: str, name: str = "UI-Test", lesson: str = "haftungsrecht"):
    """Meldet sich auf der Startseite an und startet eine Lektion bis zum Chat."""
    page.goto(base + "/")
    page.fill("#name", name)
    expect(page.locator("#lesson-picker")).to_be_visible()
    page.select_option("#lesson-select", lesson)
    page.click("#btn-start")
    expect(page.locator("#view-assess")).to_be_visible(timeout=30000)
    for _ in range(3):
        page.fill("#assess-answer", "weiss ich nicht")
        page.click("#btn-assess")
    expect(page.locator("#view-learn")).to_be_visible(timeout=60000)


# ---------------------------------------------------------------- Szenarien

@scenario("t01")
def t01_nochmals_versuchen(pw):
    """T-01 AK2: Scheitern beide Aufrufe, erscheint eine brauchbare Ausgabe."""
    with server(ITS_MOCK_FAIL="THEORIE_SCHRITT") as base:
        page = pw.chromium.launch().new_page()
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
        page = pw.chromium.launch().new_page()
        start_lernsequenz(page, base, lesson="leer")
        expect(page.locator(".msg.tutor.bad").last).to_contain_text("technischen Problems", timeout=30000)
        btn = page.locator("#btn-continue")
        check("T-01 Button «Nochmals versuchen» sichtbar",
              btn.is_visible() and "Nochmals versuchen" in btn.inner_text())
        reqs = api_requests(page, "/next")
        btn.click()
        expect(page.locator(".msg.tutor.bad")).to_have_count(2, timeout=30000)
        check("T-01 «Nochmals versuchen» fordert den Schritt neu an", len(reqs) == 1, str(reqs))


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
