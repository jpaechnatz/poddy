# Podly auf dem Raspberry Pi

Getestet ist das Setup für einen Raspberry Pi 4 oder 5 mit 64-Bit-Raspberry-Pi-OS.
Podly läuft dort als **lite**-Image: ohne lokales Whisper/PyTorch, die
Transkription geht an einen externen Dienst (z. B. OpenRouter mit Voxtral).
Werbeschnitt, Kapitel, Lautheit usw. rechnet der Pi selbst mit ffmpeg.

Empfehlung: mindestens 4 GB RAM und eine SSD/NVMe statt SD-Karte, weil pro
Folge Original und bearbeitete Datei zeitweise doppelt auf der Platte liegen.

## 1. Voraussetzungen prüfen

```bash
uname -m          # muss "aarch64" ausgeben (64-Bit). "armv7l" wird nicht unterstützt.
docker --version  # falls nicht vorhanden:
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"   # danach einmal ab- und wieder anmelden
```

## 2. Code holen

```bash
git clone https://github.com/jpaechnatz/poddy.git
cd poddy
# nach dem Merge reicht main; vorher: git checkout claude/zealous-newton-7x0044
```

## 3. Konfiguration `.env.local`

```bash
cp .env.local.example .env.local
nano .env.local
```

Beispiel für OpenRouter (Transkription mit Voxtral, Werbeerkennung mit einem
LLM über OpenRouter). Den Key legst du unter https://openrouter.ai/keys an:

```ini
# Transkription (OpenAI-kompatible Schnittstelle von OpenRouter)
WHISPER_TYPE=remote
WHISPER_REMOTE_BASE_URL=https://openrouter.ai/api/v1
WHISPER_REMOTE_API_KEY=sk-or-...
WHISPER_REMOTE_MODEL=mistralai/voxtral-small-transcribe-3-0
# OpenRouter nimmt max. 25 MB pro Upload und bricht nach 60 s ab: kleine Stücke
WHISPER_REMOTE_CHUNKSIZE_MB=10

# Werbeerkennung / Zusammenfassung (LiteLLM-Modellname mit "openrouter/"-Präfix)
LLM_API_KEY=sk-or-...
LLM_MODEL=openrouter/<anbieter>/<modell>

# Pflicht, sobald Podly aus dem Internet erreichbar ist (z. B. Tailscale Funnel)
REQUIRE_AUTH=true
PODLY_ADMIN_USERNAME=admin
PODLY_ADMIN_PASSWORD=<langes Passwort>
PODLY_SECRET_KEY=<Ausgabe von: openssl rand -hex 32>

# Nur hinter tailscale serve/funnel oder einem anderen Proxy auf dem Pi:
# Gateway des Docker-Netzwerks aus compose.pi.yml, damit Feed-Links https nutzen
PODLY_TRUSTED_PROXY=172.30.42.1
```

Die Sprache stellst du später pro Feed ein (Deutsch, Englisch, … oder
„Auto-detect“ für Folgen mit fremdsprachigen Einspielern).

## 4. Datenbank

Podly legt die Datenbank (`src/instance/sqlite3.db`) beim ersten Start selbst
an und bringt sie bei jedem Start per Migration auf den aktuellen Stand. Du
musst dafür nichts tun.

## 5. Starten

```bash
docker compose -f compose.pi.yml up -d --build
docker compose -f compose.pi.yml logs -f      # Strg+C beendet nur die Anzeige
```

Die Oberfläche ist dann unter `http://<pi-name-oder-ip>:5001` erreichbar.
Der Build dauert auf dem Pi beim ersten Mal einige Minuten.

## 6. Von unterwegs erreichbar machen: Tailscale Funnel

Funnel stellt Podly unter `https://<pi-name>.<tailnet>.ts.net` öffentlich ins
Internet. Podcast-Apps brauchen das, wenn sie Feeds nicht über dein Tailnet
abrufen können.

```bash
sudo tailscale funnel --bg 5001
tailscale funnel status
```

Wichtig:

- `REQUIRE_AUTH=true` muss gesetzt sein (siehe oben), sonst kann jeder deine
  Feeds und Audios abrufen. Ohne Login antworten Feeds, Audio, Transkripte und
  Kapitel mit 401.
- `PODLY_TRUSTED_PROXY=172.30.42.1` sorgt dafür, dass Podly das `https` von
  Funnel übernimmt. Ohne diese Zeile stehen im Feed `http://…`-Links.
- Prüfen: Feed im Browser öffnen und schauen, ob `<enclosure url="https://…ts.net/…`
  im XML steht.
- Podcast-Apps abonnieren den Feed über den Link mit Feed-Token aus der
  Oberfläche (Feed teilen/kopieren), nicht über Benutzername/Passwort.

Nur im eigenen Tailnet (nicht öffentlich) reicht `sudo tailscale serve --bg 5001`.

## 7. Beispiel: Retrokompott

Feed hinzufügen, dann in den Feed-Einstellungen:

| Einstellung | Wert |
|---|---|
| Exclude episodes by title | `Stammtisch` (direkt nach dem Hinzufügen setzen) |
| Ad Detection Strategy | Chapter-based |
| Filter Strings | `werbung,musik:,titelmusik` |
| Transcription language | German |
| Audio polishing | Normalize loudness |
| Extras (optional, kostet API-Guthaben) | Always transcribe, AI summary |

Der Kapitel-Modus braucht keine KI: Er schneidet Kapitel, deren Titel einen der
Begriffe enthält („Titelmusik“, „Musik: …“, „Werbung …“). Folgen ohne Kapitel
werden automatisch per LLM-Werbeerkennung verarbeitet.

## Updates und Backup

```bash
git pull
docker compose -f compose.pi.yml up -d --build
```

Alle Daten (Datenbank, Audio, Logs) liegen in `src/instance/`. Ein Backup davon
reicht, um Podly wiederherzustellen.
