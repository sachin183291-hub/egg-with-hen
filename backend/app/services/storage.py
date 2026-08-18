"""
File storage service with pluggable backends.
Backends: local (default) | supabase
"""
import os
import hashlib
import uuid
import shutil
import mimetypes
from pathlib import Path
from typing import Optional, Tuple
# pyrefly: ignore [missing-import]
from fastapi import UploadFile, HTTPException

from app.config import settings


# ─── Validators ───────────────────────────────────────────────────────────────

MAX_FILE_SIZE = settings.MAX_FILE_SIZE_MB * 1024 * 1024  # bytes
ALLOWED_MIME_TYPES = settings.allowed_mime_types_list
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def validate_upload(file: UploadFile) -> None:
    """Validate MIME type and extension. Raise HTTPException on failure."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file extension. Allowed: {list(ALLOWED_EXTENSIONS)}",
        )
    # Normalise content_type – some browsers send 'image/jpg' or empty string
    content_type = (file.content_type or "").lower()
    if not content_type or content_type not in ALLOWED_MIME_TYPES:
        # Fall back: infer from extension
        ext_to_mime = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
        }
        inferred = ext_to_mime.get(suffix)
        if inferred:
            file.content_type = inferred  # patch so downstream code sees correct type
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type '{content_type}'. Allowed: {ALLOWED_MIME_TYPES}",
            )


async def read_and_validate_content(file: UploadFile) -> bytes:
    """Read file content and validate size. Returns raw bytes."""
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size: {settings.MAX_FILE_SIZE_MB} MB",
        )
    return content


def compute_sha256(content: bytes) -> str:
    """Compute SHA-256 hash of file content."""
    return hashlib.sha256(content).hexdigest()


# ─── Storage Backends ─────────────────────────────────────────────────────────

class LocalStorageBackend:
    """Store files on the local filesystem."""

    def __init__(self):
        self.base_path = Path(settings.LOCAL_STORAGE_PATH)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def save(self, content: bytes, original_filename: str, subfolder: str = "evidence") -> str:
        """Save file and return relative URL path."""
        suffix = Path(original_filename).suffix.lower()
        unique_name = f"{uuid.uuid4().hex}{suffix}"
        dest_dir = self.base_path / subfolder
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / unique_name
        dest_path.write_bytes(content)
        return f"/uploads/{subfolder}/{unique_name}"

    def delete(self, storage_url: str) -> bool:
        """Delete a file by its storage URL path."""
        try:
            relative = storage_url.lstrip("/uploads/")
            full_path = self.base_path / relative
            if full_path.exists():
                full_path.unlink()
            return True
        except Exception:
            return False

    def get_absolute_path(self, storage_url: str) -> Optional[Path]:
        """Get absolute filesystem path for a storage URL."""
        try:
            relative = storage_url.replace("/uploads/", "", 1)
            full_path = self.base_path / relative
            return full_path if full_path.exists() else None
        except Exception:
            return None


class SupabaseStorageBackend:
    """Supabase Storage backend — swap in by setting STORAGE_BACKEND=supabase."""

    def __init__(self):
        if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
            raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set for supabase storage.")
        # Lazy import
        # pyrefly: ignore [missing-import]
        from supabase import create_client
        self.client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        self.bucket = settings.SUPABASE_BUCKET

    def save(self, content: bytes, original_filename: str, subfolder: str = "evidence") -> str:
        suffix = Path(original_filename).suffix.lower()
        unique_name = f"{subfolder}/{uuid.uuid4().hex}{suffix}"
        mime = mimetypes.guess_type(original_filename)[0] or "image/jpeg"
        self.client.storage.from_(self.bucket).upload(unique_name, content, {"content-type": mime})
        public_url = self.client.storage.from_(self.bucket).get_public_url(unique_name)
        return public_url

    def delete(self, storage_url: str) -> bool:
        try:
            path = storage_url.split(f"{self.bucket}/")[-1]
            self.client.storage.from_(self.bucket).remove([path])
            return True
        except Exception:
            return False


# ─── Factory ──────────────────────────────────────────────────────────────────

def get_storage_backend():
    """Return the configured storage backend instance."""
    backend = settings.STORAGE_BACKEND.lower()
    if backend == "supabase":
        return SupabaseStorageBackend()
    return LocalStorageBackend()


storage = get_storage_backend()
