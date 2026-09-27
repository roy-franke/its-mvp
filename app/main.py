"""ITS-MVP – FastAPI-Backend.

Lernenden-Flow:
  POST /api/session/start           -> Session + Einstufungsfragen
  POST /api/session/{id}/assess     -> Einstufung bewerten, Profil anlegen
  POST /api/session/{id}/next       -> nächste Aufgabe
  POST /api/session/{id}/answer     -> Antwort bewerten, Adaption, Feedback
  GET  /api/session/{id}/state      -> aktueller Zustand (Fortsetzen möglich)

Lehrpersonen-Sicht (Monitoring light):
  GET  /api/teacher/sessions        -> Übersicht aller Sessions
  GET  /api/teacher/sessions/{id}   -> vollständiger Lernverlauf (Event-Log)
"""

import io
import json
import logging
import os
import re
import unicodedata
from pathlib import Path

from dotenv import load_dotenv

# .env ausdrücklich aus dem Projektordner laden, unabhängig vom Arbeitsordner.
# Bereits gesetzte Umgebungsvariablen haben Vorrang (so auch in den Tests).
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import APIRouter, Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import auth, llm, store, tutor

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("its")

BASE = Path(__file__).resolve().parent.parent
LESSONS_DIR = Path(os.getenv("ITS_LESSONS_DIR") or BASE / "app" / "lessons")
LESSONS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="ITS MVP")
store.init_db()
# Beim Start sichtbar machen, welcher Schutz aktiv ist (T-04: Passwortproblem
# war von aussen nicht erkennbar).
log.info("Zugangsschutz Lehrpersonen: %s | Klassencode: %s | Header-Anmeldung: %s",
         "aktiv" if auth.auth_enabled() else "AUS (TEACHER_PASSWORD leer)",
         "aktiv" if auth.class_code() else "aus",
         f"aktiv ({auth.user_header()}, {auth.roles_header()})" if auth.trust_headers() else "aus")

# Rollenprüfung zentral als Abhängigkeit der Router (T-04): Jede Route unter
# /api/teacher und /teacher ist damit geschützt, ohne dass sie einzeln daran
# denken muss. Ausnahmen (Login, Logout) hängen bewusst direkt an `app`.
teacher_api = APIRouter(prefix="/api/teacher", dependencies=[Depends(auth.require_teacher)])
teacher_pages = APIRouter(prefix="/teacher", dependencies=[Depends(auth.require_teacher_page)])


@app.middleware("http")
async def block_static_pages(request: Request, call_next):
    """HTML-Seiten nur über ihre Routen ausliefern.

    Ohne diese Sperre war /static/teacher.html am Login vorbei erreichbar,
    weil StaticFiles den ganzen Ordner ausliefert.
    """
    if request.url.path.startswith("/static/") and request.url.path.endswith(".html"):
        return Response("Nicht gefunden", status_code=404)
    return await call_next(request)


def load_lesson(lesson_id: str) -> dict:
    path = LESSONS_DIR / f"{lesson_id}.json"
    if not path.exists():
        raise HTTPException(404, f"Lektion '{lesson_id}' nicht gefunden")
    return json.loads(path.read_text(encoding="utf-8"))


def default_lesson_id() -> str:
    files = sorted(LESSONS_DIR.glob("*.json"))
    if not files:
        raise HTTPException(500, "Keine Lektion vorhanden")
    return files[0].stem


# ---------------------------------------------------------------- Requests

class StartRequest(BaseModel):
    name: str | None = None   # ohne Name: angemeldete Identität (Cookie oder Header)
    lesson_id: str | None = None
    code: str | None = None   # Zugangscode der Klasse (falls konfiguriert)
    pin: str | None = None    # optionale PIN (Entscheid E7)
    neu_beginnen: bool = False  # bestehende Sequenz dieser Lektion archivieren


class AssessRequest(BaseModel):
    answers: list[str]


class AnswerRequest(BaseModel):
    answer: str
    confidence: int | None = None   # Sicherheitsangabe 1-10 vor der Bewertung


class ChatRequest(BaseModel):
    message: str


class LessonSource(BaseModel):
    """Eine hochgeladene Quelldatei – nur Metadaten, der Text steckt in `material`."""
    name: str
    chars: int = 0


class LessonCreateRequest(BaseModel):
    titel: str
    lernziele: list[str]
    material: str
    tutor_hinweise: str = ""
    quellen: list[LessonSource] = []


class SuggestGoalsRequest(BaseModel):
    material: str


class TeacherLoginRequest(BaseModel):
    password: str


# ---------------------------------------------------------------- Lektionen

@app.get("/api/lessons")
def lessons_list():
    """Verfügbare Lektionen – für die Auswahl beim Start."""
    out = []
    for p in sorted(LESSONS_DIR.glob("*.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        out.append({"id": p.stem, "titel": data.get("titel", p.stem)})
    return out


@teacher_api.post("/lessons")
def lesson_create(req: LessonCreateRequest):
    """Neue Lektion anlegen (Lehrpersonen-Modul light)."""
    titel = req.titel.strip()
    material = req.material.strip()
    ziele = [z.strip() for z in req.lernziele if z.strip()]
    if not titel:
        raise HTTPException(400, "Titel fehlt")
    if len(material) < 100:
        raise HTTPException(400, "Material ist zu kurz (mindestens 100 Zeichen), "
                                 "damit der Tutor sinnvoll arbeiten kann")
    if not ziele:
        raise HTTPException(400, "Mindestens ein Lernziel angeben")
    lesson_id = _unique_slug(titel)
    lesson = {
        "id": lesson_id,
        "titel": titel,
        "lernziele": ziele,
        "material": material,
        "quellen": [{"name": q.name, "chars": q.chars} for q in req.quellen],
        "tutor_hinweise": req.tutor_hinweise.strip(),
        "einstufungsfragen_fallback": [
            "Was weisst du bereits zu diesem Thema? Beschreibe es in eigenen Worten.",
            "Nenne ein Beispiel aus dem Alltag, das zu diesem Thema passt.",
            "Welche Fachbegriffe zu diesem Thema kennst du schon?",
        ],
    }
    path = LESSONS_DIR / f"{lesson_id}.json"
    path.write_text(json.dumps(lesson, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Lektion erstellt: %s", lesson_id)
    return {"id": lesson_id, "titel": titel}


@teacher_api.post("/lessons/extract")
async def lesson_extract(file: UploadFile = File(...)):
    """Extrahiert Text aus einer hochgeladenen Datei (PDF, Word, Text)."""
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(400, "Datei zu gross (max. 10 MB)")
    text = _extract_text(file.filename or "", data)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) < 50:
        raise HTTPException(400, "Aus dieser Datei liess sich kaum Text extrahieren. "
                                 "Ist es ein gescanntes PDF ohne Textebene?")
    return {"filename": file.filename, "text": text, "chars": len(text)}


@teacher_api.post("/lessons/suggest-goals")
def lesson_suggest_goals(req: SuggestGoalsRequest):
    """KI-Vorschlag für Titel und Lernziele aus dem Material."""
    if len(req.material.strip()) < 100:
        raise HTTPException(400, "Zuerst Material einfügen (mindestens 100 Zeichen)")
    return tutor.suggest_goals(req.material)


def _extract_text(filename: str, data: bytes) -> str:
    name = filename.lower()
    if name.endswith((".txt", ".md")):
        return data.decode("utf-8", errors="replace")
    if name.endswith(".docx"):
        try:
            import docx
        except ImportError:
            raise HTTPException(500, "python-docx nicht installiert: pip install python-docx")
        d = docx.Document(io.BytesIO(data))
        return "\n".join(p.text for p in d.paragraphs if p.text.strip())
    if name.endswith(".pdf"):
        try:
            from pypdf import PdfReader
        except ImportError:
            raise HTTPException(500, "pypdf nicht installiert: pip install pypdf")
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    raise HTTPException(400, "Unterstützte Formate: .pdf, .docx, .txt, .md")


def _unique_slug(titel: str) -> str:
    s = unicodedata.normalize("NFKD", titel).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower() or "lektion"
    slug, n = s, 2
    while (LESSONS_DIR / f"{slug}.json").exists():
        slug = f"{s}-{n}"
        n += 1
    return slug


# ---------------------------------------------------------------- Lernende

@app.post("/api/session/start")
def start_session(req: StartRequest, request: Request, response: Response):
    """Startet eine Lernsequenz für die angemeldete Person.

    Pro Person und Lektion gibt es höchstens eine nicht archivierte Sequenz
    (T-05). Existiert bereits eine, antwortet der Server mit 409, und die
    Oberfläche fragt nach. Mit neu_beginnen=true wird die bestehende Sequenz
    archiviert und eine neue angelegt.
    """
    ident = auth.identity(request)
    if req.name and (ident.via != "header") and auth.normalize_user(req.name) != ident.key:
        name = _login_learner(request, response, req.name, req.code, req.pin)
    elif ident.name:
        name = ident.name
    else:
        name = _login_learner(request, response, req.name, req.code, req.pin)
    user_key = auth.normalize_user(name)
    lesson_id = req.lesson_id or default_lesson_id()
    lesson = load_lesson(lesson_id)
    bestehend = store.open_session_for(user_key, lesson_id)
    if bestehend:
        if not req.neu_beginnen:
            raise HTTPException(409, detail={
                "code": "sequenz_existiert", "session_id": bestehend["id"],
                "status": bestehend["status"],
                "message": "Zu dieser Lektion gibt es bereits eine Lernsequenz."})
        store.set_status(bestehend["id"], "archiviert", "Neu begonnen")
    profile = tutor.new_profile()
    testlauf = ident.is_teacher
    sid = store.create_session(name, lesson_id, profile, testlauf=testlauf, user_key=user_key)
    questions = tutor.generate_assessment(lesson)
    store.log_event(sid, "session_started", {"name": name, "lesson": lesson["titel"],
                                             "testlauf": testlauf})
    store.log_event(sid, "assessment_questions", {"questions": questions})
    profile["assessment_questions"] = questions
    store.update_session(sid, profile=profile)
    return {
        "session_id": sid,
        "lesson": {"titel": lesson["titel"], "lernziele": lesson["lernziele"]},
        "questions": questions,
        "total_steps": tutor.total_steps(),
    }


@app.post("/api/session/{sid}/assess")
def assess(sid: str, req: AssessRequest, request: Request):
    s = _owned(request, sid, aktion=True)
    lesson = load_lesson(s["lesson_id"])
    profile = s["profile"]
    questions = profile.get("assessment_questions", [])
    result = tutor.evaluate_assessment(lesson, questions, req.answers)
    _log_llm_meta(sid, "EINSTUFUNG_BEWERTEN", result)
    profile["level"] = result["level"]
    store.log_event(sid, "assessment_evaluated", {
        "answers": req.answers, "level": result["level"],
        "begruendung": result.get("begruendung", ""),
    })
    profile["wartet_auf"] = "weiter"
    store.update_session(sid, phase="learning", profile=profile)
    return {
        "level": result["level"],
        "level_label": tutor.LEVEL_LABELS[result["level"]],
        "begruendung": result.get("begruendung", ""),
    }


SCHRITTART = {"theorie": "THEORIE_SCHRITT", "aufgabe": "NAECHSTE_AUFGABE"}


def _log_llm_meta(sid: str, schrittart: str, data: dict):
    """Protokolliert Fallbacks und Regelverstösse eines LLM-Ergebnisses (T-01)."""
    if data.get("_fallback"):
        store.log_event(sid, "fallback_used", {
            "schrittart": schrittart, "grund": data.get("_fehler", "unbekannt")})
    if data.get("_verstoesse"):
        store.log_event(sid, "regel_verstoss", {
            "schrittart": schrittart, "verstoesse": data["_verstoesse"],
            "behoben": data.get("_versuche", 1) > 1 and len(data["_verstoesse"]) < data["_versuche"]})


def _generate_step(lesson: dict, profile: dict, history: list[dict],
                   adaptation: str | None) -> tuple[str, dict]:
    step_type = tutor.decide_step_type(profile, adaptation)
    if step_type == "theorie":
        return step_type, tutor.generate_theory(lesson, profile, history, adaptation)
    return step_type, tutor.generate_task(lesson, profile, history, adaptation)


def _vorabruf_ungueltig(pre: dict, sid: str, profile: dict, adaptation: str | None) -> str | None:
    """Prüft, ob ein vorab erzeugter Schritt noch zum Gesprächsstand passt."""
    if pre.get("stand") != store.last_event_id(sid):
        return "Gesprächsstand hat sich seit dem Vorabruf geändert"
    if (pre.get("adaptation") or "") != (adaptation or ""):
        return "andere Adaption angefordert"
    if pre.get("step") != profile["step"]:
        return "Lernschritt hat sich geändert"
    if pre.get("step_type") != tutor.decide_step_type(profile, adaptation):
        return "andere Schrittart fällig"
    if pre.get("task", {}).get("_fallback"):
        return "Vorabruf endete im Fallback, neuer Versuch"
    return None


@app.post("/api/session/{sid}/next")
def next_step(sid: str, request: Request, adaptation: str | None = None,
              prefetch: bool = False):
    """Nächster Lernschritt.

    Mit prefetch=true wird der Schritt nur vorbereitet und separat gespeichert,
    ohne Profil oder Lernverlauf zu verändern. Der eigentliche Aufruf übernimmt
    ihn, wenn sich der Gesprächsstand seither nicht geändert hat, sonst wird
    neu erzeugt (T-01: veraltete Vorabrufe nach einer Verständnisfrage).
    """
    s = _owned(request, sid, aktion=not prefetch)
    if prefetch and s["status"] != "aktiv":
        return {"vorabruf": False, "done": False}
    lesson = load_lesson(s["lesson_id"])
    profile = s["profile"]
    if profile["step"] >= tutor.total_steps():
        if prefetch:
            return {"vorabruf": True, "done": True}
        return _finish(sid, lesson, profile)
    if prefetch:
        stand = store.last_event_id(sid)
        step_type, task = _generate_step(lesson, profile, store.get_events(sid), adaptation)
        store.set_vorabruf(sid, {"stand": stand, "adaptation": adaptation or "",
                                 "step": profile["step"], "step_type": step_type,
                                 "task": task})
        return {"vorabruf": True, "done": False}

    task = None
    pre = store.get_vorabruf(sid)
    if pre:
        store.set_vorabruf(sid, None)
        grund = _vorabruf_ungueltig(pre, sid, profile, adaptation)
        if grund:
            store.log_event(sid, "vorabruf_verworfen", {"grund": grund})
        else:
            step_type, task = pre["step_type"], pre["task"]
    if task is None:
        step_type, task = _generate_step(lesson, profile, store.get_events(sid), adaptation)
    return _commit_step(sid, profile, step_type, task)


def _commit_step(sid: str, profile: dict, step_type: str, task: dict) -> dict:
    """Übernimmt einen erzeugten Schritt in Profil und Lernverlauf."""
    _log_llm_meta(sid, SCHRITTART[step_type], task)
    public_task = llm.public(task)
    if task.get("_fallback"):
        public_task["fallback"] = True
    if task.get("typ") == "fehler":
        # Nichts erzeugt: Profil bleibt, damit «Nochmals versuchen» denselben
        # Schritt erneut anfordert.
        profile["current_task"] = public_task
        profile["wartet_auf"] = "nochmals"
        store.log_event(sid, "task", public_task)
        store.update_session(sid, profile=profile)
        return {"done": False, "task": public_task, "progress": _progress(profile)}
    if step_type == "theorie":
        profile["theory_steps"] = profile.get("theory_steps", 0) + 1
    if "material_abschnitt" in task:
        profile.setdefault("fallback_abschnitte", []).append(task["material_abschnitt"])
    profile["current_task"] = public_task
    profile["last_type"] = step_type
    profile["wartet_auf"] = "weiter" if step_type == "theorie" else "antwort"
    profile["letztes_feedback"] = None
    concept = task.get("konzept")
    if concept and concept not in profile["covered"]:
        profile["covered"].append(concept)
    store.log_event(sid, "task", public_task)
    store.update_session(sid, profile=profile)
    return {
        "done": False,
        "task": public_task,
        "progress": _progress(profile),
    }


@app.post("/api/session/{sid}/answer")
def answer(sid: str, req: AnswerRequest, request: Request):
    s = _owned(request, sid, aktion=True)
    lesson = load_lesson(s["lesson_id"])
    profile = s["profile"]
    task = profile.get("current_task")
    if not task:
        raise HTTPException(400, "Keine aktive Aufgabe – rufe zuerst /next auf")
    if task.get("typ") == "theorie":
        raise HTTPException(400, "Der aktuelle Schritt ist Theorie – es gibt "
                                 "nichts zu bewerten. Weiter mit /next")
    confidence = req.confidence if req.confidence in range(1, 11) else None
    store.log_event(sid, "answer_submitted",
                    {"answer": req.answer, "confidence": confidence})
    result = tutor.evaluate_answer(lesson, profile, task, req.answer)
    _log_llm_meta(sid, "ANTWORT_BEWERTEN", result)
    if result["bewertung"] == "unbewertet":
        # Technischer Fehler bei der Bewertung: zählt weder als richtig noch
        # als falsch, die lernende Person schickt die Antwort nochmals ab.
        store.log_event(sid, "answer_evaluated", {
            "bewertung": "unbewertet", "korrekt": False,
            "feedback": result.get("feedback", ""), "hinweis": result.get("hinweis", ""),
            "adaption": "retry", "adaption_begruendung": "", "level": profile["level"],
        })
        return {"bewertung": "unbewertet", "korrekt": False,
                "feedback": result.get("feedback", ""), "hinweis": result.get("hinweis", ""),
                "adaption": "retry", "adaption_begruendung": "", "finished": False,
                "progress": _progress(profile)}
    if confidence is not None:
        profile.setdefault("confidence", []).append(confidence)
    action, reason = tutor.adapt(profile, result["bewertung"])
    store.log_event(sid, "answer_evaluated", {
        "bewertung": result["bewertung"], "korrekt": result["korrekt"],
        "feedback": result.get("feedback", ""),
        "hinweis": result.get("hinweis", ""), "adaption": action,
        "adaption_begruendung": reason, "level": profile["level"],
    })
    finished = profile["step"] >= tutor.total_steps() and action != "retry"
    profile["wartet_auf"] = "antwort" if action == "retry" else "weiter"
    profile["letztes_feedback"] = {
        "bewertung": result["bewertung"], "feedback": result.get("feedback", ""),
        "hinweis": result.get("hinweis", ""), "adaption": action,
        "adaption_begruendung": reason, "finished": finished,
    }
    store.update_session(sid, profile=profile)
    return {
        "bewertung": result["bewertung"],   # korrekt | teilweise | falsch
        "korrekt": result["korrekt"],
        "feedback": result.get("feedback", ""),
        "hinweis": result.get("hinweis", ""),
        "adaption": action,           # next | advance | retry | simplify
        "adaption_begruendung": reason,
        "finished": finished,
        "progress": _progress(profile),
    }


@app.post("/api/session/{sid}/chat")
def chat_with_tutor(sid: str, req: ChatRequest, request: Request):
    """Verständnisfrage des Lernenden im Dialog – jederzeit möglich."""
    s = _owned(request, sid, aktion=True)
    lesson = load_lesson(s["lesson_id"])
    profile = s["profile"]
    message = req.message.strip()
    if not message:
        raise HTTPException(400, "Leere Nachricht")
    store.log_event(sid, "chat_question", {"frage": message})
    history = store.get_events(sid)
    result = tutor.answer_question(lesson, profile, profile.get("current_task"),
                                   message, history)
    _log_llm_meta(sid, "FRAGE_BEANTWORTEN", result)
    antwort = result.get("antwort", "")
    store.log_event(sid, "chat_reply", {"antwort": antwort})
    return {"antwort": antwort}


@app.get("/api/session/{sid}/state")
def state(sid: str, request: Request):
    """Aktueller Zustand einer Session – Basis für Pausieren/Fortsetzen.

    `wartet_auf` sagt der Oberfläche, wo es weitergeht: einstufung, antwort
    (Aufgabe offen), weiter (Theorie gelesen oder Feedback erhalten),
    nochmals (technischer Fehler) oder abschluss.
    """
    s = _owned(request, sid)
    return _state(s)


def _state(s: dict) -> dict:
    lesson = load_lesson(s["lesson_id"])
    p = s["profile"]
    if s["phase"] == "assessment":
        wartet = "einstufung"
    elif s["phase"] == "finished":
        wartet = "abschluss"
    else:
        wartet = p.get("wartet_auf") or ("antwort" if (p.get("current_task") or {}).get("typ") == "aufgabe" else "weiter")
    return {
        "session_id": s["id"],
        "name": s["name"],
        "phase": s["phase"],
        "status": s["status"],
        "lesson_id": s["lesson_id"],
        "lesson": {"titel": lesson["titel"], "lernziele": lesson["lernziele"]},
        "progress": _progress(p),
        "current_task": p.get("current_task"),
        "wartet_auf": wartet,
        "letztes_feedback": p.get("letztes_feedback"),
        "questions": p.get("assessment_questions", []) if wartet == "einstufung" else [],
        "total_steps": tutor.total_steps(),
    }


@app.post("/api/session/{sid}/fortsetzen")
def resume(sid: str, request: Request):
    """Setzt eine pausierte Sequenz fort und liefert den Stand zum Anzeigen."""
    s = _owned(request, sid, aktion=True)
    ident = auth.identity(request)
    if ident.key != s["user_key"] and ident.is_teacher:
        raise HTTPException(403, "Lehrpersonen können fremde Sequenzen nur ansehen.")
    return _state(store.get_session(sid))


def _eigene(request: Request, sid: str) -> dict:
    """Wie _owned, aber nur für die Person, der die Sequenz gehört."""
    s = _owned(request, sid)
    if auth.identity(request).key != s["user_key"]:
        raise HTTPException(403, "Nur die lernende Person selbst kann das tun.")
    return s


@app.post("/api/session/{sid}/pausieren")
def pause(sid: str, request: Request):
    """«Pausieren und später weiterfahren» (T-06): Stand bleibt gespeichert."""
    s = _eigene(request, sid)
    if s["status"] != "aktiv":
        raise HTTPException(409, f"Die Lernsequenz ist {s['status']} und kann nicht pausiert werden.")
    store.set_status(sid, "pausiert", "Von der lernenden Person pausiert")
    store.set_vorabruf(sid, None)
    return {"ok": True, "status": "pausiert"}


@app.post("/api/session/{sid}/abbrechen")
def abort(sid: str, request: Request):
    """«Lektion abbrechen» (T-06): Sequenz endet, kann neu begonnen werden."""
    s = _eigene(request, sid)
    if s["status"] not in ("aktiv", "pausiert"):
        raise HTTPException(409, f"Die Lernsequenz ist {s['status']} und kann nicht abgebrochen werden.")
    store.set_status(sid, "abgebrochen", "Von der lernenden Person abgebrochen")
    store.set_vorabruf(sid, None)
    return {"ok": True, "status": "abgebrochen"}


@app.get("/api/me/sequenzen")
def my_sequences(request: Request):
    """Die nicht archivierten Lernsequenzen der angemeldeten Person (T-05)."""
    ident = auth.identity(request)
    if not ident.key:
        raise HTTPException(401, "Bitte melde dich zuerst an.")
    titel = _lesson_titles()
    out = []
    for s in store.sessions_of_user(ident.key):
        p = s["profile"]
        out.append({
            "session_id": s["id"], "lesson_id": s["lesson_id"],
            "lesson_titel": titel.get(s["lesson_id"], s["lesson_id"]),
            "status": s["status"], "phase": s["phase"],
            "step": p.get("step", 0), "total_steps": tutor.total_steps(),
            "level": p.get("level", "basic"),
            "level_label": tutor.LEVEL_LABELS.get(p.get("level", "basic"), ""),
            "updated_at": s["updated_at"],
            "fortsetzbar": s["status"] in ("aktiv", "pausiert"),
        })
    return out


def _lesson_titles() -> dict[str, str]:
    out = {}
    for p in LESSONS_DIR.glob("*.json"):
        try:
            out[p.stem] = json.loads(p.read_text(encoding="utf-8")).get("titel", p.stem)
        except (OSError, json.JSONDecodeError):
            out[p.stem] = p.stem
    return out


def _finish(sid: str, lesson: dict, profile: dict):
    # Idempotent: Wurde die Session bereits abgeschlossen, die gespeicherte
    # Zusammenfassung wiederverwenden statt neu zu generieren und doppelt zu loggen.
    for ev in reversed(store.get_events(sid)):
        if ev["type"] == "finished":
            return {"done": True, "summary": ev["payload"], "progress": _progress(profile)}
    history = store.get_events(sid)
    summary = tutor.generate_summary(lesson, profile, history)
    _log_llm_meta(sid, "ABSCHLUSS", summary)
    summary = llm.public(summary)
    store.log_event(sid, "finished", summary)
    store.update_session(sid, phase="finished", profile=profile)
    store.set_status(sid, "abgeschlossen")
    return {"done": True, "summary": summary, "progress": _progress(profile)}


def _progress(profile: dict) -> dict:
    return {
        "step": profile["step"],
        "total_steps": tutor.total_steps(),
        "level": profile["level"],
        "level_label": tutor.LEVEL_LABELS[profile["level"]],
        "correct": profile["correct"],
        "wrong": profile["wrong"],
        "correct_rate": tutor.correct_rate(profile),
        "covered": profile["covered"],
        "theory_steps": profile.get("theory_steps", 0),
        "partial": profile.get("partial", 0),
        "confidence_avg": (round(sum(c) / len(c), 1)
                           if (c := profile.get("confidence", [])) else None),
    }


def _session(sid: str) -> dict:
    s = store.get_session(sid)
    if s is None:
        raise HTTPException(404, "Session nicht gefunden")
    return s


def _owned(request: Request, sid: str, aktion: bool = False) -> dict:
    """Lädt eine Session und prüft, ob sie der anfragenden Person gehört.

    Lehrpersonen dürfen jede Session lesen. Lernende nur ihre eigenen; die
    Zuordnung läuft über den Benutzernamen, nicht über die Session-ID (T-05).
    Mit aktion=True wird zusätzlich geprüft, ob in der Sequenz noch gelernt
    werden darf. Eine pausierte Sequenz wird dabei automatisch fortgesetzt.
    """
    s = _session(sid)
    ident = auth.identity(request)
    eigen = ident.key is not None and ident.key == s.get("user_key")
    if not eigen and not ident.is_teacher:
        if ident.key is None:
            raise HTTPException(401, "Bitte melde dich zuerst an.")
        raise HTTPException(403, "Diese Lernsequenz gehört jemand anderem.")
    if aktion:
        if s["status"] in ("abgebrochen", "archiviert"):
            raise HTTPException(409, f"Diese Lernsequenz ist {s['status']} und kann nicht "
                                     "fortgesetzt werden. Du kannst die Lektion neu beginnen.")
        if s["status"] == "pausiert":
            store.set_status(sid, "aktiv", "Weitergelernt")
            s["status"] = "aktiv"
    return s


# ---------------------------------------------------------------- Lehrperson

@teacher_api.get("/sessions")
def teacher_sessions(testlaeufe: bool = False):
    """Monitoring-Übersicht. Testläufe von Lehrpersonen nur mit ?testlaeufe=true (E3)."""
    out = []
    for s in store.list_sessions():
        if s.get("testlauf") and not testlaeufe:
            continue
        p = s["profile"]
        out.append({
            "session_id": s["id"],
            "name": s["name"],
            "lesson_id": s["lesson_id"],
            "phase": s["phase"],
            "step": p.get("step", 0),
            "total_steps": tutor.total_steps(),
            "level": p.get("level", "basic"),
            "correct_rate": tutor.correct_rate(p) if "correct" in p else 0.0,
            "confidence_avg": (round(sum(c) / len(c), 1)
                               if (c := p.get("confidence", [])) else None),
            "covered": p.get("covered", []),
            "testlauf": bool(s.get("testlauf")),
            "status": s.get("status", "aktiv"),
            "status_at": s.get("status_at"),
            "archived_at": s.get("archived_at"),
            "created_at": s["created_at"],
            "updated_at": s["updated_at"],
        })
    return out


@teacher_api.get("/sessions/{sid}")
def teacher_session_detail(sid: str):
    s = _session(sid)
    return {
        "session": {"id": s["id"], "name": s["name"], "phase": s["phase"],
                    "status": s.get("status"), "status_at": s.get("status_at"),
                    "archived_at": s.get("archived_at"),
                    "testlauf": bool(s.get("testlauf")), "profile": s["profile"]},
        "events": store.get_events(sid),
    }


@app.get("/api/access")
def access_info():
    """Sagt dem Frontend, ob ein Zugangscode nötig ist (den Code selbst nie ausliefern)."""
    return {"code_required": bool(auth.class_code()),
            "teacher_login_required": auth.auth_enabled()}


@app.get("/api/me")
def me(request: Request):
    """Wer bin ich? Grundlage für die rollenabhängige Oberfläche (T-04)."""
    ident = auth.identity(request)
    header = ident.via == "header"
    return {
        "angemeldet": bool(ident.name) or ident.is_teacher,
        "name": ident.name,
        "rolle": ident.rolle,
        "lehrperson": ident.is_teacher,
        "name_fixiert": header,
        "header_anmeldung": header,
        "code_required": bool(auth.class_code()) and not header,
        "teacher_login_required": auth.auth_enabled(),
    }


class LearnerLoginRequest(BaseModel):
    name: str
    code: str | None = None
    pin: str | None = None


@app.post("/api/learner/login")
def learner_login(req: LearnerLoginRequest, request: Request, response: Response):
    """Anmeldung für Lernende ohne Header: Name (Pseudonym) plus Klassencode,
    optional mit PIN."""
    name = _login_learner(request, response, req.name, req.code, req.pin)
    user = store.get_user(auth.normalize_user(name)) or {}
    return {"ok": True, "name": name, "pin_gesetzt": bool(user.get("pin_hash"))}


def _login_learner(request: Request, response: Response, name: str | None,
                   code: str | None, pin: str | None = None) -> str:
    """Prüft Anmeldedaten und setzt das Lernenden-Cookie. Gibt den Namen zurück.

    PIN (Entscheid E7): Wer beim ersten Start eine PIN setzt, muss sie bei
    jeder weiteren Anmeldung mit diesem Namen angeben. Ohne PIN genügt der Name;
    wer denselben Namen verwendet, kann dann auch fremde Sequenzen fortsetzen.
    Dieses Risiko ist für den Klassentest bewusst in Kauf genommen.
    """
    ident = auth.identity(request)
    if ident.via == "header":
        return ident.name            # Name kommt vom Proxy und ist nicht änderbar
    name = (name or "").strip()
    if not name:
        raise HTTPException(400, "Bitte einen Namen oder ein Pseudonym eingeben")
    if len(name) > 60:
        raise HTTPException(400, "Der Name ist zu lang (höchstens 60 Zeichen)")
    if not auth.check_class_code(code) and not ident.is_teacher:
        raise HTTPException(403, "Falscher Zugangscode. Frag deine Lehrperson "
                                 "nach dem aktuellen Code.")
    pin = (pin or "").strip()
    if pin and not auth.valid_pin_format(pin):
        raise HTTPException(400, "Die PIN besteht aus genau vier Ziffern.")
    key = auth.normalize_user(name)
    user = store.get_user(key)
    if user and user.get("pin_hash"):
        if not pin:
            raise HTTPException(403, detail={"code": "pin_noetig",
                                             "message": "Für diesen Namen ist eine PIN gesetzt. Bitte gib sie ein."})
        if not auth.verify_pin(pin, user["pin_hash"]):
            raise HTTPException(403, detail={"code": "pin_falsch",
                                             "message": "Die PIN stimmt nicht."})
    else:
        store.ensure_user(key, name)
        if pin:
            store.set_user_pin(key, auth.hash_pin(pin))
    response.set_cookie(auth.LEARNER_COOKIE, auth.make_learner_token(name),
                        max_age=auth.LEARNER_COOKIE_MAX_AGE, httponly=True, samesite="lax")
    return name


@app.post("/api/learner/logout")
def learner_logout(response: Response):
    response.delete_cookie(auth.LEARNER_COOKIE)
    return {"ok": True}


@app.post("/api/teacher/login")
def teacher_login(req: TeacherLoginRequest, response: Response):
    if auth.auth_enabled() and not auth.check_password(req.password):
        raise HTTPException(401, "Falsches Passwort")
    # Auch ohne Passwort (lokale Entwicklung) ein Cookie setzen: Es markiert
    # Lernsequenzen, die eine Lehrperson startet, als Testlauf (E3).
    response.set_cookie(auth.COOKIE_NAME, auth.make_token(),
                        max_age=auth.COOKIE_MAX_AGE, httponly=True, samesite="lax")
    if not auth.auth_enabled():
        return {"ok": True, "hinweis": "Zugangsschutz ist deaktiviert (TEACHER_PASSWORD leer)"}
    return {"ok": True}


@app.get("/teacher/logout")
def teacher_logout():
    r = RedirectResponse("/teacher/login")
    r.delete_cookie(auth.COOKIE_NAME)
    return r


@app.get("/api/info")
def info():
    return {"provider": llm.provider_name(), "model": llm.current_model(),
            "lessons": [p.stem for p in sorted(LESSONS_DIR.glob('*.json'))]}


@teacher_api.get("/timings")
def teacher_timings():
    """Antwortzeiten der letzten LLM-Aufrufe – Grundlage für Optimierungen.

    Die Werte liegen nur im Arbeitsspeicher und sind nach einem Neustart weg.
    Für die Frage «wo gehen die Sekunden hin» genügt das.
    """
    return {
        "provider": llm.provider_name(),
        "modell": llm.current_model(),
        "zusammenfassung": llm.timing_summary(),
        "letzte": list(reversed(llm.timings()))[:20],
    }


@app.get("/api/llm-test", dependencies=[Depends(auth.require_teacher)])
def llm_test():
    """Diagnose: Testet die Verbindung zum konfigurierten LLM und zeigt Fehler an."""
    import time
    t0 = time.time()
    try:
        text = llm.chat("Du bist ein Verbindungstest.",
                        "Antworte mit genau einem Wort: OK")
        return {
            "ok": True,
            "provider": llm.provider_name(),
            "model": llm.current_model(),
            "antwort": text.strip()[:100],
            "dauer_sekunden": round(time.time() - t0, 1),
        }
    except Exception as e:
        return {
            "ok": False,
            "provider": llm.provider_name(),
            "model": llm.current_model(),
            "fehler": f"{type(e).__name__}: {e}",
            "dauer_sekunden": round(time.time() - t0, 1),
        }


# ---------------------------------------------------------------- Frontend

def _page(name: str) -> FileResponse:
    """HTML-Seite ausliefern, ohne dass der Browser sie zwischenspeichert.

    Ohne Cache-Control darf der Browser die Seite nach eigenem Gutdünken aus
    dem Cache bedienen. Nach einem Update sieht die Lehrperson dann weiterhin
    die alte Oberfläche, obwohl der Server längst die neue Datei hat.
    "no-cache" erlaubt das Zwischenspeichern weiterhin, erzwingt aber jedes
    Mal eine Rückfrage beim Server – bei unveränderter Datei bleibt es beim
    schlanken 304.
    """
    return FileResponse(BASE / "static" / name,
                        headers={"Cache-Control": "no-cache"})


@app.get("/")
def index():
    return _page("index.html")


@teacher_pages.get("")
def teacher():
    return _page("teacher.html")


@app.get("/teacher/login")
def teacher_login_page(request: Request):
    if auth.is_teacher(request):
        return RedirectResponse("/teacher")
    return _page("teacher_login.html")


@teacher_pages.get("/lessons/new")
def lesson_editor():
    return _page("lesson_editor.html")


app.include_router(teacher_api)
app.include_router(teacher_pages)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
