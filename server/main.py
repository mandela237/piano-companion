"""Piano Companion analysis service.

POST /analyze {url}     -> {jobId}
GET  /jobs/{id}         -> {status, step, error?}
GET  /jobs/{id}/result  -> piano-companion/song@1 JSON
GET  /jobs/{id}/audio   -> extracted audio stream (what the app plays)
GET  /health            -> {ok, engine}

Run:  python main.py     (listens on http://127.0.0.1:8756)
"""
import shutil
import subprocess
import tempfile
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
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
               '.opus': 'audio/ogg', '.ogg': 'audio/ogg', '.mp3': 'audio/mpeg', '.wav': 'audio/wav'}


def find_ffmpeg():
    p = shutil.which('ffmpeg')
    if p:
        return p
    hits = sorted(Path.home().glob(
        'AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg*/**/bin/ffmpeg.exe'))
    if hits:
        return str(hits[-1])
    raise RuntimeError('ffmpeg not found — install it (winget install Gyan.FFmpeg)')


FFMPEG = find_ffmpeg()


class AnalyzeReq(BaseModel):
    url: str


def run_job(job_id: str, url: str):
    job = JOBS[job_id]
    dirp = WORK / job_id
    dirp.mkdir(parents=True, exist_ok=True)
    try:
        import yt_dlp
        job.update(status='downloading', step='Fetching audio from YouTube')
        opts = {
            'format': 'bestaudio[ext=m4a]/bestaudio/best',
            'outtmpl': str(dirp / 'audio.%(ext)s'),
            'quiet': True, 'no_warnings': True, 'noplaylist': True,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)

        src = next(p for p in dirp.glob('audio.*') if p.suffix != '.wav')
        job.update(step='Converting audio')
        wav = dirp / 'audio.wav'
        subprocess.run([FFMPEG, '-y', '-i', str(src), '-ac', '1', '-ar', '22050', str(wav)],
                       check=True, capture_output=True)

        job.update(status='analyzing', step='Detecting key, tempo, chords and sections')
        analysis, duration = analyze_file(str(wav))
        wav.unlink(missing_ok=True)

        vid = info.get('id', '')
        song = {
            'schema': 'piano-companion/song@1',
            'id': f'yt:{vid}',
            'title': info.get('title') or f'YouTube video {vid}',
            'artist': info.get('uploader') or info.get('channel') or 'YouTube',
            'duration': duration,
            'source': {'type': 'youtube', 'url': info.get('webpage_url') or url, 'videoId': vid},
            'audio': {'url': f'/jobs/{job_id}/audio', 'format': src.suffix.lstrip('.')},
            'analysis': analysis,
        }
        job.update(status='done', step='Done', result=song)
    except Exception as e:  # surface a readable error, never fake a result
        msg = str(e).replace('\n', ' ')[:300]
        job.update(status='error', error=msg)


@app.get('/health')
def health():
    return {'ok': True, 'engine': ENGINE}


@app.post('/analyze')
def analyze(req: AnalyzeReq):
    job_id = uuid.uuid4().hex[:12]
    JOBS[job_id] = {'status': 'queued', 'step': 'Queued'}
    threading.Thread(target=run_job, args=(job_id, req.url), daemon=True).start()
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
    print(f'Piano Companion analysis service · engine {ENGINE} · ffmpeg: {FFMPEG}')
    uvicorn.run(app, host='127.0.0.1', port=8756)
