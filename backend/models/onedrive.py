from pydantic import BaseModel
from typing import Optional


class OneDriveFile(BaseModel):
    id: str
    name: str
    size: Optional[int] = None
    is_folder: bool
    modified_at: Optional[str] = None
    web_url: Optional[str] = None
    download_url: Optional[str] = None
