# Internetrecherche einrichten (N-03)

Die Internetrecherche ist die dritte Wissensstufe des Tutors. Sie ist
standardmässig aus. Damit sie wirkt, braucht es drei Dinge:

1. einen SearXNG-Dienst, der Ergebnisse als JSON liefert,
2. die Freigabe auf dem Server in der `.env`,
3. die Freigabe in der Lektion (Editor, Abschnitt 4, «Internetrecherche erlauben»).

## SearXNG lokal starten

Am einfachsten mit Docker auf demselben Rechner wie das ITS:

```
docker run -d --name searxng -p 8888:8080 -v searxng:/etc/searxng searxng/searxng
```

Danach in der Datei `settings.yml` im Volume `searxng` die JSON-Ausgabe
einschalten und den Container neu starten:

```yaml
search:
  formats:
    - html
    - json
```

Test im Browser: `http://localhost:8888/search?q=Tierhalterhaftung&format=json`
muss eine JSON-Antwort mit `results` liefern.

## ITS einschalten

In der `.env`:

```
ITS_WEB_SEARCH=true
ITS_SEARXNG_URL=http://localhost:8888
```

Server neu starten. Im Lektionseditor steht unter der Einstellung, ob die
Recherche auf dem Server eingeschaltet ist.

## Was nach aussen geht

Nur eine fachliche Suchanfrage aus Konzept und Lektionstitel, zum Beispiel
«Tierhalterhaftung Haftpflichtrecht Grundlagen». Name, Antworten und
Chatnachrichten der Lernenden verlassen den Server nie. SearXNG selbst fragt
die angeschlossenen Suchmaschinen ohne Cookies und ohne Profil ab.

## Verhalten im Unterricht

Die Recherche kommt nur als Angebot, wenn das Material zu einem Konzept
ausgeschöpft ist: zuerst Allgemeinwissen (falls erlaubt), danach «Ja, schau
im Internet nach». Die Antwort ist orange markiert, nennt die verwendeten
Treffer als Links und trägt den Hinweis, dass die Inhalte nicht von der
Lehrperson geprüft sind. Die Bewertung von Antworten bleibt immer an das
Lektionsmaterial gebunden. Im Lernverlauf der Lehrperson stehen Suchanfrage
und Links.
