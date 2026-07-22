"""URL validation helpers for OneDrive / cloud folder links.

Extraído de `routes/onedrive.py`.
Do **not** overwrite `services/onedrive.py` (Graph OAuth core).
"""
from __future__ import annotations

FOLDER_URL_VALID_PREFIXES = (
    # OneDrive
    "https://1drv.ms/",
    "https://onedrive.live.com/",
    "https://onedrive.sharepoint.com/",
    # SharePoint genérico
    ".sharepoint.com/",
    # Google Drive
    "https://drive.google.com/",
    # AWS S3
    "s3://",
    # HTTP/HTTPS genérico
    "https://",
    "http://",
)

LINK_URL_VALID_PREFIXES = (
    "https://",
    "http://",
    "s3://",
    "https://1drv.ms/",
    "https://onedrive.live.com/",
    "https://drive.google.com/",
    ".sharepoint.com/",
)


def is_valid_folder_url(folder_url: str) -> bool:
    """Accept OneDrive / SharePoint / Drive / S3 / generic HTTP(S) URLs."""
    for prefix in FOLDER_URL_VALID_PREFIXES:
        if folder_url.startswith(prefix) or prefix in folder_url:
            return True
    return False


def is_valid_link_url(url: str) -> bool:
    """Accept cloud / HTTP(S) URLs for process link CRUD."""
    return any(url.startswith(p) or p in url for p in LINK_URL_VALID_PREFIXES)
