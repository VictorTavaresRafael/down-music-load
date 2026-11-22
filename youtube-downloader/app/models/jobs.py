from datetime import UTC, datetime
from enum import Enum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, HttpUrl


def _now() -> datetime:
    return datetime.now(UTC)


class MediaFormat(str, Enum):
    MP3 = "mp3"
    MP4 = "mp4"


class JobStatus(str, Enum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    FINISHED = "finished"
    ERROR = "error"


VideoQuality = Literal["best", "1080", "720", "480", "360"]
AudioBitrate = Literal["320", "192", "128"]


class DownloadRequest(BaseModel):
    url: HttpUrl
    format: MediaFormat = MediaFormat.MP3
    playlist: bool = Field(False, description="Baixa a playlist inteira quando a URL tiver uma")
    quality: VideoQuality = Field("best", description="Altura máxima do vídeo (apenas mp4)")
    audio_bitrate: AudioBitrate = Field("192", description="Bitrate em kbps (apenas mp3)")


class InfoRequest(BaseModel):
    url: HttpUrl
    playlist: bool = False


class PlaylistEntry(BaseModel):
    title: str | None = None
    duration: float | None = None


class MediaInfo(BaseModel):
    title: str | None = None
    uploader: str | None = None
    duration: float | None = None
    thumbnail: str | None = None
    is_playlist: bool = False
    entry_count: int = 1
    entries: list[PlaylistEntry] = []


class Job(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    url: str
    format: MediaFormat
    playlist: bool = False
    quality: VideoQuality = "best"
    audio_bitrate: AudioBitrate = "192"

    status: JobStatus = JobStatus.QUEUED
    progress: float = 0.0
    speed: float | None = None
    eta: int | None = None
    title: str | None = None
    thumbnail: str | None = None
    current_item: int = 0
    total_items: int = 1
    files: list[str] = []
    download_name: str | None = None
    error: str | None = None

    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    def touch(self) -> None:
        self.updated_at = _now()
