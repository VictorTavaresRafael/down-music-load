import zipfile

from app.models.jobs import Job, MediaFormat
from app.services import downloader

URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert isinstance(body["ffmpeg"], bool)


def test_frontend_is_served(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "Down Music" in res.text


def test_rejects_invalid_url(client, fake_ydl):
    res = client.post("/api/downloads", json={"url": "isso não é url", "format": "mp3"})
    assert res.status_code == 422


def test_rejects_invalid_format(client, fake_ydl):
    res = client.post("/api/downloads", json={"url": URL, "format": "flac"})
    assert res.status_code == 422


def test_mp3_download_lifecycle(client, fake_ydl):
    res = client.post("/api/downloads", json={"url": URL, "format": "mp3", "audio_bitrate": "320"})
    assert res.status_code == 202
    job_id = res.json()["id"]

    job = client.get(f"/api/downloads/{job_id}").json()
    assert job["status"] == "finished"
    assert job["progress"] == 100
    assert job["title"] == "Minha Musica"
    assert job["download_name"] == "Minha Musica.mp3"

    file_res = client.get(f"/api/downloads/{job_id}/file")
    assert file_res.status_code == 200
    assert file_res.content == b"data"

    assert [j["id"] for j in client.get("/api/downloads").json()] == [job_id]

    assert client.delete(f"/api/downloads/{job_id}").status_code == 204
    assert client.get(f"/api/downloads/{job_id}").status_code == 404
    assert not downloader.job_dir(job_id).exists()


def test_playlist_is_zipped(client, fake_ydl):
    fake_ydl.files = ["1 - A.mp3", "2 - B.mp3", "3 - C.mp3"]
    fake_ydl.info = {"title": "Minha Playlist", "_type": "playlist"}

    job_id = client.post("/api/downloads", json={"url": URL, "format": "mp3", "playlist": True}).json()["id"]
    job = client.get(f"/api/downloads/{job_id}").json()

    assert job["status"] == "finished"
    assert job["download_name"] == "Minha Playlist.zip"
    assert len(job["files"]) == 3

    archive = downloader.job_dir(job_id) / job["download_name"]
    with zipfile.ZipFile(archive) as zf:
        assert sorted(zf.namelist()) == fake_ydl.files


def test_error_is_reported(client, fake_ydl):
    fake_ydl.fail = "Video unavailable"
    job_id = client.post("/api/downloads", json={"url": URL, "format": "mp4"}).json()["id"]
    job = client.get(f"/api/downloads/{job_id}").json()

    assert job["status"] == "error"
    assert job["error"] == "Video unavailable"
    assert client.get(f"/api/downloads/{job_id}/file").status_code == 409


def test_info(client, fake_ydl):
    res = client.post("/api/info", json={"url": URL})
    assert res.status_code == 200
    body = res.json()
    assert body["title"] == "Minha Musica"
    assert body["is_playlist"] is False
    assert body["entry_count"] == 1


def test_info_error(client, fake_ydl):
    fake_ydl.fail = "Unsupported URL"
    res = client.post("/api/info", json={"url": URL})
    assert res.status_code == 422
    assert res.json()["detail"] == "Unsupported URL"


def test_unknown_job(client):
    assert client.get("/api/downloads/nope").status_code == 404
    assert client.delete("/api/downloads/nope").status_code == 404


def test_build_opts_mp4_quality():
    job = Job(url=URL, format=MediaFormat.MP4, quality="720")
    opts = downloader.build_download_opts(job, {"progress": None, "postprocessor": None})
    assert "height<=720" in opts["format"]
    assert opts["merge_output_format"] == "mp4"
    assert opts["noplaylist"] is True


def test_build_opts_mp3_bitrate():
    job = Job(url=URL, format=MediaFormat.MP3, audio_bitrate="320", playlist=True)
    opts = downloader.build_download_opts(job, {"progress": None, "postprocessor": None})
    extract = next(p for p in opts["postprocessors"] if p["key"] == "FFmpegExtractAudio")
    assert extract["preferredquality"] == "320"
    assert opts["noplaylist"] is False


def test_mp4_without_ffmpeg_uses_progressive_format():
    job = Job(url=URL, format=MediaFormat.MP4, quality="480")
    opts = downloader.build_download_opts(job, {"progress": None, "postprocessor": None}, has_ffmpeg=False)
    assert "+" not in opts["format"]
    assert "height<=480" in opts["format"]
    assert "postprocessors" not in opts


def test_mp3_without_ffmpeg_fails_clearly(client, fake_ydl, monkeypatch):
    monkeypatch.setattr(downloader, "ffmpeg_available", lambda: False)
    job_id = client.post("/api/downloads", json={"url": URL, "format": "mp3"}).json()["id"]
    job = client.get(f"/api/downloads/{job_id}").json()
    assert job["status"] == "error"
    assert "ffmpeg" in job["error"]
