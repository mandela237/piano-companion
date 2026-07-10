"""Baseline music-analysis engine for Piano Companion.

Produces the `analysis` block of the piano-companion/song@1 schema.
Every detector is a standalone function with a plain signature so it can be
replaced by a stronger model later (e.g. a chord-transcription network or a
beat-tracking transformer) without touching the API layer in main.py.
"""
import numpy as np
import librosa
from scipy.ndimage import median_filter

ENGINE = "librosa-baseline/1.0"
SR = 22050
PREF = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B']

# Krumhansl-Schmuckler key profiles
KS_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
KS_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

# Chord qualities the baseline engine can distinguish. Suffixes use the app's
# chord grammar. 4-note qualities get a small score penalty so they only win
# when the 7th is really present.
QUALS = {'': [0, 4, 7], 'm': [0, 3, 7], '7': [0, 4, 7, 10], 'maj7': [0, 4, 7, 11], 'm7': [0, 3, 7, 10]}
QUAL_PENALTY = {'': 1.0, 'm': 1.0, '7': 0.985, 'maj7': 0.98, 'm7': 0.985}


def detect_key(chroma):
    """Correlate mean chroma against 24 rotated K-S profiles."""
    v = chroma.mean(axis=1)
    best = (-2.0, 0, 'major')
    for rot in range(12):
        r = np.roll(v, -rot)
        for prof, mode in ((KS_MAJOR, 'major'), (KS_MINOR, 'minor')):
            c = float(np.corrcoef(r, prof)[0, 1])
            if c > best[0]:
                best = (c, rot, mode)
    conf = float(np.clip((best[0] + 1) / 2, 0, 1))
    return {'tonic': PREF[best[1]], 'mode': best[2], 'confidence': round(conf, 2)}


def _chord_templates():
    names, mats = [], []
    for root in range(12):
        for suf, ivs in QUALS.items():
            v = np.zeros(12)
            for iv in ivs:
                v[(root + iv) % 12] = 1.0
            v[root] += 0.6
            v /= np.linalg.norm(v)
            names.append(PREF[root] + suf)
            mats.append(v)
    return names, np.array(mats)


CHORD_NAMES, CHORD_MAT = _chord_templates()
CHORD_PEN = np.array([QUAL_PENALTY[n.lstrip('ABCDEFG#b')] if n.lstrip('ABCDEFG#b') in QUAL_PENALTY
                      else 1.0 for n in CHORD_NAMES])


def detect_chords_per_beat(chroma, beat_frames):
    """Template-match a chord id for every inter-beat interval, then smooth."""
    bounds = np.concatenate([[0], beat_frames, [chroma.shape[1]]])
    ids = []
    for i in range(len(bounds) - 1):
        seg = chroma[:, bounds[i]:max(bounds[i] + 1, bounds[i + 1])]
        v = seg.mean(axis=1)
        n = np.linalg.norm(v)
        if n < 1e-6:
            ids.append(ids[-1] if ids else 0)
            continue
        ids.append(int(np.argmax((CHORD_MAT @ (v / n)) * CHORD_PEN)))
    ids = median_filter(np.array(ids), size=5, mode='nearest')
    return ids[1:]  # one per beat interval, aligned with beat i .. beat i+1


def detect_meter(onset_env, beat_frames, chord_ids, hop=512):
    """Choose 3/4 vs 4/4 and the downbeat phase.

    Downbeats tend to carry stronger onsets and chord changes; score every
    (meter, phase) and keep the best.
    """
    strength = onset_env[np.clip(beat_frames, 0, len(onset_env) - 1)]
    changes = np.zeros(len(chord_ids))
    changes[1:] = chord_ids[1:] != chord_ids[:-1]
    best = (-1e9, 4, 0)
    for meter in (3, 4):
        for phase in range(meter):
            idx = np.arange(phase, len(strength), meter)
            if len(idx) < 4:
                continue
            on_down = strength[idx].mean() / (strength.mean() + 1e-9)
            ch_idx = idx[idx < len(changes)]
            ch_on_down = changes[ch_idx].mean() / (changes.mean() + 1e-9) if changes.mean() > 0 else 1.0
            score = on_down + 0.8 * ch_on_down
            if score > best[0]:
                best = (score, meter, phase)
    conf = float(np.clip(best[0] / 4.0, 0.3, 0.95))
    return best[1], best[2], round(conf, 2)


def detect_sections(feats_by_bar, n_bars):
    """Segment bars into sections and label them by repetition."""
    if n_bars < 8:
        return [{'label': 'Section A', 'startBar': 0, 'endBar': n_bars}]
    X = feats_by_bar  # (n_bars, dims)
    k = int(np.clip(round(n_bars / 12), 2, 8))
    try:
        bounds = librosa.segment.agglomerative(X.T, k)
    except Exception:
        bounds = np.array([0])
    bounds = sorted(set([0] + [int(b) for b in bounds] + [n_bars]))
    segs = [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1) if bounds[i + 1] > bounds[i]]

    # cluster segments by mean-feature similarity -> letters
    means = [X[a:b].mean(axis=0) for a, b in segs]
    letters, reps = [], []
    for m in means:
        found = None
        for li, r in enumerate(reps):
            c = float(np.dot(m, r) / (np.linalg.norm(m) * np.linalg.norm(r) + 1e-9))
            if c > 0.975:
                found = li
                break
        if found is None:
            reps.append(m)
            letters.append(len(reps) - 1)
        else:
            letters.append(found)

    counts = {l: letters.count(l) for l in set(letters)}
    # Only claim Verse/Chorus when the structure actually shows distinct,
    # repeating material; otherwise use honest neutral labels.
    if len(counts) < 2:
        return [{'label': f'Section {i + 1}', 'startBar': int(a), 'endBar': int(b)}
                for i, (a, b) in enumerate(segs)]
    chorus = max(counts, key=lambda l: counts[l]) if max(counts.values()) > 1 else None
    out, verse_n, chorus_n = [], 0, 0
    for i, ((a, b), l) in enumerate(zip(segs, letters)):
        if i == 0 and b - a <= 4 and len(segs) > 2:
            label = 'Intro'
        elif i == len(segs) - 1 and b - a <= 4 and len(segs) > 2:
            label = 'Outro'
        elif l == chorus and counts.get(l, 0) > 1:
            chorus_n += 1
            label = f'Chorus {chorus_n}' if counts[l] > 2 else 'Chorus'
        elif counts.get(l, 0) == 1 and 0 < i < len(segs) - 1 and len(segs) >= 4:
            label = 'Bridge'
        else:
            verse_n += 1
            label = f'Verse {verse_n}'
        out.append({'label': label, 'startBar': int(a), 'endBar': int(b)})
    return out


def analyze_file(path):
    """Full pipeline. Returns (analysis_dict, duration_seconds)."""
    y, sr = librosa.load(path, sr=SR, mono=True)
    duration = float(len(y) / sr)

    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, onset_envelope=onset_env)
    tempo = float(np.atleast_1d(tempo)[0])
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    if len(beat_times) < 8:
        raise RuntimeError('Could not track beats in this audio')

    key = detect_key(chroma)
    chord_ids = detect_chords_per_beat(chroma, beat_frames)
    meter, phase, ts_conf = detect_meter(onset_env, beat_frames, chord_ids)

    # bars from downbeats
    down_idx = list(range(phase, len(beat_times), meter))
    med_beat = float(np.median(np.diff(beat_times)))
    bars = []
    for j, bi in enumerate(down_idx):
        start = float(beat_times[bi])
        end = float(beat_times[down_idx[j + 1]]) if j + 1 < len(down_idx) else \
            float(min(duration, beat_times[-1] + med_beat))
        if end - start < med_beat * 0.5:
            continue
        seg_ids = chord_ids[bi:min(bi + meter, len(chord_ids))]
        if len(seg_ids) == 0:
            seg_ids = chord_ids[-1:]
        vals, cnts = np.unique(seg_ids, return_counts=True)
        bars.append({'start': round(start, 3), 'end': round(end, 3),
                     'chord': CHORD_NAMES[int(vals[np.argmax(cnts)])], 'lyric': None})

    # bar-synced features for section detection
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
    tf = librosa.frames_to_time(np.arange(chroma.shape[1]), sr=sr)
    feats = []
    for b in bars:
        m = (tf >= b['start']) & (tf < b['end'])
        if m.sum() == 0:
            feats.append(np.zeros(chroma.shape[0] + mfcc.shape[0]))
        else:
            feats.append(np.concatenate([chroma[:, m].mean(axis=1), mfcc[1:, m].mean(axis=1) / 100,
                                         [0] * (1 if mfcc.shape[0] == 12 else 0)]))
    feats = np.array([f[:25] if len(f) >= 25 else np.pad(f, (0, 25 - len(f))) for f in feats])
    sections = detect_sections(feats, len(bars))

    analysis = {
        'engine': ENGINE,
        'key': key,
        'tempo': {'bpm': round(tempo, 1), 'confidence': 0.8},
        'timeSignature': {'beatsPerBar': int(meter), 'beatUnit': 4, 'confidence': ts_conf},
        'bars': bars,
        'sections': sections,
        'beats': [round(float(t), 3) for t in beat_times],
    }
    return analysis, duration
