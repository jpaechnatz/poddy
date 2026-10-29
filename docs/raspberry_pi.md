# Poddy auf dem Raspberry Pi

Getestet ist das Setup für einen Raspberry Pi 4 oder 5 mit 64-Bit-Raspberry-Pi-OS.
Poddy läuft dort als **lite**-Image: ohne lokales Whisper/PyTorch, die
Transkription geht an einen externen Dienst (Standard: OpenRouter).
Werbeschnitt, Kapitel, Lautheit usw. rechnet der Pi selbst mit ffmpeg.

Empfehlung: mindestens 4 GB RAM und eine SSD/NVMe statt SD-Karte, weil pro
Folge Original und bearbeitete Datei zeitweise doppelt auf der Platte liegen.

Die Anleitung geht davon aus, dass Poddy per Tailscale Funnel von unterwegs
erreichbar sein soll. Nur im Heimnetz: siehe [Ohne Tailscale](#ohne-tailscale).

## 1. Voraussetzungen

```bash
uname -m          # muss "aarch64" ausgeben (64-Bit). "armv7l" wird nicht unterstützt.
id -u             # 1000 passt; sonst PUID=<zahl> und PGID=<zahl> in die Datei .env (Schritt 3)
docker compose version || curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"   # danach einmal ab- und wieder anmelden
```

## 2. Code holen

```bash
git clone https://github.com/jpaechnatz/poddy.git
cd poddy
```

## 3. Konfiguration

```bash
cp .env.local.example .env.local
openssl rand -hex 32      # Ausgabe kopieren, wird unten PODLY_SECRET_KEY
nano .env.local
```

Im Abschnitt SCHNELLSTART nur den OpenRouter-Key eintragen; KI-Modell,
Transkriptionsmodell und Sprache sind dort schon gesetzt. Den Key legst du unter
https://openrouter.ai/keys an (vorher Guthaben aufladen). Dazu bei ANMELDUNG
und TAILSCALE das `#` vor diesen Zeilen entfernen und Werte eintragen:

```ini
# SCHNELLSTART (schon vorhanden, nur Key ersetzen)
OPENROUTER_API_KEY=sk-or-v1-...
LLM_MODEL=openrouter/~deepseek/deepseek-flash-latest
WHISPER_REMOTE_MODEL=openai/whisper-large-v3-turbo
WHISPER_LANGUAGE=de

# ANMELDUNG
REQUIRE_AUTH=true
PODLY_ADMIN_USERNAME=admin
PODLY_ADMIN_PASSWORD=ein-langes-passwort
PODLY_SECRET_KEY=<Ausgabe von openssl>

# TAILSCALE
PODLY_TRUSTED_PROXY=172.30.42.1
```

Dann den Port nur auf dem Pi selbst veröffentlichen (Datei `.env`, ohne
`.local`, liest Docker Compose automatisch):

```bash
echo "PODDY_BIND_ADDRESS=127.0.0.1" > .env
```

Was die Zeilen bewirken:

- `OPENROUTER_API_KEY` gilt für Transkription und KI zugleich.
- `LLM_MODEL`: KI für Werbeerkennung, Kapitel und Zusammenfassungen. Der Alias
  `~deepseek/deepseek-flash-latest` zeigt immer auf das neueste
  DeepSeek-Flash-Modell. `WHISPER_REMOTE_MODEL`: Transkription mit Whisper
  Large v3 Turbo. Alternativen, z. B. Voxtral, stehen kommentiert weiter unten
  in der Datei; die Zeile im Schnellstart dann ersetzen, nicht doppelt eintragen.
- `WHISPER_LANGUAGE=de`: Eine feste Sprache ist für einsprachige Podcasts die
  bessere Wahl; fremdsprachige Einspieler werden dann meist übersetzt. `auto`
  erkennt die Sprache je Abschnitt von etwa 10 Minuten und lohnt sich nur, wenn
  sie von Folge zu Folge wechselt. Englische Podcasts wie Darknet Diaries
  stellst du in den Feed-Einstellungen auf „English“.
- `REQUIRE_AUTH=true` ist Pflicht, sobald Poddy öffentlich erreichbar ist.
  Ohne Login antworten Feeds, Audio, Transkripte und Kapitel mit 401. Das
  Admin-Konto wird beim ersten Start angelegt.
- `PODLY_TRUSTED_PROXY` sorgt dafür, dass Poddy das `https` von Tailscale
  übernimmt. Ohne diese Zeile stehen im Feed `http://…`-Links.
- `PODDY_BIND_ADDRESS=127.0.0.1` verhindert, dass jemand im Heimnetz Poddy
  direkt über die Proxy-Adresse anspricht.

Die Datenbank (`src/instance/sqlite3.db`) legt Poddy beim ersten Start selbst
an und bringt sie bei jedem Start per Migration auf den aktuellen Stand.

## 4. Starten

```bash
docker compose -f compose.pi.yml up -d --build
docker compose -f compose.pi.yml logs -f      # Strg+C beendet nur die Anzeige
```

Der Build dauert auf dem Pi beim ersten Mal einige Minuten. Fertig ist er,
wenn dieser Test auf dem Pi antwortet (bis dahin kommt „Connection refused“
oder gar nichts; einfach nach einer Minute wiederholen):

```bash
curl -sI http://127.0.0.1:5001/ | head -1      # erwartet: HTTP/1.1 200 OK
```

## 5. Tailscale Funnel

```bash
tailscale version || curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
sudo tailscale funnel --bg 5001
tailscale funnel status
```

Ist Funnel in deinem Tailnet noch nicht erlaubt, gibt der Befehl einen Link zum
Freischalten in der Tailscale-Admin-Konsole aus. Danach ist Poddy unter
`https://<pi-name>.<tailnet>.ts.net` erreichbar; das Zertifikat kann beim
allerersten Aufruf etwas dauern.

Nur im eigenen Tailnet (nicht öffentlich) reicht statt Funnel
`sudo tailscale serve --bg 5001`.

## 6. Erste Anmeldung: nur neue Folgen bearbeiten

1. `https://<pi-name>.<tailnet>.ts.net` öffnen und mit Admin-Name und
   Passwort aus `.env.local` anmelden.
2. Unter **Settings → Advanced → General** den Wert **„Episodes to enable on
   new feeds“ auf `0`** setzen und speichern, **bevor** du Feeds hinzufügst. Sonst werden
   beim Hinzufügen gleich die neuesten Folgen aus dem Archiv bearbeitet (Standard: 1).
3. „Auto-enable new episodes“ eingeschaltet lassen: Neu erscheinende Folgen
   werden dann automatisch bearbeitet.
4. Optional für den Kosten-Tab: Auf derselben Seite unter „Cost estimates“
   „Whisper rate ($ per hour)“ auf `0.01` setzen (Whisper Turbo bei
   OpenRouter). KI-Kosten übernimmt Poddy direkt aus den OpenRouter-Antworten;
   die Transkription schätzt es mit diesem Stundensatz.

Wurden schon Folgen eines Feeds freigegeben, setzt **„Mark backlog as seen“**
im Menü des Feeds (drei Punkte) den Stand zurück: Alle bisherigen Folgen gelten als gesehen,
nur neue werden bearbeitet.

## 7. Beispiel: Retrokompott

Feed hinzufügen, entweder über die Suche („Retrokompott“) oder mit der RSS-URL:

```
http://www.medienpublikation.de/retrocompod/podcastgen/feed.xml
```

Dann in den Feed-Einstellungen (Zahnrad-Symbol „Feed settings“ am Feed):

| Einstellung | Wert |
|---|---|
| Ad Detection Strategy | Chapter-based |
| Filter Strings | `werbung,musik:,titelmusik` |
| Exclude episodes by title | `Stammtisch` |
| Transcription language | German |
| Audio polishing | Normalize loudness (-16 LUFS) |
| Extras (optional, kostet API-Guthaben) | Always transcribe, AI summary |

Der Kapitel-Modus braucht keine KI: Er schneidet Kapitel, deren Titel einen der
Begriffe enthält („Titelmusik“, „Musik: …“, „Werbung …“), ohne Beachtung der
Groß-/Kleinschreibung. Folgen ohne Kapitel werden automatisch per
LLM-Werbeerkennung verarbeitet.

## 8. In der Podcast-App abonnieren

Im Feed auf **„Subscribe to Poddy RSS“** klicken: Das kopiert einen Link mit
eigenem Feed-Token. Diesen Link in der Podcast-App über „Per URL hinzufügen“
eintragen; Benutzername und Passwort braucht die App nicht.

Kontrolle: Den Link im Browser öffnen. Im XML muss
`<enclosure url="https://<pi-name>.<tailnet>.ts.net/…` stehen. Steht dort
`http://`, fehlt `PODLY_TRUSTED_PROXY` oder der Container wurde danach nicht
neu gestartet.

## Ohne Tailscale

Nur im Heimnetz: In Schritt 3 `PODLY_TRUSTED_PROXY` und die Datei `.env`
weglassen. Poddy ist dann unter `http://<pi-name-oder-ip>:5001` erreichbar.
`REQUIRE_AUTH=true` ist trotzdem empfehlenswert.

## Fehlersuche

```bash
docker compose -f compose.pi.yml ps               # läuft der Container, "healthy"?
docker compose -f compose.pi.yml logs --tail 100  # letzte Logzeilen
```

Vor dem Teilen von Logs API-Keys und Passwörter schwärzen.

## Updates und Backup

```bash
git pull
docker compose -f compose.pi.yml up -d --build
```

Alle Daten (Datenbank, Audio, Logs) liegen in `src/instance/`. Ein Backup davon
reicht, um Poddy wiederherzustellen.
