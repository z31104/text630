"""Persistent storage for member photos used by Cloud Run."""

import os


BUCKET_NAME = os.getenv("MEMBER_IMAGE_BUCKET", "").strip()
OBJECT_PREFIX = os.getenv("MEMBER_IMAGE_PREFIX", "member_images").strip("/")


def _blob_name(filename):
    safe_name = os.path.basename(str(filename).replace("\\", "/"))
    if not safe_name:
        raise ValueError("Invalid member image filename")
    return f"{OBJECT_PREFIX}/{safe_name}" if OBJECT_PREFIX else safe_name


def _bucket():
    if not BUCKET_NAME:
        return None
    from google.cloud import storage
    return storage.Client().bucket(BUCKET_NAME)


def upload_member_image(local_path):
    """Mirror a validated local photo to persistent storage."""
    bucket = _bucket()
    if bucket is None:
        return False
    content_type = "image/png" if str(local_path).lower().endswith(".png") else "image/jpeg"
    bucket.blob(_blob_name(local_path)).upload_from_filename(
        local_path,
        content_type=content_type,
    )
    return True


def download_member_image(filename):
    """Return (bytes, content_type), or None when the object is absent."""
    bucket = _bucket()
    if bucket is None:
        return None
    blob = bucket.blob(_blob_name(filename))
    if not blob.exists():
        return None
    return blob.download_as_bytes(), (blob.content_type or "image/jpeg")


def delete_member_image(filename):
    bucket = _bucket()
    if bucket is None:
        return False
    blob = bucket.blob(_blob_name(filename))
    if blob.exists():
        blob.delete()
    return True
