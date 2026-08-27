# ITS-MVP auf einem Server veröffentlichen

Diese Anleitung bringt das System auf einen Linux-Server (VPS), z.B. bei
Infomaniak. Danach ist es unter https://deine-domain.ch erreichbar –
verschlüsselt, mit Login für die Lehrpersonen-Sicht und Zugangscode für
Lernende. Vorwissen braucht es kaum, die Befehle sind zum Kopieren gedacht.

## Was du brauchst

1. Einen VPS mit Ubuntu (bei Infomaniak: «VPS Lite» genügt für den Anfang).
2. Eine Domain oder Subdomain, deren A-Record auf die IP des Servers zeigt
   (z.B. its.deineschule.ch → 203.0.113.10, einstellbar beim Domain-Anbieter).
3. Einen API-Key, falls das LLM aus der Cloud kommen soll (z.B. Anthropic).
   Hinweis Datenschutz: Für den Pilot mit echten Lernenden war On-Premise
   (RIB-AI-01 mit Ollama) vorgesehen; ein öffentlicher Demo-Server mit
   Cloud-LLM ist für Tests mit fiktiven Daten gedacht.

## Schritt 1: Auf dem Server anmelden und Docker installieren

```bash
ssh ubuntu@DEINE-SERVER-IP
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
exit   # einmal ab- und wieder anmelden, damit die Gruppenrechte greifen
ssh ubuntu@DEINE-SERVER-IP
```

## Schritt 2: Projekt holen und konfigurieren

```bash
git clone https://github.com/DEIN-GITHUB-NAME/its-mvp.git
cd its-mvp
cp .env.example .env
nano .env
```

In der `.env` mindestens diese Werte setzen:

```ini
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...        # deinen Key eintragen

TEACHER_PASSWORD=ein-langes-eigenes-passwort
CLASS_CODE=code-fuer-die-klasse
ITS_DOMAIN=its.deineschule.ch       # deine echte (Sub-)Domain
```

Wichtig: `TEACHER_PASSWORD` muss gesetzt sein, sonst ist die
Lehrpersonen-Sicht für alle offen. Speichern mit Ctrl+O, Enter, Ctrl+X.

## Schritt 3: Starten

```bash
docker compose up -d --build
```

Das baut das System und startet zwei Container: die App selbst und Caddy als
Reverse-Proxy. Caddy holt automatisch ein Let's-Encrypt-Zertifikat für die
Domain – HTTPS funktioniert ohne weiteres Zutun, sofern der A-Record stimmt
und die Ports 80/443 offen sind.

Prüfen:

```bash
docker compose ps                  # beide Container «running»?
docker compose logs -f its         # Logs der App (Ctrl+C zum Beenden)
```

Dann im Browser: https://its.deineschule.ch → Lernenden-Ansicht mit
Zugangscode-Feld. https://its.deineschule.ch/teacher → Login.
https://its.deineschule.ch/api/llm-test → prüft die LLM-Verbindung.

## Updates einspielen

```bash
cd its-mvp
git pull
docker compose up -d --build
```

Die Daten (Lernenden-Sessions, selbst erstellte Lektionen) liegen auf einem
Docker-Volume und überleben Updates und Neustarts.

## Passwort oder Code ändern

`.env` anpassen, dann:

```bash
docker compose up -d --force-recreate its
```

Nach einer Passwortänderung sind alte Logins automatisch ungültig.

## Alles stoppen

```bash
docker compose down          # Daten bleiben erhalten
docker compose down -v       # ACHTUNG: löscht auch alle Daten
```

## Lokal ausprobieren (ohne Server)

Mit Docker Desktop geht das Ganze auch auf dem eigenen Rechner:
`ITS_DOMAIN=localhost` in der `.env` lassen und `docker compose up -d --build`
ausführen. Dann https://localhost öffnen; die Zertifikatswarnung des Browsers
ist normal (selbstsigniertes Zertifikat) und kann bestätigt werden.

## Variante Pilotbetrieb on-premise (RIB-AI-01)

Für den Pilot mit echten Lernenden läuft das System auf RIB-AI-01 mit
`LLM_PROVIDER=ollama`. Damit Lernende von zu Hause zugreifen können, ohne dass
der Server offen im Internet steht, bieten sich Cloudflare Tunnel oder
Tailscale Funnel an – beide brauchen keine offenen Ports. Das richten wir ein,
wenn es so weit ist.
