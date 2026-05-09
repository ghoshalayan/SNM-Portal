import os
import uuid
from pathlib import Path

from app.core.config import settings


class LocalStorageService:
    def __init__(self):
        self.base_path = Path(settings.LOCAL_STORAGE_PATH)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def upload_file(self, file_data: bytes, original_filename: str, content_type: str = None) -> dict:
        ext = original_filename.rsplit(".", 1)[-1] if "." in original_filename else ""
        stored_name = f"{uuid.uuid4().hex}.{ext}" if ext else uuid.uuid4().hex

        file_path = self.base_path / stored_name
        file_path.write_bytes(file_data)

        return {
            "blob_name": stored_name,
            "url": f"/local-files/{stored_name}",
            "file_name": original_filename,
        }

    def _resolve_inside_base(self, blob_name: str) -> Path:
        """Resolve `blob_name` under `base_path` and refuse anything that
        escapes it. Defends against a tampered `Asset.fileUrl` containing
        `../` or an absolute path — uploads only ever write UUID names, but
        downloads trust the DB-stored URL, so this is the choke point.
        """
        base = self.base_path.resolve()
        candidate = (self.base_path / blob_name).resolve()
        try:
            candidate.relative_to(base)
        except ValueError:
            raise FileNotFoundError(f"File not found: {blob_name}")
        return candidate

    def download_file(self, blob_name: str) -> bytes:
        file_path = self._resolve_inside_base(blob_name)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {blob_name}")
        return file_path.read_bytes()

    def delete_file(self, blob_name: str) -> None:
        file_path = self._resolve_inside_base(blob_name)
        if file_path.exists():
            os.remove(file_path)

    def generate_sas_url(self, blob_name: str, expiry_hours: int = 1) -> str:
        return f"/local-files/{blob_name}"
