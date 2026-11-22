import os
import tempfile

# Precisa ser definido antes de importar o app
os.environ.setdefault("DOWNLOAD_DIR", tempfile.mkdtemp(prefix="dml-tests-"))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services import downloader  # noqa: E402
from app.services.job_store import store  # noqa: E402


class FakeYDL:
    """Imita yt_dlp.YoutubeDL: escreve arquivos falsos e dispara os hooks."""

    files: list[str] = ["Minha Musica.mp3"]
    fail: str | None = None
    info: dict = {"title": "Minha Musica", "duration": 200, "uploader": "Artista", "thumbnail": "http://t/x.jpg"}

    def __init__(self, opts):
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=True):
        if self.fail:
            raise RuntimeError(f"ERROR: {self.fail}")
        if download:
            out_dir = os.path.dirname(self.opts["outtmpl"])
            for hook in self.opts["progress_hooks"]:
                hook({"status": "downloading", "downloaded_bytes": 50, "total_bytes": 100, "info_dict": self.info})
            for name in self.files:
                with open(os.path.join(out_dir, name), "wb") as fh:
                    fh.write(b"data")
            for hook in self.opts["postprocessor_hooks"]:
                hook({"status": "started"})
        return self.info


@pytest.fixture
def fake_ydl(monkeypatch):
    FakeYDL.files = ["Minha Musica.mp3"]
    FakeYDL.fail = None
    FakeYDL.info = {"title": "Minha Musica", "duration": 200, "uploader": "Artista", "thumbnail": "http://t/x.jpg"}
    monkeypatch.setattr(downloader.yt_dlp, "YoutubeDL", FakeYDL)
    monkeypatch.setattr(downloader, "ffmpeg_available", lambda: True)
    # Roda o download na mesma thread para o teste ser determinístico
    monkeypatch.setattr(downloader, "enqueue", lambda job_id: downloader.run_download(job_id))
    return FakeYDL


@pytest.fixture
def client():
    for job in store.list():
        store.remove(job.id)
    return TestClient(app)
