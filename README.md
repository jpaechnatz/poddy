<h1 align="center">
<img width="120" src="src/app/static/images/logos/logo.webp" alt="" /><br />
Poddy
</h1>

<p align="center">Werbefreie Podcasts als eigener RSS-Feed – selbst gehostet, z. B. auf dem Raspberry Pi.</p>

Poddy ist ein Fork von [Podly Pure Podcasts](https://github.com/podly-pure-podcasts/podly_pure_podcasts).
Die App selbst heißt in der Oberfläche weiterhin „Podly“.

<img width="100%" src="docs/images/screenshot.png" alt="Screenshot der Weboberfläche" />

## Was Poddy macht

1. Du abonnierst einen Podcast in Poddy und bekommst dafür einen eigenen Feed.
2. Poddy lädt neue Folgen herunter.
3. Werbung wird erkannt – per KI (Transkript + LLM) oder über die Kapitelmarken
   der Folge (z. B. Kapitel „Werbung“ oder „Musik: …“).
4. Poddy schneidet sie heraus und liefert die bereinigte Folge an deine Podcast-App.

## Funktionen dieses Forks

- **Kapitel bleiben korrekt:** Kapitelmarken, Kapitelbilder und Links wandern
  mit, wenn Werbung oder Pausen herausgeschnitten werden; Cover und andere
  ID3-Tags bleiben erhalten.
- **Folgen ausschließen:** Titel-Filter pro Feed, z. B. `Stammtisch`.
- **Audio aufbereiten:** lange Pausen kürzen und Lautheit auf −16 LUFS
  normalisieren (pro Feed).
- **Transkripte im Feed:** `podcast:transcript` (WebVTT) passend zur
  geschnittenen Folge, auf Wunsch in jedem Modus; Sprache fest oder „Auto“ für
  Folgen mit fremdsprachigen Einspielern.
- **KI-Zusammenfassung** in der Folgenbeschreibung (pro Feed).
- **Kapitel als JSON:** `podcast:chapters` mit Bildern und Links für Apps, die
  Podcasting 2.0 unterstützen.
- **Kapitel-Modus mit Rückfall:** Folgen ohne Kapitel werden automatisch per KI
  verarbeitet.

Alle neuen Optionen sind pro Feed in den Feed-Einstellungen zu finden und
standardmäßig aus.

## Installation

Poddy wird aus diesem Repository gebaut. Die fertigen Images des
Originalprojekts (`./run_podly_docker.sh` ohne `--dev`) enthalten die
Funktionen dieses Forks **nicht**.

```bash
git clone https://github.com/jpaechnatz/poddy.git
cd poddy
cp .env.local.example .env.local   # API-Keys und Login eintragen
docker compose -f compose.pi.yml up -d --build
```

Danach läuft Poddy unter `http://<rechner>:5001`. `compose.pi.yml` baut die
schlanke „lite“-Variante (Transkription über einen externen Dienst wie
OpenRouter oder Groq) und funktioniert auf dem Raspberry Pi (arm64) wie auf
normalen PCs (x86_64).

- **Raspberry Pi, OpenRouter/Voxtral, Tailscale Funnel:**
  [docs/raspberry_pi.md](docs/raspberry_pi.md)
- **Lokales Whisper, GPU, Entwicklung:**
  [docs/how_to_run_beginners.md](docs/how_to_run_beginners.md) und
  [docs/contributors.md](docs/contributors.md)

Wenn Poddy aus dem Internet erreichbar ist, unbedingt `REQUIRE_AUTH=true`
setzen (siehe `.env.local.example`).

## Kosten

Poddy selbst ist kostenlos. Kosten entstehen nur, wenn Transkription oder LLM
über einen externen Anbieter laufen, und hängen von Modell und Folgenlänge ab.
Im Kapitel-Modus ohne Transkript fallen gar keine API-Kosten an.

## Mitmachen

Lokale Einrichtung, Tests und Konventionen: [docs/contributors.md](docs/contributors.md).

## Lizenz

Siehe [LICENCE](LICENCE). Poddy baut auf der Arbeit der Podly-Pure-Podcasts-Entwickler auf.
