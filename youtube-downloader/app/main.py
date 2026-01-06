from fastapi import FastAPI

app = FastAPI(
    title="YouTube Downloader API",
    description="API para baixar vídeos, áudios e playlists",
    version="1.0.0"
)

@app.get("/")
def root():
    return {"message": "Backend funcionando!"}
