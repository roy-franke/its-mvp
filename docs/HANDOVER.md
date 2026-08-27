# ITS-MVP – Übergabe-Dokument für Claude

Dieses Dokument fasst den Stand des Projekts und die bisherige Zusammenarbeit
zusammen. Es dient als Kontext für eine neue Claude-Session (z.B. auf einem
anderen Rechner), damit dort ohne Unterbruch weitergearbeitet werden kann.
Lies zusätzlich das `README.md` im Projektstamm.

Stand: 27. August 2026 (nachgeführt nach dem Klassentest-Block)

## 1. Projektkontext

Roy Franke (EB Zürich, roy.franke@gmx.ch) entwickelt im Rahmen des
DLH-Innovationsfonds-Projekts «Intelligente tutorielle Systeme erstellen mit KI»
einen ITS-Prototyp. Team: Roy Franke, Christian Flury (Systemkonzept),
Christian Hirt, Christian Roduner (Pilot-Lehrperson, BBW). Ziel: MVP bis
Dezember 2026, danach Pilotbetrieb in einer realen BM-Klasse.

Zentrale Konzeptdokumente (liegen im Claude-Projekt «ITS» als Wissen):
Systemkonzept von Christian Flury (April 2026, drei Ebenen Lektion /
Durchführung / Bearbeitung, Tutoring-Modi, Prinzip «Verlässlichkeit vor
Eloquenz», Lernpfade rekonstruierbar), Featureliste mit Milestones M1-M8,
Roadmap Juli-Dezember 2026, Roys MVP-Done-Kriterien, Pflichtenheft.

Wichtige Projektgeschichte: Im März 2026 gab es einen Reset. Der alte Prototyp
P1 wurde eingefroren; P2 ist eine RAG-Pipeline mit CLI auf dem Linux-System
RIB-AI-01 (GPU, On-Premise). Der hier entwickelte MVP ist ein Neuanfang per
Vibe Coding mit Claude.

## 2. Getroffene Entscheide

- MVP-Scope: Lernenden-Flow plus Lehrpersonen-Monitoring light, danach schrittweise erweitert.
- LLM-Abstraktion von Anfang an: Provider per `.env` umschaltbar (anthropic, openai, ollama, mock). On-Premise mit Ollama ist Must-Have für den Pilotbetrieb.
- Adaptionslogik bewusst als deterministischer Code, nicht als LLM-Entscheid (nachvollziehbar, testbar). Das LLM generiert Inhalte, Bewertungen, Feedback.
- Lektionen als austauschbare JSON-Dateien in `app/lessons/`, materialgebundener Systemprompt.
- Alles wird getestet (pytest) und in Git committet.

## 3. Aktueller Funktionsumfang

Lernenden-Flow: Onboarding mit Name und Lektionsauswahl, Wissenseinstufung
(3 KI-Fragen, Startniveau basic/intermediate/advanced mit Begründung),
adaptiver Lernpfad als Chat-Dialog. Adaption: richtig → weiter, 2 richtige in
Serie → Niveau rauf; falsch → Hinweis und zweiter Versuch, nochmals falsch →
Vereinfachung und Niveau runter. Theorie-Schritte (Lern-Input ohne Bewertung)
kommen adaptiv: auf basic vor jedem neuen Konzept, auf intermediate zum
Einstieg, nach zwei Fehlern als erneute einfachere Erklärung; nie zwei
automatische Theorie-Schritte nacheinander. Buttons «Theorie dazu», «Genauer
erklären», «Frage stellen» (unbewerteter Chat, verrät Lösung nicht).
Pausieren/Fortsetzen über localStorage plus DB-Zustand. Abschlussbilanz mit
Lernzielabgleich.

Nach LLMTutor-Vorbild (Swiss Learning Analytics, siehe Abschnitt 6):
dreistufige Bewertung korrekt/teilweise/falsch (teilweise → Nachbesserung mit
Hinweis, zählt nicht als Fehler; zweite unvollständige Nachbesserung wird
akzeptiert) und Sicherheitsfrage 1-10 vor der ersten Bewertung jeder Aufgabe
(protokolliert, Durchschnitt in der Teacher-Übersicht).

Lehrpersonen: Monitoring unter `/teacher` (Sessionübersicht mit Fortschritt,
Niveau, Quote, Sicherheit; vollständiger Lernverlauf pro Session aus dem
Event-Log). Lektionseditor unter `/teacher/lessons/new`: Material einfügen
oder hochladen (PDF/Word/Text, Textextraktion), KI-Vorschlag für Titel und
Lernziele, Tutor-Hinweise, speichern → sofort verfügbar.

Technisch: FastAPI (Python), SQLite (Sessions + Event-Log, vollständige
Protokollierung), Vanilla-JS-Frontend (3 statische Seiten), KaTeX für
Formeldarstellung (LaTeX-Anweisung im Systemprompt), Diagnose-Endpoint
`/api/llm-test`, 43 pytest-Tests (Adaptionslogik, API End-to-End mit
Mock-Provider, Lektionserstellung). Mock-Provider bewertet heuristisch nach
Antwortlänge (>=40 Zeichen korrekt, 15-39 teilweise, sonst falsch), damit die
Adaption ohne LLM demonstrierbar ist.

## 4. Setup auf einem neuen Rechner

```bash
git clone <REPO-URL>          # Repo liegt auf Roys GitHub-Account, Name: its-mvp
cd its-mvp
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # Provider eintragen, siehe unten
uvicorn app.main:app --reload
# Browser: http://localhost:8000  |  /teacher  |  /api/info  |  /api/llm-test
# Tests: python3 -m pytest tests/ -q
```

`.env` auf Roys MacBook: `LLM_PROVIDER=ollama`, `OLLAMA_MODEL=qwen2.5:7b`.
Zugänge (API-Keys, GitHub-Token) stehen bewusst NICHT in diesem Dokument –
die `.env` ist gitignored und wird pro Rechner neu erstellt.

## 5. Bekannte Stolpersteine (alle schon erlebt)

- `.env` wird nur beim Serverstart gelesen; nach Änderungen uvicorn neu starten.
- Befehle immer im Projektordner ausführen (`cd its-mvp`), venv aktivieren; auf Roys MacBook existiert zusätzlich ein verirrtes `.venv` im Home-Verzeichnis.
- Ollama: Menüleisten-App muss laufen (sonst «Connection refused» auf Port 11434); `OLLAMA_MODEL` muss exakt einem Eintrag aus `ollama list` entsprechen.
- Wenn Einstufungsbegründung oder Theorie generisch klingen («Wir starten sicherheitshalber…», «Lies den Abschnitt im Lektionsmaterial…»), sind das Fallback-Texte → LLM nicht erreichbar → `/api/llm-test` aufrufen.
- Frontend-Änderungen brauchen einen Hard-Refresh (Cmd+Shift+R).
- KaTeX lädt vom CDN; für Betrieb ohne Internet lokal bundeln.
- Roys OpenAI-Key wurde einmal im Chat geteilt und sollte rotiert werden (platform.openai.com).

## 6. Austausch mit Swiss Learning Analytics (LLMTutor)

github.com/SwissLearningAnalytics/LLMTutor – Open-Source-LLM-Tutor aus dem
BeLEARN-Projekt, fallbasiert-sokratisch, drehbuchbasiert (YAML mit grossem
Systemprompt inkl. Musterlösungen), TypeScript/Postgres, Hochschulkontext.
Es besteht ein Austausch mit den Verantwortlichen (Kontakt:
borter@learning-analytics.ch). Komplementär: Ihr Autoren-Engpass (YAML von
Hand) vs. unser Lektionseditor; ihre didaktische Präzision vs. unsere
Adaptivität. Bereits übernommen: dreistufige Bewertung, Feedback-Regeln,
Sicherheitsfrage. Ideen für Zusammenarbeit: Log-Formate abstimmen (ihr
Folgeprojekt erforscht Muster erfolgreichen Lernens), Autorenwerkzeug für
ihre YAML-Tutoren, gemeinsame Evaluationsinstrumente für den Pilot.

## 7. Nächste Schritte (besprochen und priorisiert)

1. **Klassentest-Block – UMGESETZT (27.8.2026)**: Lehrpersonen-Login (`TEACHER_PASSWORD`, signiertes Cookie, Login-Seite `/teacher/login`, Logout; Passwortwechsel invalidiert alte Logins), Zugangscode für Lernende (`CLASS_CODE`, Prüfung beim Session-Start, Pseudonym-Hinweis im Onboarding), Deployment-Paket (Dockerfile, docker-compose mit Caddy/HTTPS, `docs/DEPLOYMENT.md` mit VPS-Anleitung für Infomaniak). Auth-Logik in `app/auth.py`, Secret in der DB (Tabelle `config`), 11 neue Tests in `tests/test_auth.py`. Leere Variablen deaktivieren den Schutz (lokale Entwicklung); in Roys lokaler `.env` auf a9-mega sind Testwerte gesetzt (`teste-mich` / `BM2026`). Noch offen aus diesem Block: tatsächliches Deployment auf einen VPS bzw. Tunnel-Setup für RIB-AI-01.
2. **Prompt-Tuning** mit Roys Praxisbeobachtungen (Bewertungsstrenge, Erklärtiefe, Einstufungskalibrierung; Vergleich Ollama vs. Cloud als Evaluationsergebnis).
3. **Tutoring-Modi** (erklärend, sokratisch, prüfend, coaching) aus dem Systemkonzept; sokratische Hinweis-Treppe von LLMTutor als Vorlage.
4. Später: RAG-Anbindung an P2 für grosse Materialmengen, KaTeX lokal bundeln, Klassenverwaltung.

## 8. Arbeitsweise in der Zusammenarbeit

Roy ist Lehrperson, kein Entwickler; Terminal-Anleitungen konkret und
schrittweise geben (cd in Projektordner, venv aktivieren, Server-Fenster offen
lassen). Deutsch mit Schweizer Rechtschreibung, Du-Form, Fliesstext, keine
KI-Floskeln. Nach jeder Änderung: Tests laufen lassen, End-to-End-Smoke-Test,
README nachführen, Git-Commit mit deutscher Message. Roy testet selbst im
Browser und meldet Beobachtungen, oft mit Screenshots.
