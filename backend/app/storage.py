"""Slip images live in a private Supabase Storage bucket.

Two rules this module enforces:
  1. Nothing is ever uploaded at original size or with EXIF intact — slips are
     downscaled and re-encoded, which strips GPS/device metadata as a side
     effect and keeps us far away from the 1 GB free-tier ceiling.
  2. The bucket is private. We store the object *path* in Postgres and mint a
     short-lived signed URL on demand; no durable public link ever exists.
"""

import io
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import HTTPException, status
from PIL import Image, ImageOps

from .config import settings

_ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic"}
MAX_UPLOAD_BYTES = 12 * 1024 * 1024


class StorageDisabled(RuntimeError):
    pass


def _require_storage() -> None:
    if not settings.storage_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ยังไม่ได้ตั้งค่า Supabase Storage (SUPABASE_URL / SUPABASE_SERVICE_KEY)",
        )


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.supabase_service_key}",
        "apikey": settings.supabase_service_key,
    }


def process_image(raw: bytes) -> bytes:
    """Downscale, fix orientation, drop metadata, re-encode as JPEG."""
    try:
        with Image.open(io.BytesIO(raw)) as img:
            # Applies the EXIF orientation tag, then we discard EXIF entirely.
            img = ImageOps.exif_transpose(img)
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            img.thumbnail(
                (settings.slip_max_edge_px, settings.slip_max_edge_px),
                Image.LANCZOS,
            )
            out = io.BytesIO()
            img.save(
                out,
                format="JPEG",
                quality=settings.slip_jpeg_quality,
                optimize=True,
                progressive=True,
            )
            return out.getvalue()
    except Exception as exc:  # noqa: BLE001 - any decode failure is a 400
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"อ่านไฟล์รูปไม่ได้: {exc}",
        ) from exc


def validate_upload(content_type: str | None, size: int) -> None:
    if size > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="ไฟล์ใหญ่เกิน 12MB",
        )
    if content_type and content_type.lower() not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"รองรับเฉพาะไฟล์รูป ({', '.join(sorted(_ALLOWED_CONTENT_TYPES))})",
        )


def build_object_path() -> str:
    """Date-partitioned, random filename — no user or amount leaks via the path."""
    now = datetime.now(timezone.utc)
    return f"{now:%Y/%m}/{uuid.uuid4().hex}.jpg"


async def upload_slip(jpeg_bytes: bytes, object_path: str) -> str:
    _require_storage()
    url = (
        f"{settings.supabase_url.rstrip('/')}"
        f"/storage/v1/object/{settings.supabase_bucket}/{object_path}"
    )
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            url,
            headers={
                **_headers(),
                "Content-Type": "image/jpeg",
                "x-upsert": "false",
                "cache-control": "max-age=31536000",
            },
            content=jpeg_bytes,
        )
    if resp.status_code not in (200, 201):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"อัปโหลดสลิปไม่สำเร็จ ({resp.status_code}): {resp.text[:200]}",
        )
    return object_path


async def create_signed_url(object_path: str, expires_in: int | None = None) -> str:
    _require_storage()
    expires_in = expires_in or settings.signed_url_ttl_seconds
    base = settings.supabase_url.rstrip("/")
    url = f"{base}/storage/v1/object/sign/{settings.supabase_bucket}/{object_path}"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            url,
            headers={**_headers(), "Content-Type": "application/json"},
            json={"expiresIn": expires_in},
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"สร้างลิงก์ดูสลิปไม่สำเร็จ ({resp.status_code})",
        )
    # Supabase returns a path like "/object/sign/slips/...?token=..."
    signed = resp.json().get("signedURL") or resp.json().get("signedUrl")
    if not signed:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Supabase ไม่ได้ส่ง signedURL กลับมา",
        )
    return f"{base}/storage/v1{signed}" if signed.startswith("/") else signed


async def delete_slip(object_path: str) -> None:
    """Best-effort. A leftover object is cheaper than a failed delete request."""
    if not settings.storage_enabled:
        return
    url = (
        f"{settings.supabase_url.rstrip('/')}"
        f"/storage/v1/object/{settings.supabase_bucket}/{object_path}"
    )
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            await client.delete(url, headers=_headers())
    except httpx.HTTPError:
        pass
