from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions, ContentSettings
from datetime import datetime, timedelta, timezone
from typing import Optional
import uuid

from app.core.config import settings


class AzureBlobService:
    def __init__(self):
        self.connection_string = settings.AZURE_BLOB_CONNECTION_STRING
        self.container_name = settings.AZURE_BLOB_CONTAINER
        self.directory = settings.AZURE_BLOB_DIRECTORY
        self._client: Optional[BlobServiceClient] = None

    @property
    def client(self) -> BlobServiceClient:
        if not self._client and self.connection_string:
            self._client = BlobServiceClient.from_connection_string(self.connection_string)
        return self._client

    def _blob_path(self, blob_name: str) -> str:
        """Prefix blob name with directory if configured."""
        if self.directory:
            return f"{self.directory}/{blob_name}"
        return blob_name

    def upload_file(self, file_data: bytes, original_filename: str, content_type: str = None) -> dict:
        ext = original_filename.rsplit(".", 1)[-1] if "." in original_filename else ""
        blob_name = f"{uuid.uuid4().hex}.{ext}" if ext else uuid.uuid4().hex
        full_path = self._blob_path(blob_name)

        blob_client = self.client.get_blob_client(
            container=self.container_name,
            blob=full_path,
        )
        blob_client.upload_blob(
            file_data,
            content_settings=ContentSettings(content_type=content_type) if content_type else None,
            overwrite=True,
        )

        return {
            "blob_name": full_path,
            "url": blob_client.url,
            "file_name": original_filename,
        }

    def download_file(self, blob_name: str) -> bytes:
        blob_client = self.client.get_blob_client(
            container=self.container_name,
            blob=blob_name,
        )
        return blob_client.download_blob().readall()

    def delete_file(self, blob_name: str) -> None:
        blob_client = self.client.get_blob_client(
            container=self.container_name,
            blob=blob_name,
        )
        blob_client.delete_blob()

    def generate_sas_url(self, blob_name: str, expiry_hours: int = 1) -> str:
        blob_client = self.client.get_blob_client(
            container=self.container_name,
            blob=blob_name,
        )
        sas_token = generate_blob_sas(
            account_name=self.client.account_name,
            container_name=self.container_name,
            blob_name=blob_name,
            account_key=self.client.credential.account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.now(timezone.utc) + timedelta(hours=expiry_hours),
        )
        return f"{blob_client.url}?{sas_token}"
