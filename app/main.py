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

load_dotenv()

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import llm, store, tutor

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("its")

BASE = Path(__file__).resolve().parent.parent
LESSONS_DIR = Path(os.getenv("ITS_LESSONS_DIR") or BASE / "app" / "lessons")
LESSONS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="ITS MVP")
store.init_db()


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
    name: str
    lesson_id: str | None = None


class AssessRequest(BaseModel):
    answers: list[str]


class AnswerRequest(BaseModel):
    answer: str


class ChatRequest(BaseModel):
    message: str


class LessonCreateRequest(BaseModel):
    titel: str
    lernziele: list[str]
    material: str
    tutor_hinweise: str = ""


class SuggestGoalsRequest(BaseModel):
    material: str


# ---------------------------------------------------------------- Lektionen

@app.get("/api/lessons")
def lessons_list():
    """Verfügbare Lektionen – für die Auswahl beim Start."""
    out = []
    for p in sorted(LESSONS_DIR.glob("*.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        out.append({"id": p.stem, "titel": data.get("titel", p.stem)})
    return out


@app.post("/api/teacher/lessons")
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


@app.post("/api/teacher/lessons/extract")
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


@app.post("/api/teacher/lessons/suggest-goals")
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
def start_session(req: StartRequest):
    lesson_id = req.lesson_id or default_lesson_id()
    lesson = load_lesson(lesson_id)
    profile = tutor.new_profile()
    sid = store.create_session(req.name.strip() or "Anonym", lesson_id, profile)
    questions = tutor.generate_assessment(lesson)
    store.log_event(sid, "session_started", {"name": req.name, "lesson": lesson["titel"]})
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
def assess(sid: str, req: AssessRequest):
    s = _session(sid)
    lesson = load_lesson(s["lesson_id"])
    profile = s["profile"]
    questions = profile.get("assessment_questions", [])
    result = tutor.evaluate_assessment(lesson, questions, req.answers)
    profile["level"] = result["level"]
    store.log_event(sid, "assessment_evaluated", {
        "answers": req.answers, "level": result["level"],
        "begruendung": result.get("begruendung", ""),
    })
    store.update_session(sid, phase="learning", profile=profile)
    return {
        "level": result["level"],
        "level_label": tutor.LEVEL_LABELS[result["level"]],
        "begruendung": result.get("begruendung", ""),
    }


@app.post("/api/session/{sid}/next")
def next_step(sid: str, adaptation: str | None = None):
    s = _session(sid)
    lesson = load_lesson(s["lesson_id"])
    profile = s["profile"]
    if profile["step"] >= tutor.total_steps():
        return _finish(sid, lesson, profile)
    history = store.get_events(sid)
    step_type = tutor.decide_step_type(profile, adaptation)
    if step_type == "theorie":
        task = tutor.generate_theory(lesson, profile, history, adaptation)
        profile["theory_steps"] = profile.get("theory_steps", 0) + 1
    else:
        task = tutor.generate_task(lesson, profile, history, adaptation)
    profile["current_task"] = task
    profile["last_type"] = step_type
    concept = task.get("konzept")
    if concept and concept not in profile["covered"]:
        profile["covered"].append(concept)
    store.log_event(sid, "task", task)
    store.update_session(sid, profile=profile)
    return {
        "done": False,
        "task": task,
        "progress": _progress(profile),
    }


@app.post("/api/session/{sid}/answer")
def answer(sid: str, req: AnswerRequest):
    s = _session(sid)
    lesson = load_lesson(s["lesson_id"])
    profile = s["profile"]
    task = profile.get("current_task")
    if not task:
        raise HTTPException(400, "Keine aktive Aufgabe – rufe zuerst /next auf")
    if task.get("typ") == "theorie":
        raise HTTPException(400, "Der aktuelle Schritt ist Theorie – es gibt "
                                 "nichts zu bewerten. Weiter mit /next")
    store.log_event(sid, "answer_submitted", {"answer": req.answer})
    result = tutor.evaluate_answer(lesson, profile, task, req.answer)
    action, reason = tutor.adapt(profile, result["korrekt"])
    store.log_event(sid, "answer_evaluated", {
        "korrekt": result["korrekt"], "feedback": result.get("feedback", ""),
        "hinweis": result.get("hinweis", ""), "adaption": action,
        "adaption_begruendung": reason, "level": profile["level"],
    })
    store.update_session(sid, profile=profile)
    finished = profile["step"] >= tutor.total_steps() and action != "retry"
    return {
        "korrekt": result["korrekt"],
        "feedback": result.get("feedback", ""),
        "hinweis": result.get("hinweis", ""),
        "adaption": action,           # next | advance | retry | simplify
        "adaption_begruendung": reason,
        "finished": finished,
        "progress": _progress(profile),
    }


@app.post("/api/session/{sid}/chat")
def chat_with_tutor(sid: str, req: ChatRequest):
    """Verständnisfrage des Lernenden im Dialog – jederzeit möglich."""
    s = _session(sid)
    lesson = load_lesson(s["lesson_id"])
    profile = s["profile"]
    message = req.message.strip()
    if not message:
        raise HTTPException(400, "Leere Nachricht")
    store.log_event(sid, "chat_question", {"frage": message})
    history = store.get_events(sid)
    result = tutor.answer_question(lesson, profile, profile.get("current_task"),
                                   message, history)
    antwort = result.get("antwort", "")
    store.log_event(sid, "chat_reply", {"antwort": antwort})
    return {"antwort": antwort}


@app.get("/api/session/{sid}/state")
def state(sid: str):
    """Aktueller Zustand einer Session – Basis für Pausieren/Fortsetzen."""
    s = _session(sid)
    lesson = load_lesson(s["lesson_id"])
    return {
        "session_id": sid,
        "name": s["name"],
        "phase": s["phase"],
        "lesson": {"titel": lesson["titel"], "lernziele": lesson["lernziele"]},
        "progress": _progress(s["profile"]),
        "current_task": s["profile"].get("current_task"),
    }


def _finish(sid: str, lesson: dict, profile: dict):
    # Idempotent: Wurde die Session bereits abgeschlossen, die gespeicherte
    # Zusammenfassung wiederverwenden statt neu zu generieren und doppelt zu loggen.
    for ev in reversed(store.get_events(sid)):
        if ev["type"] == "finished":
            return {"done": True, "summary": ev["payload"], "progress": _progress(profile)}
    history = store.get_events(sid)
    summary = tutor.generate_summary(lesson, profile, history)
    store.log_event(sid, "finished", summary)
    store.update_session(sid, phase="finished", profile=profile)
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
    }


def _session(sid: str) -> dict:
    s = store.get_session(sid)
    if s is None:
        raise HTTPException(404, "Session nicht gefunden")
    return s


# ---------------------------------------------------------------- Lehrperson

@app.get("/api/teacher/sessions")
def teacher_sessions():
    out = []
    for s in store.list_sessions():
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
            "covered": p.get("covered", []),
            "created_at": s["created_at"],
            "updated_at": s["updated_at"],
        })
    return out


@app.get("/api/teacher/sessions/{sid}")
def teacher_session_detail(sid: str):
    s = _session(sid)
    return {
        "session": {"id": s["id"], "name": s["name"], "phase": s["phase"],
                    "profile": s["profile"]},
        "events": store.get_events(sid),
    }


@app.get("/api/info")
def info():
    return {"provider": llm.provider_name(), "lessons": [p.stem for p in sorted(LESSONS_DIR.glob('*.json'))]}


# ---------------------------------------------------------------- Frontend

@app.get("/")
def index():
    return FileResponse(BASE / "static" / "index.html")


@app.get("/teacher")
def teacher():
    return FileResponse(BASE / "static" / "teacher.html")


@app.get("/teacher/lessons/new")
def lesson_editor():
    return FileResponse(BASE / "static" / "lesson_editor.html")


app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
