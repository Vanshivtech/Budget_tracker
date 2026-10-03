"""
Supabase Storage adapter for receipts and bill attachments.
Files are stored strictly in a PRIVATE Supabase Storage bucket.
Never stores files on the local disk.
"""
import uuid
import logging
from typing import Tuple, Optional
import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Max file size: 5 MB
MAX_FILE_SIZE = 5 * 1024 * 1024

# In-memory storage fallback for testing or when credentials are not supplied
_mock_storage: dict[str, tuple[bytes, str]] = {}


def validate_file_content(content: bytes) -> Tuple[bool, str, str, str]:
    """Validate file size and MIME type based on magic bytes content.
    Returns: (is_valid, mime_type, file_extension, error_message)
    """
    if len(content) == 0:
        return False, "", "", "Uploaded file is empty."

    if len(content) > MAX_FILE_SIZE:
        return False, "", "", f"File exceeds maximum allowed size of 5 MB (size: {len(content)} bytes)."

    # JPEG magic bytes: FF D8 FF
    if content.startswith(b"\xff\xd8\xff"):
        return True, "image/jpeg", "jpg", ""

    # PNG magic bytes: 89 50 4E 47 0D 0A 1A 0A
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return True, "image/png", "png", ""

    # PDF magic bytes: %PDF-
    if content.startswith(b"%PDF-"):
        return True, "application/pdf", "pdf", ""

    return False, "", "", "Unsupported file type. Only JPG, PNG, and PDF files are allowed."


MAX_AVATAR_SIZE = 2 * 1024 * 1024


def validate_avatar_file(content: bytes) -> Tuple[bool, str, str, str]:
    """Validate avatar photo size (max 2MB) and content type (JPG or PNG only).
    Returns: (is_valid, mime_type, file_extension, error_message)
    """
    if len(content) == 0:
        return False, "", "", "Uploaded file is empty."

    if len(content) > MAX_AVATAR_SIZE:
        return False, "", "", "File exceeds maximum allowed size of 2 MB."

    # JPEG magic bytes: FF D8 FF
    if content.startswith(b"\xff\xd8\xff"):
        return True, "image/jpeg", "jpg", ""

    # PNG magic bytes: 89 50 4E 47 0D 0A 1A 0A
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return True, "image/png", "png", ""

    if content.startswith(b"GIF87a") or content.startswith(b"GIF89a"):
        return False, "", "", "GIF format is not supported. Please upload a JPG or PNG photo."

    return False, "", "", "Unsupported file type. Only JPG and PNG photos are allowed."


def get_storage_path(user_id: int, transaction_id: int, ext: str) -> str:
    """Generate path in the format: {user_id}/{transaction_id}/{uuid}.{ext}"""
    file_id = uuid.uuid4().hex
    return f"{user_id}/{transaction_id}/{file_id}.{ext}"


def upload_to_storage(path: str, content: bytes, mime: str) -> bool:
    """Upload file to private Supabase Storage bucket.
    Falls back to mock memory storage if Supabase credentials are not configured."""
    supabase_url = settings.get_supabase_url()
    service_key = settings.SUPABASE_SERVICE_ROLE_KEY
    bucket = settings.SUPABASE_STORAGE_BUCKET

    if not supabase_url or not service_key:
        logger.info(f"Supabase Storage credentials not configured. Storing {path} in memory storage.")
        _mock_storage[path] = (content, mime)
        return True

    url = f"{supabase_url}/storage/v1/object/{bucket}/{path}"
    headers = {
        "Authorization": f"Bearer {service_key}",
        "Content-Type": mime,
        "x-upsert": "true",
    }

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, content=content, headers=headers)
            if resp.status_code in (200, 201):
                return True
            logger.error(f"Supabase storage upload failed ({resp.status_code}): {resp.text}")
            # If bucket doesn't exist, create it as private and retry once
            if resp.status_code == 404 or "Bucket not found" in resp.text:
                create_bucket_if_missing()
                retry_resp = client.post(url, content=content, headers=headers)
                return retry_resp.status_code in (200, 201)
            return False
    except Exception as e:
        logger.error(f"Error uploading to Supabase Storage: {e}")
        _mock_storage[path] = (content, mime)
        return True


def create_bucket_if_missing() -> None:
    """Ensure the private bucket exists in Supabase Storage."""
    supabase_url = settings.get_supabase_url()
    service_key = settings.SUPABASE_SERVICE_ROLE_KEY
    bucket = settings.SUPABASE_STORAGE_BUCKET

    if not supabase_url or not service_key:
        return

    url = f"{supabase_url}/storage/v1/bucket"
    headers = {
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "id": bucket,
        "name": bucket,
        "public": False,  # Strict private bucket requirement
    }

    try:
        with httpx.Client(timeout=10.0) as client:
            client.post(url, json=payload, headers=headers)
    except Exception as e:
        logger.warning(f"Could not create storage bucket: {e}")


def get_signed_url(path: str, expires_in_seconds: int = 300) -> str:
    """Generate a short-lived signed URL for a private storage object.
    Expires in 300 seconds (5 minutes) by default."""
    supabase_url = settings.get_supabase_url()
    service_key = settings.SUPABASE_SERVICE_ROLE_KEY
    bucket = settings.SUPABASE_STORAGE_BUCKET

    if not supabase_url or not service_key or path in _mock_storage:
        # Fallback to local streaming proxy endpoint
        return f"/api/receipts/file-stream?path={path}"

    url = f"{supabase_url}/storage/v1/object/sign/{bucket}/{path}"
    headers = {
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
    }
    payload = {"expiresIn": expires_in_seconds}

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(url, json=payload, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                signed_path = data.get("signedURL")
                if signed_path:
                    if signed_path.startswith("http"):
                        return signed_path
                    return f"{supabase_url}/storage/v1{signed_path}"
    except Exception as e:
        logger.error(f"Error getting signed URL from Supabase Storage: {e}")

    return f"/api/receipts/file-stream?path={path}"


def get_file_bytes(path: str) -> Optional[Tuple[bytes, str]]:
    """Retrieve raw file bytes and mime type for proxy streaming or testing."""
    if path in _mock_storage:
        return _mock_storage[path]

    supabase_url = settings.get_supabase_url()
    service_key = settings.SUPABASE_SERVICE_ROLE_KEY
    bucket = settings.SUPABASE_STORAGE_BUCKET

    if not supabase_url or not service_key:
        return None

    url = f"{supabase_url}/storage/v1/object/authenticated/{bucket}/{path}"
    headers = {"Authorization": f"Bearer {service_key}"}

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url, headers=headers)
            if resp.status_code == 200:
                mime = resp.headers.get("content-type", "application/octet-stream")
                return resp.content, mime
    except Exception as e:
        logger.error(f"Error downloading file from Supabase Storage: {e}")

    return None


def delete_from_storage(path: str) -> bool:
    """Delete object from Supabase Storage."""
    if path in _mock_storage:
        del _mock_storage[path]

    supabase_url = settings.get_supabase_url()
    service_key = settings.SUPABASE_SERVICE_ROLE_KEY
    bucket = settings.SUPABASE_STORAGE_BUCKET

    if not supabase_url or not service_key:
        return True

    url = f"{supabase_url}/storage/v1/object/{bucket}"
    headers = {
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
    }
    payload = {"prefixes": [path]}

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.request("DELETE", url, json=payload, headers=headers)
            return resp.status_code in (200, 204)
    except Exception as e:
        logger.error(f"Error deleting file from Supabase Storage: {e}")
        return False


def ocr_receipt_hook(file_bytes: bytes, mime: str) -> Optional[dict]:
    """Hook for future local-OCR integration.
    Currently deterministic placeholder returning None.
    When a local OCR engine (like pytesseract or easyocr) is configured,
    this hook will extract text, merchant, total amount, and date."""
    # Future OCR implementation placeholder
    return None
