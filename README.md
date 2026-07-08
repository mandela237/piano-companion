# Piano Performance Companion

A live performance companion for pianists, keyboard players and worship musicians.
Import a song, and the app plays the recording while chords, lyrics and keyboard
diagrams track it bar by bar — including the performance's real timing (fermatas
and all). Built as an installable, offline-capable PWA.

## Features

- **Live Performance Mode** — a moving playhead sweeps 16 bars of chords + lyrics
  in sync with the actual recording. *Rehearse* plays the audio; *Live* is silent
  by design (you play, the app keeps time) and keeps the screen awake.
- **Chord difficulty levels** — Beginner (triads), Intermediate (7ths), Advanced
  (faithful transcription of the recording, including its Gm7–C7 and the brass
  voicings as actually played).
- **Chord Dictionary** — 17 chord qualities, inversions, and voicing styles
  (Closed, Open, Gospel, Neo Soul, Rootless, Drop 2), plus a "★ In this song"
  voicing detected from the recording. Chords play via Web Audio.
- **Transpose** — ♭/♯ through all 12 keys with correct spelling; every diagram
  follows.
- **Circle of Fifths** — interactive, with diatonic chords at your level
  (triads / 7ths / extended).
- **Record** — simulated live chord recognition UI.
- **Song analysis** — paste any link to see the import pipeline (demo).

The bundled song is a public-domain U.S. Air Force Band brass performance of
*Amazing Grace* (via Wikimedia Commons), analyzed offline for key (F major),
tempo (66 BPM), bar-by-bar timing and voicings.

## Run locally

Any static server works:

```
python -m http.server 8080
```

Then open http://localhost:8080. To install on a phone, serve over HTTPS
(GitHub Pages works) and use "Add to Home Screen".

## Project layout

- `index.html` — the entire app (no build step, no dependencies)
- `sw.js` — service worker (offline cache)
- `manifest.webmanifest` — PWA manifest
- `audio/` — the analyzed recording (mp3 + ogg)
- `icons/` — app icons

## Roadmap

- Real import + analysis engine (chord/key/beat/voicing detection from YouTube
  and local files) — currently simulated with one pre-analyzed song
- Multiple songs, playlists, cloud sync
- Native build (React Native / Expo) for the app stores
