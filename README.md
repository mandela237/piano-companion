# Piano Performance Companion

A live performance companion for pianists, keyboard players and worship
musicians. Paste a YouTube link, the analysis service extracts the audio and
transcribes it, and the player shows synchronized bars — chords, sections and
keyboard diagrams tracking the actual recording as it plays.

## Architecture

```
┌────────────────────────┐   POST /analyze {url}    ┌──────────────────────────┐
│  Web app (this repo)   │ ───────────────────────▶ │  Analysis service        │
│  index.html (PWA)      │   GET /jobs/{id}         │  server/ (FastAPI)       │
│  renders Song JSON     │ ◀─────────────────────── │  yt-dlp + ffmpeg + libro │
│  plays /jobs/{id}/audio│   Song JSON + audio      │  sa baseline engine      │
└────────────────────────┘                          └──────────────────────────┘
```

- **The contract is [SONG_SCHEMA.md](SONG_SCHEMA.md)** (`piano-companion/song@1`):
  key, tempo, time signature, per-bar chords with timestamps, sections, optional
  synced lyrics and voicings. The client renders *only* from this JSON — no
  hardcoded songs.
- **The analysis service** (`server/`) extracts audio with yt-dlp/ffmpeg and runs
  a librosa baseline engine: Krumhansl–Schmuckler key detection, beat tracking,
  3/4-vs-4/4 meter estimation, per-beat chord template matching with smoothing,
  downbeat-aligned measures, and self-similarity section segmentation. Every
  detector in `server/analysis.py` is a standalone function designed to be
  replaced by stronger AI music-analysis models without touching the API.
- **If the service is unreachable** the app shows an informative error — it never
  opens demo content in place of your song.
- `songs/amazing-grace.json` is a bundled, schema-compliant sample (with audio)
  that appears in the library; it is opened only when you tap it.

## Run it

1. **Analysis service** (needs Python 3.11+ and ffmpeg):
   ```powershell
   pip install -r server\requirements.txt
   .\run-server.ps1        # http://127.0.0.1:8756
   ```
2. **App**: open the deployed PWA (or serve this folder statically). Paste a
   YouTube link under *Break down any song*. The service URL is configurable in
   Settings → Analysis service.

### Service URL modes

- **Local development** — when the app itself is served from `localhost`, it
  defaults to `http://127.0.0.1:8756` automatically.
- **Production (GitHub Pages / phones)** — there is no default. `127.0.0.1`
  only exists on the developer's machine, so the deployed app requires a public
  backend URL, entered under **Settings → Analysis Service URL**. Until one is
  configured, imports show: *"Your analysis backend is not deployed yet.
  Deploy the analysis service and paste the public API URL in Settings."*

### Deploying the analysis service

`server/Dockerfile` makes this one step on any Docker host:

- **Render**: New → Web Service → connect this repo → Root Directory `server`
  → Environment `Docker` → deploy. Copy the `https://….onrender.com` URL into
  Settings → Analysis Service URL.
- **Railway / Fly.io**: point them at `server/` — they inject `PORT`
  automatically and the service binds `0.0.0.0`.
- **Your own box**: `pip install -r server/requirements.txt` + ffmpeg, then
  `PORT=8756 python server/main.py` behind any https reverse proxy.

The URL must be **https://** — browsers block plain-http backends from an
https page (mixed content).

### When YouTube blocks extraction (operator notes)

YouTube bot-detection sometimes blocks datacenter IPs ("Sign in to confirm
you're not a bot"). The service already retries with alternative player
clients, returns only friendly messages to users, and the app offers
fallbacks (audio-file upload, manual chord entry, the labeled sample).
To restore YouTube extraction on a blocked host:

1. Export YouTube cookies from a logged-in browser using a
   "cookies.txt" extension (Netscape format).
2. On Render: service → **Environment → Secret Files** → add the file as
   `cookies.txt`, then add env var `YTDLP_COOKIES_FILE=/etc/secrets/cookies.txt`.
3. Redeploy. The cookies file becomes the first extraction strategy.

Cookie setup is operator-only — the app never shows extraction internals to
users. The extraction chain in `server/main.py` (`download_audio`) is the
place to plug in stronger methods later (PO tokens, residential proxies, a
self-hosted extractor box on a home connection — the most reliable option).

## Current analysis quality (baseline engine)

Tempo and meter are solid; key is usually right or a near neighbour; chords are
plausible diatonic transcriptions (maj/min/7th qualities); sections are honest
best-effort with confidence-aware labels; lyrics are reported as unavailable
(no lyric source is wired yet). All confidences are surfaced in the song info
sheet. The upgrade path is swapping detectors in `server/analysis.py` for
dedicated models (chord-transcription networks, source separation, beat
transformers, lyric alignment).

## Project layout

- `index.html` — the entire app (no build step)
- `SONG_SCHEMA.md` — the Song JSON contract
- `server/` — FastAPI analysis service (`main.py` API, `analysis.py` engine)
- `songs/` — bundled sample song JSON
- `audio/`, `icons/`, `sw.js`, `manifest.webmanifest` — PWA assets
