import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import __version__, config
from app.models.jobs import DownloadRequest, InfoRequest, Job, JobStatus, MediaInfo
from app.services import downloader
from app.services.job_store import store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(
    title="Down Music Load",
    description="API self-hosted para baixar áudios (MP3) e vídeos (MP4) — inclusive playlists — com yt-dlp.",
    version=__version__,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _get_job_or_404(job_id: str) -> Job:
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Download não encontrado")
    return job


@app.get("/api/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok", "version": __version__, "ffmpeg": downloader.ffmpeg_available()}


@app.post("/api/info", response_model=MediaInfo, tags=["downloads"])
def media_info(data: InfoRequest) -> MediaInfo:
    """Busca título, thumbnail, duração e itens da playlist sem baixar nada."""
    try:
        return downloader.fetch_info(str(data.url), playlist=data.playlist)
    except Exception as exc:  # noqa: BLE001
        message = str(exc).replace("ERROR: ", "").strip()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, message or "Não foi possível ler essa URL") from exc


@app.post("/api/downloads", response_model=Job, status_code=status.HTTP_202_ACCEPTED, tags=["downloads"])
def create_download(data: DownloadRequest) -> Job:
    job = store.add(
        Job(
            url=str(data.url),
            format=data.format,
            playlist=data.playlist,
            quality=data.quality,
            audio_bitrate=data.audio_bitrate,
        )
    )
    downloader.enqueue(job.id)
    return job


@app.get("/api/downloads", response_model=list[Job], tags=["downloads"])
def list_downloads() -> list[Job]:
    return store.list()


@app.get("/api/downloads/{job_id}", response_model=Job, tags=["downloads"])
def get_download(job_id: str) -> Job:
    return _get_job_or_404(job_id)


@app.get("/api/downloads/{job_id}/file", tags=["downloads"])
def get_download_file(job_id: str) -> FileResponse:
    job = _get_job_or_404(job_id)
    if job.status != JobStatus.FINISHED or not job.download_name:
        raise HTTPException(status.HTTP_409_CONFLICT, "O download ainda não terminou")

    path = downloader.job_dir(job.id) / job.download_name
    if not path.is_file():
        raise HTTPException(status.HTTP_410_GONE, "Arquivo não está mais disponível")
    return FileResponse(path, filename=job.download_name)


@app.delete("/api/downloads/{job_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["downloads"])
def delete_download(job_id: str) -> None:
    job = _get_job_or_404(job_id)
    if job.status in (JobStatus.DOWNLOADING, JobStatus.PROCESSING):
        raise HTTPException(status.HTTP_409_CONFLICT, "Aguarde o download terminar para removê-lo")
    store.remove(job.id)
    downloader.delete_files(job.id)


# Frontend estático (precisa vir por último para não sombrear /api)
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
