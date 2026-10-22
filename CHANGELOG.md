# Änderungsprotokoll

Die Version folgt [Semantic Versioning](https://semver.org/lang/de/): Major.Minor.Patch.
Bis zum Pilotbetrieb bleibt die Hauptversion 0. Jeder Auftrag erhöht die Minor-Version,
Korrekturen ohne neue Funktion die Patch-Version. Die Oberfläche zeigt zusätzlich den
Short-Hash des Commits, aus dem der Server läuft (`0.5.0+abc1234`).

## 0.6.0 – 22.10.2026 (Auftrag 5, Feedback zum Test vom 20.10.2026)

- D-19: Erwartete Begründungstiefe passt zur Frage.
- D-20: Sinngleiche Formulierungen mit demselben Fachbegriff werden akzeptiert.
- D-21: Hinweis und Feedback verraten die erwartete Antwort nicht.
- L-04: Archivierte Lektionen lassen sich nicht bearbeiten.
- N-06: Teaching Mode mit «Teach the Tutor» unter jedem Schritt des Tutors.

## 0.5.0 – 15.10.2026 (Auftrag 4, Feedback Pascal vom 13.10.2026)

- L-01: Lernmaterialien global abgelegt, mit Metadaten (Name, Fächer, Niveau, Beschreibung,
  Tags) und automatisch erfassten Datei-Metadaten; neue Seite «Lernmaterialien».
- L-02: Lernmaterialien aus der Ablage im Lektionseditor auswählen, mit Filtern.
- L-03: Lernmaterialien archivieren (löschen) und wiederherstellen.
- T-27: Favicon.
- T-28: Bearbeitung einer Anfrage stoppen.
- T-29: Lernmaterialien als Embeddings in ChromaDB (Chunking mit Overlap).
- T-30: Retrieval Augmented Generation im Tutor.
- T-31: Versionierung mit Anzeige im Fuss jeder Seite.

## 0.4.0 – 13.10.2026 (Auftrag 3)

T-25, T-26, D-13 bis D-18: Legende passend zu den Buttons, Zeitstempel, stimmige Aufgaben,
faire Nachbesserung, vertretbare Alternativen, vorsichtige Formulierungen, «Lösung ansehen» mit
Gegenüberstellung, keine widersprüchlichen Aussagen.

## 0.3.0 – 11.10.2026 (Auftrag 2)

T-08 bis T-24, D-07 bis D-12: Kontextfenster, leere Antworten, Wahlmöglichkeiten statt
Schleifen, Formatierung, Fortsetzen mit Verlauf, Duplizieren, Archivieren, Abmelden,
Header-Logging; didaktische Pakete zur Aufgabenqualität.

## 0.2.0 – 28.9.2026 (Auftrag 1, Phasen 1 bis 4)

T-01 bis T-07, D-01 bis D-06, N-01 bis N-05: Fallbacks, Wartezustände, Rollen,
Lernsequenzen, Lektionsverwaltung, Didaktik-Regelkatalog, Quellenverweise,
Auswertungsansicht, Internetrecherche, Selbsteinschätzung, eigener Lernverlauf.

## 0.1.0 – 27.8.2026

Erster MVP mit Lernenden-Flow, Lehrpersonen-Monitoring, Lektionseditor und Klassentest-Block
(Login, Zugangscode, Deployment).
