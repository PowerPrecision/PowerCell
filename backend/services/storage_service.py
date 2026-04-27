"""
Storage Service - Factory Pattern for provider-agnostic file operations.

Reads the active storage provider from system_settings and routes to
the correct adapter (Local, S3, OneDrive).
"""
import os
import re
import logging
import tempfile
import shutil
from abc import ABC, abstractmethod
from typing import Dict, Optional, BinaryIO, Any

logger = logging.getLogger(__name__)

# Categories for client document folders
DEFAULT_CATEGORIES = [
    "Documentos Pessoais",
    "Financeiros",
    "Imóvel",
    "Bancários",
    "RGPD",
    "Outros",
]


def sanitize_folder_name(name: str) -> str:
    """Remove special characters from folder name."""
    if not name:
        return "cliente"
    name = re.sub(r'[^\w\s-]', '', name)
    name = re.sub(r'\s+', '_', name.strip())
    return name[:50] if name else "cliente"


class StorageAdapter(ABC):
    """Abstract base class for storage adapters."""

    @abstractmethod
    def is_configured(self) -> bool:
        """Check if the storage adapter is ready for operations."""
        pass

    @abstractmethod
    def upload_file(
        self,
        file_obj: BinaryIO,
        client_id: str,
        client_name: str,
        category: str,
        filename: str,
        content_type: str = None,
        second_client_name: str = None,
        s3_folder: str = None,
    ) -> Optional[str]:
        """Upload a file and return the storage path/key."""
        pass

    @abstractmethod
    def get_file_content(self, storage_path: str) -> Optional[bytes]:
        """Get file content as bytes."""
        pass

    @abstractmethod
    def delete_file(self, storage_path: str) -> bool:
        """Delete a file."""
        pass

    @abstractmethod
    def file_exists(self, storage_path: str) -> bool:
        """Check if a file exists."""
        pass

    @abstractmethod
    def get_presigned_url(self, storage_path: str, expiration: int = 3600) -> Optional[str]:
        """Get a temporary URL for file access."""
        pass

    @abstractmethod
    def list_files(
        self,
        client_id: str,
        client_name: str,
        second_client_name: str = None,
        s3_folder: str = None,
    ) -> Dict[str, Any]:
        """List all files for a client organized by category."""
        pass

    @abstractmethod
    def initialize_client_folders(
        self,
        client_id: str,
        client_name: str,
        second_client_name: str = None,
    ) -> tuple:
        """Create default folder structure for a new client."""
        pass


class LocalStorageAdapter(StorageAdapter):
    """Local filesystem storage adapter."""

    def __init__(self, base_path: str = None):
        self.base_path = base_path or os.path.join(tempfile.gettempdir(), "powercell_uploads")
        os.makedirs(self.base_path, exist_ok=True)

    def is_configured(self) -> bool:
        return os.path.isdir(self.base_path)

    def _get_client_path(self, client_name: str) -> str:
        safe = sanitize_folder_name(client_name)
        return os.path.join(self.base_path, "Documentação Clientes", safe)

    def upload_file(
        self,
        file_obj: BinaryIO,
        client_id: str,
        client_name: str,
        category: str,
        filename: str,
        content_type: str = None,
        second_client_name: str = None,
        s3_folder: str = None,
    ) -> Optional[str]:
        try:
            if s3_folder:
                base = os.path.join(self.base_path, s3_folder.replace("/", os.sep).lstrip(os.sep))
            else:
                base = self._get_client_path(client_name)

            cat = sanitize_folder_name(category)
            if cat.lower() == "all":
                cat = "Outros"

            dir_path = os.path.join(base, cat)
            os.makedirs(dir_path, exist_ok=True)

            file_path = os.path.join(dir_path, filename)
            with open(file_path, "wb") as f:
                shutil.copyfileobj(file_obj, f)

            rel_path = os.path.relpath(file_path, self.base_path)
            return rel_path
        except Exception as e:
            logger.error(f"[LocalStorage] Upload error: {e}")
            return None

    def get_file_content(self, storage_path: str) -> Optional[bytes]:
        try:
            full_path = os.path.join(self.base_path, storage_path)
            if os.path.isfile(full_path):
                with open(full_path, "rb") as f:
                    return f.read()
        except Exception as e:
            logger.error(f"[LocalStorage] Read error: {e}")
        return None

    def delete_file(self, storage_path: str) -> bool:
        try:
            full_path = os.path.join(self.base_path, storage_path)
            if os.path.isfile(full_path):
                os.remove(full_path)
                return True
        except Exception as e:
            logger.error(f"[LocalStorage] Delete error: {e}")
        return False

    def file_exists(self, storage_path: str) -> bool:
        full_path = os.path.join(self.base_path, storage_path)
        return os.path.isfile(full_path)

    def get_presigned_url(self, storage_path: str, expiration: int = 3600) -> Optional[str]:
        # Local storage doesn't generate presigned URLs
        return None

    def list_files(
        self,
        client_id: str,
        client_name: str,
        second_client_name: str = None,
        s3_folder: str = None,
    ) -> Dict[str, Any]:
        if s3_folder:
            base = os.path.join(self.base_path, s3_folder.replace("/", os.sep).lstrip(os.sep))
        else:
            base = self._get_client_path(client_name)

        files_by_category = {cat: [] for cat in DEFAULT_CATEGORIES}
        total_size = 0

        if not os.path.isdir(base):
            return {"files": files_by_category, "categories": DEFAULT_CATEGORIES,
                    "stats": {"total_files": 0, "total_size": 0, "total_size_formatted": "0 B"},
                    "base_path": None}

        for root, dirs, filenames in os.walk(base):
            for fname in filenames:
                if fname.endswith(".keep"):
                    continue
                rel = os.path.relpath(root, base)
                parts = rel.split(os.sep)
                cat = parts[0].replace("_", " ") if parts else "Outros"
                if cat.lower() == "all":
                    cat = "Outros"
                matched = False
                for c in DEFAULT_CATEGORIES:
                    if c.lower().replace(" ", "_") == cat.lower().replace(" ", "_"):
                        cat = c
                        matched = True
                        break
                    if cat.lower() in c.lower() or c.lower() in cat.lower():
                        cat = c
                        matched = True
                        break
                if not matched:
                    cat = "Outros"

                fpath = os.path.join(root, fname)
                size = os.path.getsize(fpath)
                total_size += size
                files_by_category.setdefault(cat, []).append({
                    "name": fname,
                    "path": os.path.relpath(fpath, self.base_path),
                    "size": size,
                    "size_formatted": self._format_size(size),
                    "last_modified": os.path.getmtime(fpath),
                    "category": cat,
                    "temporary_url": "",
                })

        total_files = sum(len(f) for f in files_by_category.values())
        return {
            "files": files_by_category,
            "categories": DEFAULT_CATEGORIES,
            "stats": {"total_files": total_files, "total_size": total_size,
                      "total_size_formatted": self._format_size(total_size)},
            "base_path": base,
        }

    def initialize_client_folders(
        self,
        client_id: str,
        client_name: str,
        second_client_name: str = None,
    ) -> tuple:
        try:
            base = self._get_client_path(client_name)
            for cat in DEFAULT_CATEGORIES:
                cat_dir = os.path.join(base, sanitize_folder_name(cat))
                os.makedirs(cat_dir, exist_ok=True)
                keep = os.path.join(cat_dir, ".keep")
                if not os.path.exists(keep):
                    open(keep, "w").close()
            return (True, base)
        except Exception as e:
            logger.error(f"[LocalStorage] Init folders error: {e}")
            return (False, None)

    def _format_size(self, size_bytes: int) -> str:
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


class S3StorageAdapter(StorageAdapter):
    """Amazon S3 (or compatible) storage adapter - wraps existing S3Service."""

    def __init__(self):
        from services.s3_storage import S3Service
        self._service = S3Service()

    def is_configured(self) -> bool:
        return self._service.is_configured()

    def upload_file(self, file_obj, client_id, client_name, category, filename,
                    content_type=None, second_client_name=None, s3_folder=None):
        return self._service.upload_file(
            file_obj, client_id, client_name, category, filename,
            content_type, second_client_name, s3_folder,
        )

    def get_file_content(self, storage_path):
        return self._service.get_file_content(storage_path)

    def delete_file(self, storage_path):
        return self._service.delete_file(storage_path)

    def file_exists(self, storage_path):
        return self._service.file_exists(storage_path)

    def get_presigned_url(self, storage_path, expiration=3600):
        return self._service.get_presigned_url(storage_path, expiration)

    def list_files(self, client_id, client_name, second_client_name=None, s3_folder=None):
        return self._service.list_files(client_id, client_name, second_client_name, s3_folder)

    def initialize_client_folders(self, client_id, client_name, second_client_name=None):
        return self._service.initialize_client_folders(client_id, client_name, second_client_name)


class OneDriveStorageAdapter(StorageAdapter):
    """Microsoft OneDrive storage adapter - placeholder for future implementation."""

    def is_configured(self) -> bool:
        return False

    def upload_file(self, file_obj, client_id, client_name, category, filename,
                    content_type=None, second_client_name=None, s3_folder=None):
        raise NotImplementedError("OneDrive adapter is not yet implemented. Use S3 or Local storage.")

    def get_file_content(self, storage_path):
        raise NotImplementedError("OneDrive adapter is not yet implemented.")

    def delete_file(self, storage_path):
        raise NotImplementedError("OneDrive adapter is not yet implemented.")

    def file_exists(self, storage_path):
        raise NotImplementedError("OneDrive adapter is not yet implemented.")

    def get_presigned_url(self, storage_path, expiration=3600):
        raise NotImplementedError("OneDrive adapter is not yet implemented.")

    def list_files(self, client_id, client_name, second_client_name=None, s3_folder=None):
        raise NotImplementedError("OneDrive adapter is not yet implemented.")

    def initialize_client_folders(self, client_id, client_name, second_client_name=None):
        raise NotImplementedError("OneDrive adapter is not yet implemented.")


# Module-level singleton cache
_adapter_instance: Optional[StorageAdapter] = None
_adapter_provider: Optional[str] = None


async def get_storage_adapter() -> StorageAdapter:
    """
    Factory function: returns the storage adapter based on system_settings.
    Caches the adapter instance for performance.
    """
    global _adapter_instance, _adapter_provider

    from services.system_config import get_system_config
    config = await get_system_config()
    provider = (config.storage.provider.value
                if hasattr(config.storage.provider, 'value')
                else str(config.storage.provider))

    if _adapter_instance and _adapter_provider == provider:
        return _adapter_instance

    if provider == "aws_s3":
        adapter = S3StorageAdapter()
    elif provider == "local":
        adapter = LocalStorageAdapter()
    elif provider == "onedrive":
        adapter = OneDriveStorageAdapter()
    else:
        # Default to local if no provider configured
        logger.warning(f"Unknown storage provider '{provider}', falling back to Local")
        adapter = LocalStorageAdapter()

    _adapter_instance = adapter
    _adapter_provider = provider
    return adapter


def invalidate_storage_cache():
    """Invalidate the cached adapter (call after config changes)."""
    global _adapter_instance, _adapter_provider
    _adapter_instance = None
    _adapter_provider = None
