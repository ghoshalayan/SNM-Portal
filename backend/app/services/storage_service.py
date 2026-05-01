from app.core.config import settings


def get_storage_service():
    """Factory: returns LocalStorageService or AzureBlobService based on config."""
    if settings.FILE_STORAGE_MODE == "azure_blob":
        from app.services.azure_blob_service import AzureBlobService
        return AzureBlobService()
    else:
        from app.services.local_storage_service import LocalStorageService
        return LocalStorageService()


storage_service = get_storage_service()
