import subprocess
from pathlib import Path

DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

def download_media(url: str, format: str):
    command = ["yt-dlp"]

    if format == "mp3":
        command += ["-x", "--audio-format", "mp3"]
    elif format == "mp4":
        command += ["-f", "mp4"]

    command += [
        "-o", str(DOWNLOAD_DIR / "%(title)s.%(ext)s"),
        url
    ]

    subprocess.run(command, check=True)
