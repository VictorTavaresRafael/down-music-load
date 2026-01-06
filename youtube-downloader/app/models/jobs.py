from pydantic import BaseModel

class DownloadRequest(BaseModel):
    url: str
    format: str  # mp3 | mp4 | playlist
