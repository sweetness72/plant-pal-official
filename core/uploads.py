"""
User-uploaded plant photos.

Small, deliberately boring piece of code: accept an UploadFile, normalise
to JPEG, resize to a sensible max, and save under ``data/uploads/``.
The saved path (``/uploads/<name>.jpg``) is returned as a site path so
callers can drop it straight into ``plant.image_override``.

Nothing here is web-facing — callers (routes) are responsible for
permission checks and for mounting the ``uploads`` directory as a
StaticFiles route.
"""

from __future__ import annotations

import io
import logging
import uuid
from pathlib import Path
from typing import BinaryIO

from PIL import Image, UnidentifiedImageError

from core.db.connection import DATA_DIR

logger = logging.getLogger(__name__)

# Keep these in sync with the ``accept`` attribute on the upload input.
# PIL silently handles a lot more; this whitelist is about what we
# promise to the user, not what we can technically decode.
_ALLOWED_CONTENT_TYPES = frozenset(
    {
        "image/jpeg",
        "image/pjpeg",
        "image/png",
        "image/webp",
        "image/gif",
        "image/heic",
        "image/heif",
    }
)

# 10 MiB is plenty for a phone photo after Pillow's resize. Anything
# bigger is either a raw DSLR shot or someone uploading the wrong file.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

# Store at 1024 px on the long side. The UI renders at ~400 px max
# today, so this leaves headroom for a future bigger hero view.
_MAX_LONG_EDGE_PX = 1024

_UPLOAD_DIRNAME = "uploads"


class PhotoRejected(ValueError):
    """The uploaded blob failed validation (too big, wrong type, corrupt)."""


def _uploads_dir() -> Path:
    d = Path(DATA_DIR) / _UPLOAD_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_plant_photo(
    stream: BinaryIO,
    content_type: str | None,
    *,
    max_bytes: int = MAX_UPLOAD_BYTES,
) -> str:
    """Persist ``stream`` as a resized JPEG. Return site-path ``/uploads/<id>.jpg``.

    Validation rules (in order):

    - ``content_type`` must be in the whitelist (when provided).
    - The underlying bytes must be <= ``max_bytes``.
    - Pillow must recognise the payload as an image.

    A ``PhotoRejected`` is raised for any validation failure. We never
    trust the caller's declared content type — Pillow decodes the actual
    bytes and ``Image.verify``/``load`` is the authoritative gate.
    """
    declared = (content_type or "").lower().strip()
    if declared and declared not in _ALLOWED_CONTENT_TYPES:
        raise PhotoRejected(f"Unsupported image type: {declared}")

    raw = stream.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise PhotoRejected(f"Photo too large ({len(raw)} bytes; max {max_bytes}).")
    if not raw:
        raise PhotoRejected("Empty upload.")

    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise PhotoRejected("Could not decode uploaded image.") from exc

    # RGBA / P / CMYK → RGB so JPEG encoding doesn't fail. Alpha is
    # flattened onto a white backdrop; that's correct for our UI because
    # cards sit on light surfaces.
    if img.mode in ("RGBA", "LA", "P"):
        rgba = img.convert("RGBA")
        bg = Image.new("RGB", rgba.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.split()[-1])
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")

    img.thumbnail((_MAX_LONG_EDGE_PX, _MAX_LONG_EDGE_PX), Image.Resampling.LANCZOS)

    out_name = f"{uuid.uuid4().hex}.jpg"
    out_path = _uploads_dir() / out_name
    img.save(out_path, format="JPEG", quality=85, optimize=True, progressive=True)
    logger.info("Saved plant photo: %s (%d bytes)", out_path, out_path.stat().st_size)
    return f"/uploads/{out_name}"


__all__ = ["save_plant_photo", "PhotoRejected", "MAX_UPLOAD_BYTES"]
