"""Configurações da aplicação, lidas de variáveis de ambiente."""

import os
from pathlib import Path


def _list_env(name: str, default: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


DOWNLOAD_DIR = Path(os.getenv("DOWNLOAD_DIR", "downloads")).resolve()
MAX_CONCURRENT_DOWNLOADS = int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "2"))
FFMPEG_LOCATION = os.getenv("FFMPEG_LOCATION") or None
CORS_ORIGINS = _list_env("CORS_ORIGINS", "*")
MAX_PLAYLIST_ITEMS = int(os.getenv("MAX_PLAYLIST_ITEMS", "100"))

DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
