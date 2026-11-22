"""Integração com o yt-dlp: metadados, download com progresso e empacotamento."""

import logging
import shutil
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import yt_dlp
from yt_dlp.utils import sanitize_filename

from app import config
from app.models.jobs import Job, JobStatus, MediaFormat, MediaInfo, PlaylistEntry
from app.services.job_store import JobStore, store

logger = logging.getLogger(__name__)

executor = ThreadPoolExecutor(max_workers=config.MAX_CONCURRENT_DOWNLOADS, thread_name_prefix="dl")


class _QuietLogger:
    """Evita que o yt-dlp polua o stdout do servidor."""

    def debug(self, msg: str) -> None:
        logger.debug(msg)

    def info(self, msg: str) -> None:
        logger.debug(msg)

    def warning(self, msg: str) -> None:
        logger.warning(msg)

    def error(self, msg: str) -> None:
        logger.error(msg)


def ffmpeg_available() -> bool:
    if config.FFMPEG_LOCATION:
        return Path(config.FFMPEG_LOCATION).exists()
    return shutil.which("ffmpeg") is not None


def job_dir(job_id: str) -> Path:
    return config.DOWNLOAD_DIR / job_id


def _base_opts() -> dict[str, Any]:
    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "logger": _QuietLogger(),
    }
    if config.FFMPEG_LOCATION:
        opts["ffmpeg_location"] = config.FFMPEG_LOCATION
    return opts


def _video_format(quality: str, has_ffmpeg: bool = True) -> str:
    if not has_ffmpeg:
        # Sem ffmpeg não dá para juntar trilhas: usa só formatos que já vêm com áudio+vídeo
        limit = "" if quality == "best" else f"[height<={int(quality)}]"
        return f"b{limit}[ext=mp4]/b{limit}/b"
    if quality == "best":
        return "bv*[ext=mp4]+ba[ext=m4a]/bv*+ba/b[ext=mp4]/b"
    h = int(quality)
    return (
        f"bv*[height<={h}][ext=mp4]+ba[ext=m4a]/"
        f"bv*[height<={h}]+ba/"
        f"b[height<={h}][ext=mp4]/b[height<={h}]/b"
    )


class FFmpegMissingError(RuntimeError):
    pass


def build_download_opts(job: Job, hooks: dict[str, Any], has_ffmpeg: bool = True) -> dict[str, Any]:
    out_dir = job_dir(job.id)
    template = "%(playlist_index&{} - |)s%(title)s.%(ext)s" if job.playlist else "%(title)s.%(ext)s"

    opts = _base_opts()
    opts.update(
        {
            "outtmpl": str(out_dir / template),
            "noplaylist": not job.playlist,
            "playlistend": config.MAX_PLAYLIST_ITEMS,
            "ignoreerrors": job.playlist,  # um vídeo indisponível não derruba a playlist toda
            "restrictfilenames": False,
            "windowsfilenames": True,
            "progress_hooks": [hooks["progress"]],
            "postprocessor_hooks": [hooks["postprocessor"]],
        }
    )

    if job.format == MediaFormat.MP3:
        if not has_ffmpeg:
            raise FFmpegMissingError("ffmpeg não encontrado: ele é necessário para converter para MP3.")
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [
            {"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"},
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": job.audio_bitrate},
            {"key": "FFmpegMetadata"},
            {"key": "EmbedThumbnail"},
        ]
        opts["writethumbnail"] = True
    elif has_ffmpeg:
        opts["format"] = _video_format(job.quality)
        opts["merge_output_format"] = "mp4"
        opts["postprocessors"] = [{"key": "FFmpegMetadata"}]
    else:
        opts["format"] = _video_format(job.quality, has_ffmpeg=False)

    return opts


def fetch_info(url: str, playlist: bool = False) -> MediaInfo:
    opts = _base_opts()
    opts.update({"skip_download": True, "extract_flat": "in_playlist", "noplaylist": not playlist})

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False) or {}

    is_playlist = info.get("_type") == "playlist"
    entries = [e for e in (info.get("entries") or []) if e] if is_playlist else []

    thumbnail = info.get("thumbnail")
    if not thumbnail and info.get("thumbnails"):
        thumbnail = info["thumbnails"][-1].get("url")
    if not thumbnail and entries:
        thumbs = entries[0].get("thumbnails") or []
        thumbnail = thumbs[-1].get("url") if thumbs else None

    return MediaInfo(
        title=info.get("title"),
        uploader=info.get("uploader") or info.get("channel"),
        duration=info.get("duration"),
        thumbnail=thumbnail,
        is_playlist=is_playlist,
        entry_count=len(entries) if is_playlist else 1,
        entries=[PlaylistEntry(title=e.get("title"), duration=e.get("duration")) for e in entries[:50]],
    )


def _collect_files(directory: Path) -> list[Path]:
    ignored = {".part", ".ytdl", ".webp", ".jpg", ".png", ".temp"}
    return sorted(p for p in directory.iterdir() if p.is_file() and p.suffix.lower() not in ignored)


def _zip_files(files: list[Path], directory: Path, name: str) -> Path:
    archive = directory / f"{sanitize_filename(name, restricted=False) or 'playlist'}.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as zf:
        for f in files:
            zf.write(f, arcname=f.name)
    return archive


def run_download(job_id: str, jobs: JobStore = store) -> None:
    job = jobs.get(job_id)
    if job is None:
        return

    out_dir = job_dir(job.id)
    out_dir.mkdir(parents=True, exist_ok=True)

    def on_progress(d: dict[str, Any]) -> None:
        info = d.get("info_dict") or {}
        index = info.get("playlist_index") or 1
        total = info.get("n_entries") or info.get("playlist_count") or 1

        if d["status"] == "downloading":
            done = d.get("downloaded_bytes") or 0
            size = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            item = (done / size) if size else 0.0
            overall = ((index - 1) + item) / total
            jobs.update(
                job_id,
                status=JobStatus.DOWNLOADING,
                progress=round(min(overall, 0.99) * 100, 1),
                speed=d.get("speed"),
                eta=d.get("eta"),
                current_item=index,
                total_items=total,
                title=job.title or info.get("playlist_title") or info.get("title"),
                thumbnail=job.thumbnail or info.get("thumbnail"),
            )
        elif d["status"] == "finished":
            jobs.update(job_id, progress=round(min(index / total, 0.99) * 100, 1))

    def on_postprocess(d: dict[str, Any]) -> None:
        if d.get("status") == "started":
            jobs.update(job_id, status=JobStatus.PROCESSING, speed=None, eta=None)

    hooks = {"progress": on_progress, "postprocessor": on_postprocess}

    try:
        with yt_dlp.YoutubeDL(build_download_opts(job, hooks, ffmpeg_available())) as ydl:
            info = ydl.extract_info(job.url, download=True) or {}

        files = _collect_files(out_dir)
        if not files:
            raise RuntimeError("Nenhum arquivo foi gerado. Verifique a URL e se o ffmpeg está instalado.")

        title = info.get("title") or files[0].stem
        if len(files) > 1:
            jobs.update(job_id, status=JobStatus.PROCESSING)
            download_name = _zip_files(files, out_dir, title).name
        else:
            download_name = files[0].name

        jobs.update(
            job_id,
            status=JobStatus.FINISHED,
            progress=100.0,
            speed=None,
            eta=None,
            title=title,
            files=[f.name for f in files],
            download_name=download_name,
        )
    except Exception as exc:  # noqa: BLE001 - qualquer falha vira estado de erro do job
        logger.exception("Falha no job %s", job_id)
        message = str(exc).replace("ERROR: ", "").strip() or exc.__class__.__name__
        jobs.update(job_id, status=JobStatus.ERROR, error=message[:500], speed=None, eta=None)


def enqueue(job_id: str) -> None:
    executor.submit(run_download, job_id)


def delete_files(job_id: str) -> None:
    shutil.rmtree(job_dir(job_id), ignore_errors=True)
