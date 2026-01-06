from fastapi import FastAPI
from fastapi import BackgroundTasks
from app.models.jobs import DownloadRequest

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
    # (vamos implementar já já)
    return {"status": "queued"}