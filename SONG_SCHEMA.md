# Song JSON schema — `piano-companion/song@1`

The contract between the analysis service and the app. The player renders
**only** from this structure; nothing about a song is hardcoded in the client.
Any analysis backend (the bundled librosa engine, or future AI music-analysis
models such as source-separation + chord-transcription networks) is valid as
long as it emits this shape.

```jsonc
{
  "schema": "piano-companion/song@1",
  "id": "yt:dQw4w9WgXcQ",              // stable id; "yt:<videoId>" for YouTube
  "title": "Song Title",
  "artist": "Channel or artist",
  "duration": 212.4,                    // seconds
  "source": {
    "type": "youtube",                  // youtube | file | sample
    "url": "https://www.youtube.com/watch?v=…",
    "videoId": "dQw4w9WgXcQ"
  },
  "audio": {
    "url": "http://127.0.0.1:8756/jobs/<jobId>/audio",  // playable stream; relative URLs resolve against the app origin
    "format": "m4a"
  },
  "analysis": {
    "engine": "librosa-baseline/1.0",   // which engine produced this
    "key":            { "tonic": "F", "mode": "major", "confidence": 0.94 },
    "tempo":          { "bpm": 66.2, "confidence": 0.8 },
    "timeSignature":  { "beatsPerBar": 3, "beatUnit": 4, "confidence": 0.7 },

    // One entry per measure, in order. start/end in seconds of the audio.
    // chord uses ASCII accidentals ("Bb", "F#") and the app's suffix grammar:
    //   "" m dim sus2 sus4 6 m6 add9 7 maj7 m7 dim7 m7b5 maj9 9 m9 13
    // lyric is the text sung during that bar, or null when unavailable.
    "bars": [
      { "start": 1.88, "end": 4.60, "chord": "F",  "lyric": "Amazing" },
      { "start": 4.60, "end": 7.29, "chord": "F7", "lyric": "grace, how" }
    ],

    // Song structure over bar indexes (inclusive start, exclusive end).
    "sections": [
      { "label": "Verse 1", "startBar": 0, "endBar": 16 }
    ],

    // Optional: voicings actually played in the recording,
    // as semitone offsets above the chord root.
    "chords": {
      "F":  { "voicing": [0, 7, 12, 16] }
    },

    // Optional: raw beat times, for debugging / re-analysis.
    "beats": [0.98, 1.88, 2.79]
  }
}
```

## Rules

- `bars` is the source of truth for playback sync. Bar durations vary —
  fermatas and rubato are expressed by longer bars.
- `lyric: null` (or omitted) means "no lyrics available"; the app hides the
  lyric line rather than inventing text.
- Confidences are 0–1. The app may surface them but must not fabricate them.
- The client derives Beginner/Intermediate difficulty by *simplifying* the
  detected chords (extensions → 7ths → triads); the service should emit the
  richest chord it can justify.
- If a field can't be detected, emit it with low confidence or omit optional
  fields — never emit invented values.

## Service API

| Endpoint | Description |
|---|---|
| `POST /analyze` `{ "url": "<youtube url>" }` | Start a job → `{ "jobId": "…" }` |
| `GET /jobs/{id}` | `{ "status": "queued|downloading|analyzing|done|error", "step": "…", "error": "…" }` |
| `GET /jobs/{id}/result` | The Song JSON (when `done`) |
| `GET /jobs/{id}/audio` | The extracted audio stream the app plays |
| `GET /health` | `{ "ok": true, "engine": "…" }` |
