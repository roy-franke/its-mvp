# ITS-MVP – Intelligentes Tutorielles System

Erster lauffähiger MVP gemäss Projektbeschreibung (DLH-Innovationsfonds, EB Zürich).
Umfang: Lernenden-Flow (Einstufung → adaptiver Lernpfad → KI-Feedback → Abschluss)
plus Lehrpersonen-Monitoring light. Der komplette Lernverlauf wird protokolliert.

## Was der MVP kann

- **Onboarding**: Lernende starten mit Namenseingabe eine Session.
- **Wissenseinstufung**: 3 KI-generierte Einstiegsfragen bestimmen das Startniveau (basic / intermediate / advanced).
- **Lernendenprofil**: Niveau, Fortschritt, Trefferquote, behandelte Konzepte; wird laufend aktualisiert.
- **Adaptiver Lernpfad**: Die KI generiert Lernschritte aus dem Lektionsmaterial. Richtig → weiter, 2× richtig in Serie → Niveau rauf. Falsch → Hinweis und zweiter Versuch, nochmals falsch → Vereinfachung und Niveau runter. Jede Adaption wird begründet (Transparenzprinzip aus dem Systemkonzept).
- **KI-Feedback mit dreistufiger Bewertung**: Antworten werden als korrekt, teilweise korrekt oder falsch beurteilt (Kategorien und Feedback-Regeln nach dem Vorbild des LLMTutor-Projekts von Swiss Learning Analytics). Bei «teilweise» gibt es einen Hinweis zur Nachbesserung, ohne dass die Antwort als Fehler zählt; bleibt die Nachbesserung unvollständig, wird sie akzeptiert und die Ergänzungen kommen aus dem Feedback.
- **Sicherheitsfrage (metakognitiv)**: Vor der ersten Bewertung jeder Aufgabe geben Lernende an, wie sicher sie sich sind (1-10). Die Angaben werden protokolliert und der Lehrperson als Durchschnitt angezeigt – ein Mass für die Selbsteinschätzung und deren Kalibrierung.
- **Theorie-Schritte**: Der Lernpfad besteht aus Input- und Anwendungs-Schritten. Der Tutor erklärt neue Konzepte zuerst (mit Beispiel), bevor Aufgaben dazu kommen – wie viel Theorie, entscheidet er adaptiv: Auf Niveau basic gibt es Input vor jedem neuen Konzept, auf intermediate zum Einstieg, auf advanced nur nach Fehlern. Nach zwei Fehlversuchen wird das Konzept neu und einfacher erklärt. Theorie-Schritte werden nicht bewertet und zählen nicht in die Quote. Lernende können zudem jederzeit selbst Theorie anfordern («Theorie dazu», «Genauer erklären»).
- **Mathematische Formeln**: Der Tutor schreibt Formeln in LaTeX, das UI rendert sie mit KaTeX sauber als Brüche, Exponenten, Wurzeln usw. – im Lern-Chat, in der Einstufung und im Lernverlauf der Lehrperson. Hinweis: KaTeX wird von einem CDN geladen; für den Betrieb ganz ohne Internet müsste es lokal ins Projekt gelegt werden.
- **Chat-Dialog**: Das Lernen läuft als Dialog. Der Tutor liefert Input und Aufgaben als Chat-Nachrichten, und Lernende können ihm jederzeit Verständnisfragen stellen («Frage stellen»), ohne dass dies bewertet wird. Der Tutor antwortet materialgebunden und verrät die Lösung der aktuellen Aufgabe nicht, sondern gibt Denkanstösse. Auch diese Fragen erscheinen im Lernverlauf der Lehrperson.
- **Abschluss**: Zusammenfassung mit Lernzielabgleich und Empfehlung.
- **Pausieren und Fortsetzen**: Browser schliessen genügt – beim nächsten Besuch bietet die Startseite an, die Lernsequenz an der gleichen Stelle fortzusetzen (Session-ID wird lokal im Browser gemerkt, Zustand liegt in der DB).
- **Lehrpersonen-Sicht** (`/teacher`): Übersicht aller Sessions mit Fortschritt, Niveau und Quote; Klick auf eine Zeile zeigt den vollständigen Lernverlauf (Event-Log).
- **Lektionen erstellen** (`/teacher/lessons/new`): Lehrpersonen erstellen Lektionen direkt im Browser. Material als Text einfügen oder als Datei hochladen (PDF, Word, Text/Markdown), Titel und Lernziele von der KI vorschlagen lassen, optional Hinweise ans Tutorverhalten («Arbeite mit Alltagsbeispielen», «Sei streng bei Fachbegriffen»). Nach dem Speichern erscheint die Lektion in der Auswahl auf der Lernenden-Startseite.
- **Zugangsschutz für den Klassentest**: Die Lehrpersonen-Sicht ist per Passwort geschützt (`TEACHER_PASSWORD` in der `.env`, Login unter `/teacher/login`, Abmelden möglich). Lernende brauchen einen Zugangscode (`CLASS_CODE`) und werden angehalten, ein Pseudonym statt des richtigen Namens zu verwenden. Beides lässt sich für die lokale Entwicklung deaktivieren, indem die Variablen leer bleiben.
- **Deployment-Paket**: Dockerfile und docker-compose mit Caddy-Reverse-Proxy – HTTPS inklusive automatischem Let's-Encrypt-Zertifikat. Schritt-für-Schritt-Anleitung für einen VPS in `docs/DEPLOYMENT.md`; Alternative ohne eigenen Server: lokaler Betrieb mit Cloudflare Tunnel, siehe `docs/DEPLOYMENT-CLOUDFLARE.md`.
- **LLM-Abstraktion**: Provider per `.env` umschaltbar – Cloud (Anthropic, OpenAI-kompatibel) oder lokal (Ollama). `mock` läuft ganz ohne LLM für Demos und Tests.

## Schnellstart

```bash
cd its-mvp
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # Provider und Keys eintragen
uvicorn app.main:app --reload
```

Dann im Browser:
- Lernende: http://localhost:8000/
- Lehrperson: http://localhost:8000/teacher

Auf Windows genügen `setup.bat` (einmalig) und `start.bat`. Letzteres startet
den Server auf Port **8010**, damit Port 8000 für andere lokale Anwendungen
frei bleibt (siehe `docs/DEPLOYMENT-CLOUDFLARE.md`).

**Wichtig:** Ohne Anpassung der `.env` läuft der Mock-Provider – ohne KI. Er
bewertet nur heuristisch (sehr kurze Antworten gelten als falsch) und liefert
feste Beispieltexte. Echte fachliche Bewertung, echte Aufgaben und echtes
Tutoring gibt es erst mit einem konfigurierten LLM:

```ini
# Cloud (schnellster Weg)
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...

# oder lokal auf RIB-AI-01 (On-Premise, datenschutzkonform)
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
```

## Architektur

```
Browser (static/index.html, teacher.html)
   │  REST/JSON
FastAPI (app/main.py)
   ├─ tutor.py   ITS-Kernlogik: Einstufung, Profil, Adaption, Prompts
   ├─ llm.py     Provider-Abstraktion: anthropic | openai | ollama | mock
   ├─ store.py   SQLite: Sessions + vollständiges Event-Log
   └─ lessons/   Lektionen als JSON (materialgebunden, austauschbar)
```

Designentscheide, angelehnt ans Systemkonzept vom April 2026:

- **Lektion als zentrale Einheit**: Eine Lektion ist eine JSON-Datei mit Titel, Lernzielen, Material und Fallback-Einstufungsfragen. Neue Lektion = neue Datei in `app/lessons/`, kein Codeeingriff.
- **Materialgebunden**: Der Systemprompt verpflichtet den Tutor auf das Lektionsmaterial und macht Unsicherheit sichtbar (Verlässlichkeit vor Eloquenz).
- **Trennung Inhalt/Tutorlogik**: Die Adaptionslogik (tutor.adapt) ist deterministischer Code, kein LLM-Entscheid – nachvollziehbar und testbar. Das LLM generiert Inhalte, Bewertungen und Feedback.
- **Lernpfade rekonstruierbar**: Jedes Ereignis (Fragen, Antworten, Bewertungen, Adaptionen mit Begründung) landet im Event-Log und ist in der Lehrpersonen-Sicht einsehbar.
- **Robustheit**: Jeder LLM-Aufruf hat einen Fallback; bei KI-Ausfall bleibt das System bedienbar.

## API-Überblick

| Endpoint | Zweck |
|---|---|
| `POST /api/session/start` | Session anlegen, Einstufungsfragen erhalten |
| `POST /api/session/{id}/assess` | Einstufung bewerten, Startniveau setzen |
| `POST /api/session/{id}/next` | Nächste Aufgabe (optional `?adaptation=simplify\|advance`) |
| `POST /api/session/{id}/answer` | Antwort bewerten, Feedback + Adaption |
| `POST /api/session/{id}/chat` | Verständnisfrage an den Tutor (unbewertet) |
| `GET /api/lessons` | Verfügbare Lektionen (für die Auswahl beim Start) |
| `POST /api/teacher/lessons` | Neue Lektion anlegen |
| `POST /api/teacher/lessons/extract` | Text aus PDF/Word/Text-Datei extrahieren |
| `POST /api/teacher/lessons/suggest-goals` | KI-Vorschlag für Titel und Lernziele |
| `GET /api/session/{id}/state` | Zustand (Basis für Pausieren/Fortsetzen) |
| `GET /api/teacher/sessions` | Monitoring-Übersicht |
| `GET /api/teacher/sessions/{id}` | Vollständiger Lernverlauf |
| `GET /api/teacher/timings` | Antwortzeiten der letzten LLM-Aufrufe |
| `GET /api/info` | Aktiver Provider, verfügbare Lektionen |

## Konfiguration (.env)

| Variable | Bedeutung |
|---|---|
| `LLM_PROVIDER` | `anthropic`, `openai`, `ollama` oder `mock` |
| `ITS_TOTAL_STEPS` | Anzahl Lernschritte pro Durchlauf (Standard 8) |
| `ITS_DB_PATH` | Optionaler Pfad zur SQLite-DB |
| `OLLAMA_NUM_CTX` | Kontextfenster für Ollama (Standard 16384) |
| `OLLAMA_KEEP_ALIVE` | Wie lange das Modell geladen bleibt (Standard 30m) |
| `OLLAMA_NUM_PREDICT` | Obergrenze für die Antwortlänge in Token (Standard 1024) |
| `OLLAMA_THINK` | Denkmodus von Reasoning-Modellen (`false` = schnell, Standard) |
| `LLM_TIMEOUT` | Zeitlimit pro LLM-Aufruf in Sekunden (Standard 300) |
| `ITS_LESSONS_DIR` | Optionaler Pfad zum Lektionenordner |
| `TEACHER_PASSWORD` | Passwort für `/teacher`; leer = kein Login (nur lokal) |
| `CLASS_CODE` | Zugangscode für Lernende; leer = kein Code |
| `ITS_DOMAIN` | Domain für den HTTPS-Betrieb mit Docker/Caddy |

## Tests

```bash
pip install pytest
python3 -m pytest tests/ -q
```

`tests/test_tutor.py` deckt die deterministische Adaptionslogik ab (Level rauf/runter,
Retry, Serien, Randfälle), `tests/test_api.py` testet den kompletten Lernenden-Flow
End-to-End über die API mit Mock-Provider – ohne LLM, ohne laufenden Server.

## Bewusste Grenzen (MVP)

Kein Benutzerverzeichnis und keine Rollen (nur ein gemeinsames
Lehrpersonen-Passwort und ein Klassencode), kein RAG über grosse Dokumente
(das Material geht direkt in den Kontext, sehr lange Dokumente daher kürzen).

## Sinnvolle nächste Schritte

1. Prompts mit realen Lernenden-Antworten tunen (Bewertungsstrenge, Erklärtiefe).
2. Eigene Lektionen über den Editor erstellen und mit der Klasse testen.
3. Tutoring-Modi (erklärend, sokratisch, prüfend, coaching) aus dem Systemkonzept.
4. RAG-Anbindung an P2 für umfangreiches Material.
