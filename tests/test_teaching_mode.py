"""N-06: Teaching mode for lessons (order 5, decisions E3 to E9)."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import llm, main, store, tutor
from app.main import app

MATERIAL = ("Die Tierhalterhaftung (Art. 56 OR) macht Halterinnen und Halter für Schäden ihres Tieres haftbar. "
            "Die Werkeigentümerhaftung (Art. 58 OR) gilt für Schäden aus mangelhaftem Unterhalt eines Werks. ") * 4
ANIMAL = {"typ": "aufgabe", "titel": "Hund im Park", "konzept": "Tierhalterhaftung",
          "inhalt": "Ein Hund beisst einen Jogger.", "frage": "Wer haftet und warum?",
          "erwartete_antwort": "Die Halterin nach Art. 56 OR.", "schluesselbegriffe": ["Tierhalterhaftung"],
          "erwartete_elemente": [{"dimension": "Haftung", "erwartet": "Tierhalterhaftung"}]}
BUILDING = dict(ANIMAL, titel="Ziegel", konzept="Werkeigentümerhaftung", inhalt="Ein Ziegel fällt vom Dach.",
                erwartete_elemente=[{"dimension": "Haftung", "erwartet": "Werkeigentümerhaftung"}])
TOPIC_TEXT = "Verlange bei diesem Thema immer den Gesetzesartikel."
LESSON_TEXT = "Begründe jede Bewertung mit einem Satz aus dem Sachverhalt."


def _create_lesson(client: TestClient, title: str) -> str:
    return client.post("/api/teacher/lessons", json={"titel": title, "lernziele": ["Haftungsarten unterscheiden"],
                                                    "material": MATERIAL}).json()["id"]


def _start(title="Teaching Lektion", teaching=True):
    client = TestClient(app)
    lesson_id = _create_lesson(client, title)
    started = client.post("/api/session/start", json={"name": "LP Teaching", "lesson_id": lesson_id,
                                                      "neu_beginnen": True, "teaching": teaching}).json()
    return client, started, lesson_id


def _instruction(client, sid, text, scope, concept="", step_type="bewertung", original=""):
    return client.post(f"/api/session/{sid}/instruction", json={"text": text, "scope": scope, "concept": concept,
                                                               "step_type": step_type, "original": original})


@pytest.fixture
def prompts(monkeypatch):
    """Records system and user part of every call to the mock provider."""
    calls = []
    original = llm._PROVIDERS["mock"]

    def provider(system, user, json_mode=False):
        calls.append((system, user))
        return original(system, user, json_mode)
    monkeypatch.setitem(llm._PROVIDERS, "mock", provider)
    # The cross-check of a newly generated task would concern the concept the mock picks;
    # _steps therefore runs it directly with the test's task
    monkeypatch.setenv("ITS_MUSTERLOESUNG_PRUEFEN", "false")
    return calls


def _steps(lesson: dict, task: dict) -> None:
    """Cross-check, evaluation, question and a task right after a theory on the task's concept."""
    tutor.pruefe_musterloesung(lesson, task)
    tutor.evaluate_answer(lesson, tutor.new_profile(), task, "Die Halterin haftet nach dem Gesetz für das Tier.")
    tutor.answer_question(lesson, tutor.new_profile(), task, "Warum ist das so?", [])
    theory = {"typ": "theorie", "titel": "Theorie", "konzept": task["konzept"], "inhalt": "Erklärung."}
    profile = dict(tutor.new_profile(), last_type="theorie", erklaert=[task["konzept"]], covered=[task["konzept"]])
    tutor.generate_task(lesson, profile, [{"type": "task", "payload": theory}])


# ---------------------------------------------------------------- AK 1

def test_ak1_teacher_starts_teaching_mode():
    client, started, _ = _start()
    assert started["teaching"] is True
    session = store.get_session(started["session_id"])
    assert session["teaching"] == 1 and session["testlauf"] == 1
    assert client.post(f"/api/session/{started['session_id']}/fortsetzen").json()["teaching"] is True


def test_ak1_normal_test_run_without_teaching():
    client, started, _ = _start("Normaler Testlauf", teaching=False)
    assert "teaching" not in started
    assert store.get_session(started["session_id"])["teaching"] == 0
    assert "teaching" not in client.post(f"/api/session/{started['session_id']}/fortsetzen").json()
    assert _instruction(client, started["session_id"], LESSON_TEXT, "lesson").status_code == 403


def test_ak1_not_for_learners_and_not_for_archived_lessons(monkeypatch):
    client = TestClient(app)
    lesson_id = _create_lesson(client, "Archiv Teaching")
    client.delete(f"/api/teacher/lessons/{lesson_id}")
    response = client.post("/api/session/start", json={"name": "LP", "lesson_id": lesson_id, "teaching": True})
    assert response.status_code == 404
    monkeypatch.setenv("TEACHER_PASSWORD", "geheim123")
    learner = TestClient(app)
    learner.post("/api/learner/login", json={"name": "Mia Teaching"})
    response = learner.post("/api/session/start", json={"lesson_id": "haftungsrecht", "teaching": True})
    assert response.status_code == 403


def test_ak1_start_button_only_for_lessons_not_archived():
    html = Path("static/lessons.html").read_text(encoding="utf-8")
    actions = html[html.index("${l.archiviert ?"):html.index("</div></td>")]
    archived, not_archived = actions.split(":", 1)
    assert 'data-act="teaching">Im Teaching Mode testen' in not_archived
    assert "teaching" not in archived


def test_instruction_only_from_the_teacher_of_the_session(monkeypatch):
    _, started, _ = _start("Fremde Sequenz")
    monkeypatch.setenv("TEACHER_PASSWORD", "geheim123")
    learner = TestClient(app)
    learner.post("/api/learner/login", json={"name": "LP Teaching"})
    assert _instruction(learner, started["session_id"], LESSON_TEXT, "lesson").status_code == 403


# ---------------------------------------------------------------- AK 3

def test_ak3_topic_only_in_requests_on_the_same_concept(prompts):
    client, started, lesson_id = _start("Thema Teaching")
    response = _instruction(client, started["session_id"], TOPIC_TEXT, "topic", concept="Tierhalterhaftung",
                            step_type="theorie")
    assert response.status_code == 200
    lesson = main.load_lesson(lesson_id)
    prompts.clear()                      # the placement questions at the start belong to no concept
    _steps(lesson, ANIMAL)
    same = list(prompts)
    prompts.clear()
    _steps(lesson, BUILDING)
    other = list(prompts)
    assert len(same) >= 3 and all(TOPIC_TEXT in user for _, user in same)
    assert all("«Tierhalterhaftung»" in user for _, user in same)
    assert not any(TOPIC_TEXT in user or TOPIC_TEXT in system for system, user in other)
    assert not any(TOPIC_TEXT in system for system, _ in same)


def test_ak3_concepts_are_compared_by_meaning():
    lesson = {"tutor_instructions": [{"id": "a", "text": TOPIC_TEXT, "scope": "topic", "concept": "Tierhalterhaftung"}]}
    assert TOPIC_TEXT in tutor.topic_instructions(lesson, "Die Tierhalterhaftung")
    assert tutor.topic_instructions(lesson, "Werkeigentümerhaftung") == ""
    assert tutor.topic_instructions(lesson, None) == ""


def test_topic_without_concept_is_rejected():
    client, started, _ = _start("Ohne Konzept")
    assert _instruction(client, started["session_id"], TOPIC_TEXT, "topic", concept="").status_code == 422


# ---------------------------------------------------------------- AK 4

def test_ak4_lesson_suggestion_editable_and_in_the_system_prompt(prompts):
    client, started, lesson_id = _start("Lektion Teaching")
    sid = started["session_id"]
    suggestion = client.post(f"/api/session/{sid}/instruction/suggestion", json={
        "text": "Hier hättest du den Sachverhalt zitieren sollen.", "concept": "Tierhalterhaftung",
        "step_type": "bewertung", "step_text": "Richtig, die Halterin haftet."}).json()
    assert suggestion["fallback"] is False
    assert suggestion["suggestion"].startswith("In dieser Lektion gilt allgemein")
    assert any("AUFGABE: GENERALIZE_INSTRUCTION" in user for _, user in prompts)
    # The teacher changes the suggestion and confirms it
    saved = _instruction(client, sid, LESSON_TEXT, "lesson", concept="Tierhalterhaftung",
                         original="Hier hättest du den Sachverhalt zitieren sollen.").json()
    assert saved["instruction"]["text"] == LESSON_TEXT
    assert saved["instruction"]["original"].startswith("Hier hättest")
    prompts.clear()
    lesson = main.load_lesson(lesson_id)
    _steps(lesson, ANIMAL)
    _steps(lesson, BUILDING)
    tutor.generate_theory(lesson, tutor.new_profile(), [])
    systems = {system for system, _ in prompts}
    assert len(prompts) >= 7 and len(systems) == 1
    assert LESSON_TEXT in systems.pop()
    assert not any(LESSON_TEXT in user for _, user in prompts)


def test_ak8_failed_generalization_keeps_the_text(monkeypatch):
    monkeypatch.setenv("ITS_MOCK_FAIL", "GENERALIZE_INSTRUCTION")
    client, started, lesson_id = _start("Fallback Teaching")
    text = "Erkläre mit Beispielen aus dem Detailhandel."
    suggestion = client.post(f"/api/session/{started['session_id']}/instruction/suggestion", json={"text": text}).json()
    assert suggestion == {"suggestion": text, "fallback": True, "reason": suggestion["reason"]}
    response = _instruction(client, started["session_id"], suggestion["suggestion"], "lesson", original=text)
    assert response.status_code == 200
    assert main.load_lesson(lesson_id)["tutor_instructions"][0]["text"] == text


# ---------------------------------------------------------------- AK 5 and AK 6

def test_ak5_ak6_version_editor_delete_and_learning_history(prompts):
    client, started, lesson_id = _start("Version Teaching")
    sid = started["session_id"]
    version_before = client.get(f"/api/teacher/lessons/{lesson_id}").json()["version"]
    first = _instruction(client, sid, LESSON_TEXT, "lesson").json()
    second = _instruction(client, sid, TOPIC_TEXT, "topic", concept="Tierhalterhaftung").json()
    detail = client.get(f"/api/teacher/lessons/{lesson_id}").json()
    assert first["version"] == version_before + 1 and second["version"] == version_before + 2 == detail["version"]
    assert [i["id"] for i in detail["tutor_instructions"]] == [first["instruction"]["id"], second["instruction"]["id"]]
    assert detail["tutor_hinweise"] == ""
    # AK 6: every instruction appears in the learning history of the teaching session
    events = [e for e in client.get(f"/api/teacher/sessions/{sid}").json()["events"] if e["type"] == "tutor_instruction"]
    assert [e["payload"]["text"] for e in events] == [LESSON_TEXT, TOPIC_TEXT]
    assert events[1]["payload"]["concept"] == "Tierhalterhaftung"
    # AK 5: deleting in the editor, afterwards in no prompt any more
    deleted = client.delete(f"/api/teacher/lessons/{lesson_id}/instructions/{first['instruction']['id']}").json()
    assert deleted["version"] == version_before + 3 and len(deleted["tutor_instructions"]) == 1
    client.delete(f"/api/teacher/lessons/{lesson_id}/instructions/{second['instruction']['id']}")
    response = client.delete(f"/api/teacher/lessons/{lesson_id}/instructions/{second['instruction']['id']}")
    assert response.status_code == 404
    prompts.clear()
    _steps(main.load_lesson(lesson_id), ANIMAL)
    assert prompts and not any(LESSON_TEXT in system + user or TOPIC_TEXT in system + user
                               for system, user in prompts)


def test_ak5_instructions_survive_editing_in_the_editor():
    client, started, lesson_id = _start("Editor Teaching")
    _instruction(client, started["session_id"], LESSON_TEXT, "lesson")
    client.put(f"/api/teacher/lessons/{lesson_id}", json={"titel": "Editor Teaching", "lernziele": ["Ziel"],
                                                          "material": MATERIAL})
    instructions = client.get(f"/api/teacher/lessons/{lesson_id}").json()["tutor_instructions"]
    assert [i["text"] for i in instructions] == [LESSON_TEXT]


def test_archived_lesson_accepts_no_instructions():
    client, started, lesson_id = _start("Archiv nach Start")
    client.delete(f"/api/teacher/lessons/{lesson_id}")
    assert _instruction(client, started["session_id"], LESSON_TEXT, "lesson").status_code == 409


# ---------------------------------------------------------------- AK 7

def test_ak7_prompts_unchanged_without_instructions(prompts):
    lesson = json.loads(Path("app/lessons/haftungsrecht.json").read_text(encoding="utf-8"))
    assert "tutor_instructions" not in lesson
    _steps(lesson, ANIMAL)
    without = list(prompts)
    prompts.clear()
    _steps(dict(lesson, tutor_instructions=[]), ANIMAL)
    empty = list(prompts)
    prompts.clear()
    other_topic_only = [{"id": "x", "text": TOPIC_TEXT, "scope": "topic", "concept": "Werkeigentümerhaftung"}]
    _steps(dict(lesson, tutor_instructions=other_topic_only), ANIMAL)
    assert without == empty == prompts
    assert tutor.topic_instructions(lesson, "Tierhalterhaftung") == ""
