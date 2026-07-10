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

Note: browsers treat `http://127.0.0.1` as a secure origin, so the deployed
HTTPS app can call a locally running service in Chrome/Edge. To use the app on
a phone, host the service somewhere reachable (any box that can run Python)
and set its URL in Settings.

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
