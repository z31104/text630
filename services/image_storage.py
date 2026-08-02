import mimetypes
import os
import threading
from urllib.parse import urlparse

try:
    from google.cloud import storage
    from google.api_core.exceptions import NotFound
except Exception:
    storage = None
    NotFound = ()


MEMBER_IMAGE_BUCKET = os.getenv(
    "MEMBER_IMAGE_BUCKET",
    "",
).strip()
MEMBER_IMAGE_PREFIX = (
    os.getenv("MEMBER_IMAGE_PREFIX", "member_images")
    .strip()
    .strip("/")
)

_storage_client = None
_storage_client_lock = threading.Lock()


def cloud_storage_enabled():
    return bool(MEMBER_IMAGE_BUCKET)


def _get_storage_client():
    global _storage_client

    if storage is None:
        raise RuntimeError(
            "已設定 MEMBER_IMAGE_BUCKET，"
            "但尚未安裝 google-cloud-storage"
        )

    if _storage_client is None:
        with _storage_client_lock:
            if _storage_client is None:
                _storage_client = storage.Client()

    return _storage_client


def _build_object_name(filename):
    safe_filename = os.path.basename(str(filename))
    if not safe_filename:
        raise ValueError("會員照片檔名不可為空")

    if MEMBER_IMAGE_PREFIX:
        return f"{MEMBER_IMAGE_PREFIX}/{safe_filename}"

    return safe_filename


def build_gcs_uri(bucket_name, object_name):
    return f"gs://{bucket_name}/{object_name.lstrip('/')}"


def parse_gcs_uri(image_path):
    value = str(image_path or "").strip()
    if not value.startswith("gs://"):
        return None

    remainder = value[5:]
    bucket_name, separator, object_name = remainder.partition("/")

    if not separator or not bucket_name or not object_name:
        return None

    return bucket_name, object_name


def parse_google_storage_url(image_path):
    value = str(image_path or "").strip()
    parsed = urlparse(value)

    if parsed.scheme not in {"http", "https"}:
        return None

    if parsed.netloc == "storage.googleapis.com":
        bucket_name, separator, object_name = (
            parsed.path.lstrip("/").partition("/")
        )
        if separator and bucket_name and object_name:
            return bucket_name, object_name

    suffix = ".storage.googleapis.com"
    if parsed.netloc.endswith(suffix):
        bucket_name = parsed.netloc[:-len(suffix)]
        object_name = parsed.path.lstrip("/")
        if bucket_name and object_name:
            return bucket_name, object_name

    return None


def persist_member_image(
    local_image_path,
    filename,
    content_type=None,
):
    """
    正式環境設定 bucket 時上傳至 Cloud Storage。
    本機未設定 bucket 時維持既有本機檔案行為。
    """
    if not cloud_storage_enabled():
        return local_image_path

    object_name = _build_object_name(filename)
    client = _get_storage_client()
    blob = client.bucket(MEMBER_IMAGE_BUCKET).blob(object_name)
    blob.upload_from_filename(
        local_image_path,
        content_type=content_type,
        if_generation_match=0,
    )

    return build_gcs_uri(
        MEMBER_IMAGE_BUCKET,
        object_name,
    )


def _cloud_reference(image_path):
    return (
        parse_gcs_uri(image_path)
        or parse_google_storage_url(image_path)
    )


def read_member_image(image_path):
    cloud_reference = _cloud_reference(image_path)
    if cloud_reference:
        bucket_name, object_name = cloud_reference
        client = _get_storage_client()
        blob = client.bucket(bucket_name).blob(object_name)
        content = blob.download_as_bytes()
        content_type = (
            blob.content_type
            or mimetypes.guess_type(object_name)[0]
            or "application/octet-stream"
        )
        return content, content_type

    if image_path and os.path.isfile(str(image_path)):
        content_type = (
            mimetypes.guess_type(str(image_path))[0]
            or "application/octet-stream"
        )
        with open(image_path, "rb") as image_file:
            return image_file.read(), content_type

    return None


def delete_member_image(image_path, local_roots=()):
    """
    刪除 Cloud Storage 物件或受允許目錄內的本機照片。

    找不到檔案視為已刪除，讓後台刪會員可重複安全執行。
    """
    cloud_reference = _cloud_reference(image_path)
    if cloud_reference:
        bucket_name, object_name = cloud_reference
        client = _get_storage_client()
        blob = client.bucket(bucket_name).blob(object_name)

        try:
            blob.delete()
        except NotFound:
            pass

        return True

    if not image_path:
        return False

    local_image_path = str(image_path)
    parsed_url = urlparse(local_image_path)

    # 舊版 Cloud Run 會把本機照片存成
    # https://服務網址/member_images/檔名。
    # 若檔案仍在目前執行個體，刪除會員時一併清除。
    if (
        parsed_url.scheme in {"http", "https"}
        and "/member_images/" in parsed_url.path
        and local_roots
    ):
        local_image_path = os.path.join(
            str(local_roots[0]),
            os.path.basename(parsed_url.path),
        )

    absolute_path = os.path.abspath(local_image_path)
    try:
        allowed = any(
            os.path.commonpath(
                [absolute_path, os.path.abspath(root)]
            )
            == os.path.abspath(root)
            for root in local_roots
        )
    except (OSError, TypeError, ValueError):
        allowed = False

    if not allowed:
        return False

    try:
        os.remove(absolute_path)
    except FileNotFoundError:
        pass

    return True
