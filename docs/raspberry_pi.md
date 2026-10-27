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
git checkout claude/zealous-newton-7x0044   # oder main, sobald gemergt
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

# Empfohlen, sobald Podly außerhalb des Heimnetzes erreichbar ist
# REQUIRE_AUTH=true
# PODLY_ADMIN_USERNAME=admin
# PODLY_ADMIN_PASSWORD=...
# PODLY_SECRET_KEY=<lange zufällige Zeichenkette>
```

Die Sprache stellst du später pro Feed ein (Deutsch, Englisch, … oder
„Auto-detect“ für Folgen mit fremdsprachigen Einspielern).

## 4. Datenbank-Migration erzeugen (nur einmal, solange sie im Branch fehlt)

Der Branch fügt neue Datenbankspalten hinzu. Die passende Alembic-Migration
muss es geben, bevor Podly zum ersten Mal startet. Falls in
`src/migrations/versions/` noch keine Migration für
`episode_title_exclude_strings`, `trim_silence`, `audio_edits` usw. liegt,
erzeugst du sie im Container (kein Python auf dem Pi nötig):

```bash
mkdir -p src/instance
docker compose -f compose.pi.yml build
docker compose -f compose.pi.yml run --rm --no-deps \
  -v "$PWD/src/migrations:/app/src/migrations" podly \
  bash -c 'cd /app/src && flask --app app db upgrade && flask --app app db migrate -m "feed extras and audio edits"'
```

Danach liegt eine neue Datei in `src/migrations/versions/`. Kurz prüfen und
committen, damit sie nicht verloren geht:

```bash
git status
git add src/migrations/versions && git commit -m "chore: add migration for feed extras"
```

## 5. Starten

```bash
docker compose -f compose.pi.yml up -d --build
docker compose -f compose.pi.yml logs -f      # Strg+C beendet nur die Anzeige
```

Die Oberfläche ist dann unter `http://<pi-name-oder-ip>:5001` erreichbar.
Der Build dauert auf dem Pi beim ersten Mal einige Minuten.

## 6. Beispiel: Retrokompott

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
