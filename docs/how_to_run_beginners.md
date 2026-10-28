# How To Run: Ultimate Beginner's Guide

This guide walks you through setting up Poddy from scratch using Docker. Poddy creates ad-free RSS feeds for podcasts by automatically detecting and removing advertisement segments.

## Highly Recommend!

Want an expert to guide you through the setup? Download an AI powered IDE like cursor https://www.cursor.com/ or windsurf https://windsurf.com/

Most IDEs have a free tier you can use to get started. Alternatively, you can use your own [LLM API key in Cursor](https://docs.cursor.com/settings/api-keys).

Open the AI chat in the IDE. Enable 'Agent' mode if available, which will allow the IDE to help you run commands, view the output, and debug or take corrective steps if necessary.

Paste one of the prompts below into the chat box.

If you don't have the repo downloaded:

```
Help me install docker and run Poddy https://github.com/jpaechnatz/poddy
After the project is cloned, help me:
- install docker & docker compose
- copy `.env.local.example` to `.env.local` and fill in the API keys
- run `docker compose -f compose.pi.yml up -d --build` (builds this fork; do not use the prebuilt upstream images)
- configure the app via the web UI at http://localhost:5001/config (Settings)
Be sure to check if a dependency is already installed before downloading.
We recommend Docker because installing ffmpeg & local whisper can be difficult.
The lite Docker image includes ffmpeg and uses remote transcription (OpenRouter, Groq or another OpenAI-compatible API).
Poddy works with many different LLMs, it does not require an OpenAI key.
Check your work by retrieving the index page from localhost:5001 at the end.
```

If you do have the repo pulled, open this file and prompt:

```
Review this project, follow this guide and start Poddy on my computer.
Briefly, help me:
- install docker & docker compose
- copy `.env.local.example` to `.env.local` and fill in the API keys
- run `docker compose -f compose.pi.yml up -d --build` (builds this fork; do not use the prebuilt upstream images)
- configure the app via the web UI at http://localhost:5001/config (Settings)
Be sure to check if a dependency is already installed before downloading.
We recommend docker because installing ffmpeg & local whisper can be difficult.
The lite Docker image includes ffmpeg and uses remote transcription (OpenRouter, Groq or another OpenAI-compatible API).
Poddy works with many different LLMs; it does not need to work with OpenAI.
Check your work by retrieving the index page from localhost:5001 at the end.
```

## Prerequisites

### Install Docker and Docker Compose

#### On Windows:

1. Download and install [Docker Desktop for Windows](https://docs.docker.com/desktop/install/windows-install/)
2. During installation, make sure "Use WSL 2 instead of Hyper-V" is checked
3. Restart your computer when prompted
4. Open Docker Desktop and wait for it to start completely

#### On macOS:

1. Download and install [Docker Desktop for Mac](https://docs.docker.com/desktop/install/mac-install/)
2. Drag Docker to your Applications folder
3. Launch Docker Desktop from Applications
4. Follow the setup assistant

#### On Linux (Ubuntu/Debian):

```bash
# Update package index
sudo apt update

# Install Docker
sudo apt install docker.io docker-compose-v2

# Add your user to the docker group
sudo usermod -aG docker $USER

# Log out and log back in for group changes to take effect
```

#### Verify Installation:

Open a terminal/command prompt and run:

```bash
docker --version
docker compose version
```

You should see version information for both commands.

### Get an API key

The simplest setup is one [OpenRouter](https://openrouter.ai/keys) key for both
transcription and the LLM:

1. Create an account at [openrouter.ai](https://openrouter.ai/) and add credit.
2. Create a key under [Keys](https://openrouter.ai/keys) and copy it right away.
3. Put it into `.env.local` as `OPENROUTER_API_KEY=sk-or-v1-...` (see below).

Groq, OpenAI and other OpenAI-compatible services work too; the commented
sections in `.env.local.example` show the lines for each.

> **Note**: API usage costs money. Set a spending limit at your provider to avoid surprises.

## Setup Poddy

### Download the Project

```bash
git clone https://github.com/jpaechnatz/poddy.git
cd poddy
```

## Running Poddy

### Run the Application via Docker

Build this fork from source. `./run_podly_docker.sh` without `--dev` pulls the
upstream Podly images, which do not contain this fork's features.

```bash
# Settings and API keys (once); both compose files read .env.local
cp .env.local.example .env.local

# Lite image (remote transcription, e.g. OpenRouter or Groq) - also for Raspberry Pi
docker compose -f compose.pi.yml up -d --build

# Full CPU image with local Whisper (large, slow on small machines)
docker compose -f compose.dev.cpu.yml up -d --build
```

Raspberry Pi specifics: [raspberry_pi.md](raspberry_pi.md).

### Optional: Enable Authentication

The Docker image reads environment variables from `.env.local` files or your shell. To require login:

1. Add the variables to `.env.local` in the project root (no quotes, no spaces around `=`):

```ini
REQUIRE_AUTH=true
PODLY_ADMIN_USERNAME=admin
PODLY_ADMIN_PASSWORD=a-long-password
# generate with: openssl rand -hex 32
PODLY_SECRET_KEY=
```

2. Start Poddy as usual (`docker compose -f compose.pi.yml up -d`). On first boot with auth enabled and an empty database, the admin account is created automatically. If you are turning auth on for an existing volume, clear the `sqlite3.db` file so the bootstrap can succeed.

3. Sign in at `http://localhost:5001`, then open Settings to change your password and add users. Copy a feed's RSS URL with the "Subscribe to Poddy RSS" button. Poddy generates feed-specific access tokens and embeds them in the link so podcast players can subscribe without exposing your main password. Remember to update your environment variables whenever you rotate the admin password.

### First Run

1. Docker will download and build the necessary image (this may take 5-15 minutes)
2. Look for "Serving on http://0.0.0.0:5001" in `docker compose -f compose.pi.yml logs -f`
3. Open your browser to `http://localhost:5001`
4. Configure settings at `http://localhost:5001/config` (Settings)
   - Alternatively, set secrets via Docker env file `.env.local` in the project root and restart the container. See .env.local.example

## Advanced Options

All commands build this fork from source (the prebuilt upstream images used
by `./run_podly_docker.sh` in production mode do not contain its features).

```bash
# Full image with NVIDIA GPU support for local Whisper
USE_GPU=true USE_GPU_NVIDIA=true \
  BASE_IMAGE=nvidia/cuda:12.4.1-cudnn-devel-ubuntu22.04 \
  docker compose -f compose.dev.cpu.yml -f compose.dev.nvidia.yml up -d --build

# Just build the image without running
docker compose -f compose.pi.yml build

# Rebuild from scratch (useful for troubleshooting)
docker compose -f compose.pi.yml build --no-cache
```

## Using Poddy

### Adding Your First Podcast

1. Optional, before adding feeds: set **Settings → Advanced → General → "Episodes to enable on new feeds"** to `0` if only episodes published from now on should be processed (default: the newest 1)
2. Add a podcast: search for it by name or paste its RSS feed URL
3. With "Auto-enable new episodes" on, Poddy processes new episodes automatically
4. Per-feed options (ad detection strategy, title filter, loudness, transcripts) are behind the gear icon "Feed settings"; "Mark backlog as seen" in the feed menu skips the existing episodes

### Getting Your Ad-Free RSS Feed

1. Open the feed and click "Subscribe to Poddy RSS" to copy its Poddy feed URL
2. Add this URL in your podcast app ("add by URL") instead of the original
3. Your podcast app will now download ad-free versions!

## Troubleshooting

### "Docker command not found"

- Make sure Docker Desktop is running
- On Windows, restart your terminal after installing Docker
- On Linux, make sure you logged out and back in after adding yourself to the docker group

### Cannot connect to the Docker daemon. Is the docker daemon running?

- If using docker desktop, open up the app, otherwise start the daemon

### "Permission denied" errors

- On Linux, make sure you logged out and back in after adding yourself to the docker group
- On Windows, try running Command Prompt as Administrator

### API errors (transcription or LLM)

- Double-check the key in `.env.local` or in Settings, then restart: `docker compose -f compose.pi.yml up -d`
- Make sure your provider account has credit or billing set up
- Check your usage limits haven't been exceeded

### Port 5001 already in use

- Another application is using port 5001
- **Docker users**: Either stop that application or change the left side of `5001:5001` under `ports:` in the compose file you use (e.g. `compose.pi.yml`)
- **Native users**: Start with a different port via the `PORT` environment variable
- To kill processes on that port run `lsof -i :5001 | grep LISTEN | awk '{print $2}' | xargs kill -9`

### Out of memory errors

- Close other applications to free up RAM
- Use the lite image (`compose.pi.yml`) with remote transcription instead of local Whisper

## Stopping Poddy

To stop the application:

If you have launched it in the foreground by omitting the `-d` parameter:
1. In the terminal where Poddy is running, press `Ctrl+C`
2. Wait for the container to stop gracefully

If you have launched it in the background using the `-d` parameter:
1. In the project folder, run `docker compose -f compose.pi.yml down` (use the same compose file you started with)
2. Wait for the container to stop gracefully

In both cases this output should appear to indicate that it has stopped:

```sh
[+] Running 2/2
 ✔ Container podly-pure-podcasts        Removed
 ✔ Network podly-pure-podcasts-network  Removed
```

## Upgrading Poddy

To upgrade the application while you are in the terminal where it is running:
1. [Stop it](#stopping-poddy)
2. Execute `git pull`
3. [Run it again with `--build`](#running-poddy)

## Getting Help

If you encounter issues, open an issue at https://github.com/jpaechnatz/poddy/issues.

## What's Next?

Once you have Poddy running:

- Explore the web interface to add more podcasts
- Fine-tune per-feed options with the gear icon "Feed settings"
- Make it reachable from your phone: [raspberry_pi.md](raspberry_pi.md) covers Tailscale Funnel
- Enjoy your ad-free podcasts!
