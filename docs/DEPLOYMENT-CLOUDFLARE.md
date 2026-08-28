# ITS über Cloudflare Tunnel veröffentlichen (tutor.casaai.me)

Das System läuft lokal auf dem eigenen PC (a9-mega), ist aber über
https://tutor.casaai.me aus dem Internet erreichbar. Der Cloudflare Tunnel
baut dafür eine ausgehende Verbindung von diesem PC zu Cloudflare auf – es
müssen keine Ports im Router geöffnet werden, und HTTPS übernimmt Cloudflare.

Voraussetzung: Cloudflare-Account, Domain casaai.me liegt bei Cloudflare.
Die Subdomain muss NICHT von Hand angelegt werden – sie entsteht automatisch,
sobald der Public Hostname im Tunnel eingetragen wird (Schritt 4).

## Schritt 1: Zero-Trust-Dashboard öffnen

1. https://one.dash.cloudflare.com öffnen und anmelden.
2. Links im Menü: **Networks → Tunnels**.

Falls hier schon ein Tunnel für diesen PC existiert (von einer anderen
Applikation): Schritte 2 und 3 überspringen und beim bestehenden Tunnel nur
den zusätzlichen Public Hostname eintragen (Schritt 4). Pro PC läuft
üblicherweise ein cloudflared-Dienst, der beliebig viele Hostnamen bedient.
Läuft der Tunnel der anderen App auf einem anderen Rechner, braucht dieser PC
einen eigenen Tunnel – dann normal weiter mit Schritt 2.

## Schritt 2: Tunnel erstellen

1. **Create a tunnel** → Typ **Cloudflared** → Name z.B. `a9-mega` → Save.
2. Auf der nächsten Seite als Betriebssystem **Windows (64-bit)** wählen.
3. Cloudflare zeigt einen Befehl an, der so beginnt:
   `cloudflared.exe service install eyJhIjo...`
   Diesen Befehl mit dem Kopier-Symbol kopieren. Der lange Teil ist das
   Tunnel-Token – es gehört nur in dieses Fenster, nicht in Chats oder Mails.

## Schritt 3: cloudflared auf dem PC als Dienst installieren

1. Startmenü → «PowerShell» tippen → Rechtsklick →
   **Als Administrator ausführen**.
2. cloudflared installieren:
   ```powershell
   winget install --id Cloudflare.cloudflared
   ```
   (Falls winget fehlt: Installer von
   https://github.com/cloudflare/cloudflared/releases herunterladen.)
3. PowerShell schliessen und als Administrator neu öffnen (damit der Pfad
   aktuell ist), dann den kopierten Befehl aus Schritt 2 einfügen und
   ausführen:
   ```powershell
   cloudflared.exe service install eyJhIjo...   # dein kopierter Befehl
   ```
4. Zurück im Browser: Cloudflare meldet unten «Connectors: 1 Connector» –
   der PC ist verbunden. Der Dienst startet ab jetzt automatisch mit Windows.

## Schritt 4: Public Hostname eintragen (erstellt die Subdomain)

Im Tunnel auf **Public Hostname** → **Add a public hostname**:

| Feld | Wert |
|---|---|
| Subdomain | `tutor` |
| Domain | `casaai.me` |
| Type | `HTTP` |
| URL | `localhost:8000` |

Speichern. Cloudflare legt damit automatisch den DNS-Eintrag für
tutor.casaai.me an. Wichtig: Type ist HTTP (nicht HTTPS) – gemeint ist die
lokale Verbindung vom Tunnel zur App; nach aussen liefert Cloudflare
trotzdem HTTPS.

## Schritt 5: Testen

1. Auf dem PC das ITS starten: Doppelklick auf `start.bat` im Projektordner.
2. https://tutor.casaai.me im Browser öffnen – am besten zusätzlich auf dem
   Handy über Mobilfunk, dann ist der Zugriff wirklich «von aussen» getestet.
3. Lernenden-Ansicht: Zugangscode-Feld muss erscheinen (CLASS_CODE aus der
   `.env`). https://tutor.casaai.me/teacher muss auf die Login-Seite führen.

## Betrieb

- Der Tunnel läuft immer (Windows-Dienst). Erreichbar ist das ITS aber nur,
  solange auf dem PC der Server läuft (`start.bat`-Fenster offen) – Fenster
  schliessen beendet den Zugriff. Für Ollama gilt dasselbe: Die Ollama-App
  muss laufen, sonst antwortet der Tutor mit Fallback-Texten.
- Zugangsdaten stehen in der `.env` (TEACHER_PASSWORD für /teacher,
  CLASS_CODE für Lernende). Nach jeder Änderung an der `.env` den Server neu
  starten. Ein Passwortwechsel meldet alle Lehrpersonen automatisch ab.
- Tunnel vorübergehend abschalten: Windows-Dienste öffnen (Windows-Taste,
  «Dienste» tippen), Dienst «cloudflared» stoppen. Oder im
  Cloudflare-Dashboard den Public Hostname löschen.
- Status prüfen: Networks → Tunnels zeigt, ob der Connector verbunden ist.

## Stolpersteine

- **Fehler 502 Bad Gateway** auf tutor.casaai.me: Der Tunnel steht, aber die
  App läuft nicht → `start.bat` starten.
- **Fehler 530 / Tunnel not found**: cloudflared-Dienst läuft nicht →
  Windows-Dienste prüfen oder PC neu starten.
- **Seite lädt, aber Tutor antwortet generisch**: Ollama läuft nicht oder
  falsches Modell in der `.env` → auf dem PC http://localhost:8000/api/llm-test
  aufrufen.
- Der PC darf nicht in den Ruhezustand gehen, solange Lernende arbeiten
  (Windows-Einstellungen → Energie: Ruhezustand auf «Nie» im Netzbetrieb).

## Hinweis Datenschutz

Für Tests und Demos mit fiktiven Namen ist dieses Setup unbedenklich.
Für den Pilot mit echten Lernenden gilt weiterhin der Plan aus dem
Systemkonzept: Betrieb on-premise (RIB-AI-01), Pseudonyme, und die
Zugangsdaten nur der Klasse mitteilen.
