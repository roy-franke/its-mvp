# ITS-MVP – Intelligentes Tutorielles System

Erster lauffähiger MVP gemäss Projektbeschreibung (DLH-Innovationsfonds, EB Zürich).
Umfang: Lernenden-Flow (Einstufung → adaptiver Lernpfad → KI-Feedback → Abschluss)
plus Lehrpersonen-Monitoring light. Der komplette Lernverlauf wird protokolliert.

## Was der MVP kann

- **Onboarding**: Lernende melden sich mit Pseudonym (plus Zugangscode, optional einer vierstelligen PIN) an und sehen ihre eigenen Lernsequenzen.
- **Wissenseinstufung**: 3 KI-generierte Einstiegsfragen bestimmen das Startniveau (basic / intermediate / advanced).
- **Lernendenprofil**: Niveau, Fortschritt, Trefferquote, behandelte Konzepte; wird laufend aktualisiert.
- **Adaptiver Lernpfad**: Die KI generiert Lernschritte aus dem Lektionsmaterial. Richtig → weiter, 2× richtig in Serie → Niveau rauf. Falsch → Hinweis und zweiter Versuch, nochmals falsch → Vereinfachung und Niveau runter. Jede Adaption wird begründet (Transparenzprinzip aus dem Systemkonzept).
- **KI-Feedback mit dreistufiger Bewertung**: Antworten werden als korrekt, teilweise korrekt oder falsch beurteilt (Kategorien und Feedback-Regeln nach dem Vorbild des LLMTutor-Projekts von Swiss Learning Analytics). Bei «teilweise» gibt es einen Hinweis zur Nachbesserung, ohne dass die Antwort als Fehler zählt; bleibt die Nachbesserung unvollständig, wird sie akzeptiert und die Ergänzungen kommen aus dem Feedback.
- **Sicherheitsfrage (metakognitiv)**: Vor der ersten Bewertung jeder Aufgabe geben Lernende an, wie sicher sie sich sind (1-10). Die Angaben werden protokolliert und der Lehrperson als Durchschnitt angezeigt – ein Mass für die Selbsteinschätzung und deren Kalibrierung.
- **Fragequalität (Eigenleistung statt Abschreiben)**: Jede bewertete Aufgabe verlangt eine eigene Denkleistung (anwenden auf einen neuen Fall, begründen, vergleichen, vorhersagen, Fehler finden, mit eigenen Worten an einem neuen Beispiel erklären), passend zum Niveau. Der Tutor liefert zu jeder Aufgabe intern eine Musterlösung und Schlüsselbegriffe, die Lernende nie sehen. Nach der Generierung prüft der Code deterministisch, ob ein Lösungsbegriff oder sein Wortstamm in der Frage steht, ob das Beispiel der letzten Theorie wiederverwendet wird oder ob die Antwort direkt aus dem eben gezeigten Text abschreibbar ist; bei einem Treffer wird einmal neu generiert und der Verstoss protokolliert. Die Regeln stehen gebündelt im Regelkatalog `app/didaktik.py`.
- **Einsatzart pro Lektion**: «Einführung» (Standard) setzt kein Vorwissen voraus. Bewertete Aufgaben beziehen sich nur auf Konzepte, die in der Sequenz schon erklärt wurden; verlangt eine Aufgabe trotzdem ein neues Konzept, kommt zuerst ein Theorieschritt dazu, auch auf höherem Niveau. Die Einstufung fragt dann nach Alltagswissen statt nach Fachbegriffen. «Vertiefung» darf Konzepte aus dem Material voraussetzen; eine falsche Antwort zu einem noch nicht erklärten Konzept führt zu einer Erklärung und nicht zu einer Niveausenkung.
- **Theorie-Schritte**: Der Lernpfad besteht aus Input- und Anwendungs-Schritten. Der Tutor erklärt neue Konzepte zuerst (mit Beispiel), bevor Aufgaben dazu kommen – wie viel Theorie, entscheidet er adaptiv: Auf Niveau basic gibt es Input vor jedem neuen Konzept, auf intermediate zum Einstieg, auf advanced nur nach Fehlern. Nach zwei Fehlversuchen wird das Konzept neu und einfacher erklärt. Theorie-Schritte werden nicht bewertet und zählen nicht in die Quote. Lernende können zudem jederzeit selbst Theorie anfordern («Theorie dazu», «Genauer erklären»).
- **Mathematische Formeln**: Der Tutor schreibt Formeln in LaTeX, das UI rendert sie mit KaTeX sauber als Brüche, Exponenten, Wurzeln usw. – im Lern-Chat, in der Einstufung und im Lernverlauf der Lehrperson. Hinweis: KaTeX wird von einem CDN geladen; für den Betrieb ganz ohne Internet müsste es lokal ins Projekt gelegt werden.
- **Chat-Dialog**: Das Lernen läuft als Dialog. Der Tutor liefert Input und Aufgaben als Chat-Nachrichten, und Lernende können ihm jederzeit Verständnisfragen stellen («Frage stellen»), ohne dass dies bewertet wird. Der Tutor antwortet materialgebunden und verrät die Lösung der aktuellen Aufgabe nicht, sondern gibt Denkanstösse. Auch diese Fragen erscheinen im Lernverlauf der Lehrperson. Solange der Tutor arbeitet, zeigt der Chat eine Warteanzeige («Dein Tutor denkt nach …», nach 20 Sekunden mit beruhigendem Hinweis) und alle Aktionsbuttons sind deaktiviert; das Eingabefeld bleibt beschreibbar, nichts wird doppelt abgeschickt.
- **Abschluss**: Zusammenfassung mit Lernzielabgleich und Empfehlung.
- **Lernsequenzen pro Person**: Eine Lernsequenz gehört einer Person (Benutzername, Gross-/Kleinschreibung egal) und einer Lektion. Nach der Anmeldung zeigt die Startseite die eigenen Sequenzen mit Lektion, Fortschritt, Niveau, Status und letzter Aktivität, jeweils mit «Fortsetzen» und «Neu beginnen». Fortsetzen klappt auch auf einem anderen Gerät an genau derselben Stelle. Pro Person und Lektion gibt es höchstens eine offene Sequenz; «Neu beginnen» archiviert die bisherige nach einer Bestätigung. Status: aktiv, pausiert, abgeschlossen, abgebrochen, archiviert; jeder Wechsel landet im Event-Log. Wer beim ersten Start eine PIN setzt, schützt den Namen vor fremdem Weiterlernen. In der Lernansicht gibt es oben «Pausieren und später weiterfahren» und «Lektion abbrechen» (mit Bestätigung); eine abgebrochene Sequenz bleibt für die Lehrperson mit Zeitpunkt sichtbar.
- **Lehrpersonen-Sicht** (`/teacher`): Übersicht aller Sessions mit Fortschritt, Niveau und Quote; Klick auf eine Zeile zeigt den vollständigen Lernverlauf (Event-Log).
- **Lektionen verwalten** (`/teacher/lessons`): Liste aller Lektionen mit Anzahl Lernziele und Quellen, letzter Änderung und Anzahl Sequenzen. «Ansehen» zeigt Lernziele, Quellen, Material, Hinweise und Tutor-Einstellungen. «Bearbeiten» öffnet den Editor mit allen Werten inklusive Quellenliste; beim Speichern werden Version und Änderungsdatum nachgeführt, laufende Sequenzen arbeiten ab dem nächsten Schritt mit dem neuen Material. «Löschen» archiviert die Lektion: Sie verschwindet aus der Auswahl, Lernverläufe bleiben lesbar.
- **Tutor-Einstellungen pro Lektion** (Editor, Abschnitt 4; im JSON unter `einstellungen`, fehlende Werte = Standard): Einsatzart (Einführung/Vertiefung), Niveauanpassung (automatisch/nur nach unten/fix), Bewertungsstrenge (nachsichtig/ausgewogen/streng), Wissensquellen (Material, optional gekennzeichnetes Allgemeinwissen).
- **Lektionen erstellen** (`/teacher/lessons/new`): Lehrpersonen erstellen Lektionen direkt im Browser. Material als Text einfügen oder als Datei hochladen (PDF, Word, Text/Markdown), Titel und Lernziele von der KI vorschlagen lassen, optional Hinweise ans Tutorverhalten («Arbeite mit Alltagsbeispielen», «Sei streng bei Fachbegriffen»). Nach dem Speichern erscheint die Lektion in der Auswahl auf der Lernenden-Startseite.
- **Rollen und Zugangsschutz**: Es gibt die Rollen «lernend» und «lehrperson», durchgesetzt auf dem Server. Alle Seiten unter `/teacher` und alle Endpunkte unter `/api/teacher` hängen an einer zentralen Rollenprüfung (`app/auth.py`); ohne Login gibt es 401 bzw. eine Weiterleitung auf `/teacher/login`. Lernende sehen keine Elemente für Lehrpersonen. Lehrpersonen melden sich mit `TEACHER_PASSWORD` an, Lernende mit Pseudonym plus Zugangscode (`CLASS_CODE`). Beides lässt sich für die lokale Entwicklung deaktivieren, indem die Variablen leer bleiben. Optional übernimmt das ITS Name und Rolle aus Headern eines Proxys wie Cloudflare Access (`ITS_TRUST_PROXY_HEADERS`, siehe `docs/DEPLOYMENT-CLOUDFLARE.md`). Lernsequenzen, die eine Lehrperson startet, sind Testläufe und erscheinen im Monitoring nur mit dem Filter «Testläufe anzeigen».
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
- **Robustheit**: Scheitert ein LLM-Aufruf oder ist die Antwort kein lesbares JSON, wird er einmal automatisch wiederholt. Erst danach greift ein Fallback, der für sich allein brauchbar ist: Ein Theorie-Fallback zeigt den passenden Abschnitt des Lektionsmaterials direkt an; lässt sich keiner bestimmen, meldet der Tutor offen ein technisches Problem und bietet «Nochmals versuchen» an. Jeder Fallback erzeugt ein Event `fallback_used` mit Grund und erscheint in der Messübersicht.

## API-Überblick

| Endpoint | Zweck |
|---|---|
| `POST /api/session/start` | Lernsequenz anlegen, Einstufungsfragen erhalten; 409, wenn zur Lektion schon eine offene Sequenz existiert (`neu_beginnen: true` archiviert sie) |
| `POST /api/session/{id}/assess` | Einstufung bewerten, Startniveau setzen |
| `POST /api/session/{id}/next` | Nächste Aufgabe (optional `?adaptation=simplify\|advance`); mit `?prefetch=true` nur vorbereiten, ohne Profil und Verlauf zu ändern |
| `POST /api/session/{id}/answer` | Antwort bewerten, Feedback + Adaption |
| `POST /api/session/{id}/chat` | Verständnisfrage an den Tutor (unbewertet) |
| `GET /api/lessons` | Verfügbare Lektionen (für die Auswahl beim Start) |
| `POST /api/teacher/lessons` | Neue Lektion anlegen |
| `GET /api/teacher/lessons` | Lektionen für die Verwaltung (`?archivierte=true` inkl. gelöschter) |
| `GET /api/teacher/lessons/{id}` | Lektion vollständig mit gültigen Einstellungen |
| `PUT /api/teacher/lessons/{id}` | Lektion ändern (Version und Änderungsdatum werden nachgeführt) |
| `DELETE /api/teacher/lessons/{id}` | Lektion löschen, d.h. archivieren |
| `POST /api/teacher/lessons/extract` | Text aus PDF/Word/Text-Datei extrahieren |
| `POST /api/teacher/lessons/suggest-goals` | KI-Vorschlag für Titel und Lernziele |
| `GET /api/session/{id}/state` | Zustand inkl. `wartet_auf` (Basis für das Fortsetzen) |
| `POST /api/session/{id}/fortsetzen` | Sequenz fortsetzen, liefert den Stand zum Anzeigen |
| `POST /api/session/{id}/pausieren` | «Pausieren und später weiterfahren» |
| `POST /api/session/{id}/abbrechen` | «Lektion abbrechen» (danach nur noch neu beginnen) |
| `GET /api/me/sequenzen` | Eigene, nicht archivierte Lernsequenzen |
| `GET /api/me` | Angemeldete Identität und Rolle (für die rollenabhängige Oberfläche) |
| `POST /api/learner/login` | Anmeldung Lernende mit Name, Zugangscode und optionaler PIN |
| `POST /api/learner/logout` | Abmelden bzw. Person wechseln |
| `POST /api/teacher/login` | Anmeldung Lehrperson mit Passwort |
| `GET /api/teacher/sessions` | Monitoring-Übersicht (`?testlaeufe=true` zeigt Testläufe) |
| `GET /api/teacher/sessions/{id}` | Vollständiger Lernverlauf |
| `GET /api/teacher/timings` | Antwortzeiten, Fehler und Fallbacks der letzten LLM-Aufrufe |
| `GET /api/llm-test` | Verbindungstest zum Sprachmodell (nur Lehrpersonen) |
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
| `OLLAMA_FORMAT_JSON` | Ollama erzwingt gültiges JSON, wo der Tutor JSON erwartet (Standard `true`) |
| `ITS_MOCK_DELAY` | Nur für Tests: Verzögerung des Mock-Providers in Sekunden |
| `ITS_MOCK_FAIL` | Nur für Tests: Schrittarten, bei denen der Mock scheitert, z.B. `THEORIE_SCHRITT` |
| `ITS_LESSONS_DIR` | Optionaler Pfad zum Lektionenordner |
| `TEACHER_PASSWORD` | Passwort für `/teacher`; leer = kein Login (nur lokal) |
| `CLASS_CODE` | Zugangscode für Lernende; leer = kein Code |
| `ITS_TRUST_PROXY_HEADERS` | Name und Rolle aus Proxy-Headern übernehmen (Standard `false`) |
| `ITS_USER_HEADER` | Header mit dem Benutzernamen (Standard `X-Forwarded-User`) |
| `ITS_ROLES_HEADER` | Header mit den Rollen (Standard `X-User-Roles`) |
| `ITS_TEACHER_ROLE` | Rollenname für Lehrpersonen (Standard `teacher`) |
| `ITS_DOMAIN` | Domain für den HTTPS-Betrieb mit Docker/Caddy |

## Tests

```bash
pip install pytest
python3 -m pytest tests/ -q
```

`tests/test_tutor.py` deckt die deterministische Adaptionslogik ab (Level rauf/runter,
Retry, Serien, Randfälle), `tests/test_api.py` testet den kompletten Lernenden-Flow
End-to-End über die API mit Mock-Provider – ohne LLM, ohne laufenden Server.

Oberflächenprüfungen mit Playwright laufen separat gegen eine eigens gestartete
Instanz mit Mock-Provider (bei Bedarf verzögert oder scheiternd):

```bash
pip install playwright && python3 -m playwright install chromium
python3 tests/ui/ui_checks.py          # alle Szenarien, oder z.B. t02
```

Die didaktischen Pakete lassen sich zusätzlich gegen ein echtes Sprachmodell
evaluieren (nicht Teil der normalen Testsuite, schreibt einen Bericht nach
`tests/eval/berichte/`):

```bash
python3 tests/eval/eval_didaktik.py              # alle Pakete, dauert mit qwen3:30b länger
python3 tests/eval/eval_didaktik.py D-01 --anzahl 3
```

## Bewusste Grenzen (MVP)

Kein eigenes Benutzerverzeichnis (ein gemeinsames Lehrpersonen-Passwort und ein
Klassencode, optional Anmeldung über einen Proxy), kein RAG über grosse Dokumente
(das Material geht direkt in den Kontext, sehr lange Dokumente daher kürzen).

## Sinnvolle nächste Schritte

1. Prompts mit realen Lernenden-Antworten tunen (Bewertungsstrenge, Erklärtiefe).
2. Eigene Lektionen über den Editor erstellen und mit der Klasse testen.
3. Tutoring-Modi (erklärend, sokratisch, prüfend, coaching) aus dem Systemkonzept.
4. RAG-Anbindung an P2 für umfangreiches Material.
