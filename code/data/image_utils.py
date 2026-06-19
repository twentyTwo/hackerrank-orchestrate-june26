import base64
import io
from pathlib import Path

from PIL import Image


def load_and_encode(image_path: Path, max_px: int = 1024) -> tuple[bytes, str]:
    """Return (resized_bytes, media_type) for a single image."""
    img = Image.open(image_path)
    img = _resize(img, max_px)
    media_type = _media_type(img.format or "JPEG")
    fmt = "JPEG" if media_type == "image/jpeg" else "PNG"
    buf = io.BytesIO()
    img.save(buf, format=fmt, quality=85)
    return buf.getvalue(), media_type


def to_base64(image_bytes: bytes) -> str:
    return base64.standard_b64encode(image_bytes).decode()


def _resize(img: Image.Image, max_px: int) -> Image.Image:
    w, h = img.size
    if max(w, h) <= max_px:
        return img.convert("RGB")
    ratio = max_px / max(w, h)
    new_w, new_h = int(w * ratio), int(h * ratio)
    return img.resize((new_w, new_h), Image.LANCZOS).convert("RGB")


def _media_type(fmt: str) -> str:
    fmt = fmt.upper()
    if fmt in ("JPG", "JPEG"):
        return "image/jpeg"
    if fmt == "PNG":
        return "image/png"
    if fmt == "WEBP":
        return "image/webp"
    if fmt == "GIF":
        return "image/gif"
    return "image/jpeg"
