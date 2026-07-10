"""Piano Companion analysis service.

POST /analyze {url}         -> {jobId}   (YouTube import)
POST /analyze-file  (multipart 'file')   -> {jobId}   (uploaded audio)
GET  /jobs/{id}             -> {status, step, error?, code?}
GET  /jobs/{id}/result      -> piano-companion/song@1 JSON
GET  /jobs/{id}/audio       -> extracted audio stream (what the app plays)
GET  /health                -> {ok, engine}

Errors returned to clients are always user-friendly; raw extractor output is
logged server-side only.

Optional operator config (never exposed to app users):
  YTDLP_COOKIES_FILE  path to a Netscape-format cookies.txt export; used as the
                      first extraction strategy to get past YouTube bot checks.

Run:  python main.py     (127.0.0.1:8756 locally; binds 0.0.0.0 when PORT is set)
"""
import os
import shutil
import subprocess
import tempfile
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from analysis import ENGINE, analyze_file

app = FastAPI(title='Piano Companion analysis service')
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])

WORK = Path(tempfile.gettempdir()) / 'piano-companion-jobs'
WORK.mkdir(parents=True, exist_ok=True)
JOBS: dict = {}

MEDIA_TYPES = {'.m4a': 'audio/mp4', '.mp4': 'audio/mp4', '.webm': 'audio/webm',
               '.opus': 'audio/ogg', '.ogg': 'audio/ogg', '.mp3': 'audio/mpeg',
               '.wav': 'audio/wav', '.flac': 'audio/flac', '.aac': 'audio/aac'}

FRIENDLY = {
    'youtube_blocked': 'YouTube blocked audio extraction for this video. Try another video, '
                       'upload an audio file, or connect a supported extraction method.',
    'unavailable': 'This video is unavailable (private, removed, age-restricted or '
                   'region-locked). Try another video or upload an audio file.',
    'analysis_failed': 'The audio could not be analyzed. Try another video or upload an audio file.',
    'processing_failed': 'Something went wrong while processing this song. '
                         'Try another video or upload an audio file.',
}


class ExtractionError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code if code in FRIENDLY else 'processing_failed'


def classify_yt_error(msg: str) -> str:
    m = msg.lower()
    if ('sign in to confirm' in m or 'not a bot' in m or '429' in m
            or 'too many request' in m or 'captcha' in m):
        return 'youtube_blocked'
    if ('private' in m or 'unavailable' in m or 'removed' in m or 'age' in m
            or 'region' in m or 'copyright' in m or 'terminated' in m):
        return 'unavailable'
    return 'youtube_blocked'


def find_ffmpeg():
    p = shutil.which('ffmpeg')
    if p:
        return p
    hits = sorted(Path.home().glob(
        'AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg*/**/bin/ffmpeg.exe'))
    if hits:
        return str(hits[-1])
    raise RuntimeError('ffmpeg not found — install it (winget install Gyan.FFmpeg / apt install ffmpeg)')


FFMPEG = find_ffmpeg()


def download_audio(url: str, dirp: Path):
    """Pluggable extraction chain. Later this can grow stronger strategies
    (authenticated sessions, PO tokens, third-party extractors) without any
    API change. Raises ExtractionError with a friendly code only."""
    import yt_dlp
    base = {'format': 'bestaudio[ext=m4a]/bestaudio/best',
            'outtmpl': str(dirp / 'audio.%(ext)s'),
            'quiet': True, 'no_warnings': True, 'noplaylist': True}
    strategies = []
    cookies = os.environ.get('YTDLP_COOKIES_FILE')
    if cookies and Path(cookies).exists():
        strategies.append(('cookies', {**base, 'cookiefile': cookies}))
    strategies.append(('default', dict(base)))
    for client in ('android', 'tv'):
        strategies.append((f'player:{client}',
                           {**base, 'extractor_args': {'youtube': {'player_client': [client]}}}))
    last = ''
    for name, opts in strategies:
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
            print(f'[extract] ok via {name}')
            return info
        except Exception as e:  # raw error stays in the server log only
            last = str(e)
            print(f'[extract] strategy {name} failed: {last[:200]}')
            for p in dirp.glob('audio.*'):
                p.unlink(missing_ok=True)
    raise ExtractionError(classify_yt_error(last))


def finish_job(job_id: str, dirp: Path, src: Path, song_meta: dict):
    """Convert, analyze, and store the result. Shared by both import paths."""
    job = JOBS[job_id]
    job.update(step='Converting audio')
    wav = dirp / 'audio.wav'
    subprocess.run([FFMPEG, '-y', '-i', str(src), '-ac', '1', '-ar', '22050', str(wav)],
                   check=True, capture_output=True)
    job.update(status='analyzing', step='Detecting key, tempo, chords and sections')
    analysis, duration = analyze_file(str(wav))
    wav.unlink(missing_ok=True)
    song = {
        'schema': 'piano-companion/song@1',
        'duration': duration,
        'audio': {'url': f'/jobs/{job_id}/audio', 'format': src.suffix.lstrip('.')},
        'analysis': analysis,
        **song_meta,
    }
    job.update(status='done', step='Done', result=song)


def fail_job(job_id: str, code: str, raw: str = ''):
    if raw:
        print(f'[job {job_id}] failed ({code}): {raw[:300]}')
    JOBS[job_id].update(status='error', code=code, error=FRIENDLY[code])


def run_youtube_job(job_id: str, url: str):
    dirp = WORK / job_id
    dirp.mkdir(parents=True, exist_ok=True)
    try:
        JOBS[job_id].update(status='downloading', step='Fetching audio from YouTube')
        info = download_audio(url, dirp)
        src = next(p for p in dirp.glob('audio.*') if p.suffix != '.wav')
        vid = info.get('id', '')
        finish_job(job_id, dirp, src, {
            'id': f'yt:{vid}',
            'title': info.get('title') or f'YouTube video {vid}',
            'artist': info.get('uploader') or info.get('channel') or 'YouTube',
            'source': {'type': 'youtube', 'url': info.get('webpage_url') or url, 'videoId': vid},
        })
    except ExtractionError as e:
        fail_job(job_id, e.code)
    except Exception as e:
        stage = JOBS[job_id].get('status')
        fail_job(job_id, 'analysis_failed' if stage == 'analyzing' else 'processing_failed', str(e))


def run_file_job(job_id: str, src: Path, title: str):
    dirp = src.parent
    try:
        JOBS[job_id].update(status='analyzing', step='Reading uploaded audio')
        finish_job(job_id, dirp, src, {
            'id': f'file:{job_id}',
            'title': title or 'Uploaded audio',
            'artist': 'Uploaded file',
            'source': {'type': 'file', 'url': None, 'videoId': None},
        })
    except Exception as e:
        fail_job(job_id, 'analysis_failed', str(e))


class AnalyzeReq(BaseModel):
    url: str


@app.get('/health')
def health():
    return {'ok': True, 'engine': ENGINE}


@app.post('/analyze')
def analyze(req: AnalyzeReq):
    job_id = uuid.uuid4().hex[:12]
    JOBS[job_id] = {'status': 'queued', 'step': 'Queued'}
    threading.Thread(target=run_youtube_job, args=(job_id, req.url), daemon=True).start()
    return {'jobId': job_id}


@app.post('/analyze-file')
async def analyze_upload(file: UploadFile = File(...)):
    data = await file.read()
    if len(data) > 60 * 1024 * 1024:
        raise HTTPException(413, 'This file is too large (60 MB max). Try a shorter recording.')
    if len(data) < 10_000:
        raise HTTPException(400, 'That file looks empty. Choose an audio recording (mp3, m4a, wav…).')
    job_id = uuid.uuid4().hex[:12]
    dirp = WORK / job_id
    dirp.mkdir(parents=True, exist_ok=True)
    name = Path(file.filename or 'audio.mp3')
    ext = name.suffix.lower() if name.suffix.lower() in MEDIA_TYPES else '.mp3'
    src = dirp / ('audio' + ext)
    src.write_bytes(data)
    JOBS[job_id] = {'status': 'queued', 'step': 'Queued'}
    threading.Thread(target=run_file_job, args=(job_id, src, name.stem), daemon=True).start()
    return {'jobId': job_id}


@app.get('/jobs/{job_id}')
def job_status(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, 'unknown job')
    return {k: v for k, v in job.items() if k != 'result'}


@app.get('/jobs/{job_id}/result')
def job_result(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, 'unknown job')
    if job.get('status') != 'done':
        raise HTTPException(409, f"job is {job.get('status')}")
    return job['result']


@app.get('/jobs/{job_id}/audio')
def job_audio(job_id: str):
    # served from disk so audio survives a service restart
    dirp = WORK / job_id
    if dirp.is_dir():
        for p in sorted(dirp.glob('audio.*')):
            if p.suffix != '.wav':
                return FileResponse(p, media_type=MEDIA_TYPES.get(p.suffix, 'application/octet-stream'))
    raise HTTPException(404, 'audio not found')


if __name__ == '__main__':
    import uvicorn
    port = int(os.environ.get('PORT', '8756'))
    host = os.environ.get('HOST', '0.0.0.0' if 'PORT' in os.environ else '127.0.0.1')
    print(f'Piano Companion analysis service · engine {ENGINE} · ffmpeg: {FFMPEG} · {host}:{port}')
    uvicorn.run(app, host=host, port=port)
