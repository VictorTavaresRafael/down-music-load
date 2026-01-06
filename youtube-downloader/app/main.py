from fastapi import FastAPI
from fastapi import BackgroundTasks
from app.models.jobs import DownloadRequest
from app.services.downloader import download_media

app = FastAPI(
    title="YouTube Downloader API",
    description="API para baixar vídeos, áudios e playlists",
    version="1.0.0"
)

@app.get("/")
def root():
    return {"message": "Backend funcionando!"}

@app.post("/download")
def create_download_task(data: DownloadRequest, background_tasks: BackgroundTasks):
    background_tasks.add_task(download_media, data.url, data.format)

    return {
        "message": "Download iniciado",
        "url": data.url,
        "format": data.format
    }