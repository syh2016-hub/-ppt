"""Small, dependency-light helpers shared by the API, AI and export layers."""
from __future__ import annotations

import hashlib
import html
import io
import ipaddress
import json
import math
import os
import re
import socket
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageOps

from .config import CACHE_DIR

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
IMAGE_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6",
}
MAX_DOWNLOAD_BYTES = 14 * 1024 * 1024


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def local_now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def json_loads(text: str | None, default: Any = None) -> Any:
    if not text:
        return default
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return default


def clean_text(value: Any, limit: int = 4000) -> str:
    if value is None:
        return ""
    text = str(value).replace("\x00", "").strip()
    return text[:limit]


def clean_multiline(value: Any, limit: int = 12000) -> str:
    text = clean_text(value, limit)
    return re.sub(r"\r\n?", "\n", text)


def clamp(value: Any, minimum: int, maximum: int, default: int | None = None) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default if default is not None else minimum
    return max(minimum, min(maximum, number))


def slugify(value: str, fallback: str = "presentation") -> str:
    value = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "-", value or "").strip("-")
    return (value or fallback)[:60]


def human_size(size: int | None) -> str:
    if not size:
        return "—"
    size = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def is_public_http_url(url: str) -> bool:
    """Reject non-HTTP and private-network URLs to reduce SSRF risk."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    if parsed.username or parsed.password:
        return False
    host = parsed.hostname.strip().lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        return False
    if host.endswith(".internal") or host.endswith(".lan"):
        return False
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError:
        return False
    for addr in addresses:
        try:
            ip = ipaddress.ip_address(addr[4][0])
        except ValueError:
            return False
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return False
    return True


def validate_download_url(url: str) -> bool:
    """Bing image URLs sometimes carry a trailing !/fh/... suffix; strip it."""
    if not url:
        return False
    url = url.strip()
    if not re.match(r"^https?://", url, re.I):
        return False
    return is_public_http_url(url)


def normalize_image_url(url: str) -> str:
    url = url.strip()
    # 699pic and similar CDNs append non-URL resizing fragments.
    if "!/" in url:
        url = url.split("!/", 1)[0]
    return url


def request_image(url: str, timeout: int = 12) -> Image.Image:
    """Download and decode an image with size/content validation."""
    if not validate_download_url(url):
        raise ValueError("图片地址不安全或不可访问")
    with requests.get(
        normalize_image_url(url),
        headers=IMAGE_HEADERS,
        timeout=timeout,
        stream=True,
        allow_redirects=True,
    ) as response:
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "").lower()
        if content_type and not content_type.startswith("image/"):
            raise ValueError("返回内容不是图片")
        buffer = bytearray()
        for chunk in response.iter_content(64 * 1024):
            if not chunk:
                continue
            buffer.extend(chunk)
            if len(buffer) > MAX_DOWNLOAD_BYTES:
                raise ValueError("图片体积过大")
        image = Image.open(io.BytesIO(bytes(buffer)))
        image.load()
        return image


def cover_image(image: Image.Image, size: tuple[int, int] = (1600, 900)) -> Image.Image:
    """Center-crop an image to a 16:9 canvas."""
    desired_w, desired_h = size
    image = ImageOps.exif_transpose(image).convert("RGB")
    src_w, src_h = image.size
    scale = max(desired_w / src_w, desired_h / src_h)
    new_w, new_h = max(1, round(src_w * scale)), max(1, round(src_h * scale))
    image = image.resize((new_w, new_h), Image.Resampling.LANCZOS)
    left = (new_w - desired_w) // 2
    top = (new_h - desired_h) // 2
    return image.crop((left, top, left + desired_w, top + desired_h))


def save_online_thumbnail(url: str, key: str) -> str | None:
    """Cache a remote image as a local thumbnail and return its public path."""
    target = CACHE_DIR / "online" / f"{key}.jpg"
    if target.exists() and target.stat().st_size > 512:
        return f"/api/templates/online/thumb/{key}"
    try:
        image = request_image(url, timeout=15)
        image = cover_image(image, (640, 360))
        target.parent.mkdir(parents=True, exist_ok=True)
        image.save(target, "JPEG", quality=82, optimize=True)
        return f"/api/templates/online/thumb/{key}"
    except Exception:
        return None


def save_background_image(url: str, target: Path) -> Path | None:
    try:
        image = request_image(url, timeout=20)
        image = cover_image(image, (1600, 900))
        target.parent.mkdir(parents=True, exist_ok=True)
        image.save(target, "JPEG", quality=90, optimize=True)
        return target
    except Exception:
        return None


def dominant_colors(image: Image.Image, count: int = 4) -> list[str]:
    small = image.copy().convert("RGB")
    small.thumbnail((160, 160))
    quantized = small.quantize(colors=max(3, count))
    palette = quantized.getpalette() or []
    counts = sorted(quantized.getcolors() or [], reverse=True)
    colors: list[str] = []
    for _, index in counts[:count]:
        base = index * 3
        if base + 2 >= len(palette):
            continue
        rgb = tuple(palette[base : base + 3])
        colors.append("#%02X%02X%02X" % rgb)
    return colors


def safe_filename(name: str, fallback: str = "启明演示") -> str:
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', "", name or "").strip(" .")
    return (name or fallback)[:60]


def image_to_png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def make_gradient(
    size: tuple[int, int],
    top_left: str,
    bottom_right: str,
    angle: float = 135,
) -> Image.Image:
    """Generate a smooth two-colour linear gradient."""
    width, height = size
    top_left_rgb = hex_to_rgb(top_left)
    bottom_right_rgb = hex_to_rgb(bottom_right)
    base = Image.new("RGB", (max(2, width // 4), max(2, height // 4)))
    pixels = base.load()
    radians = math.radians(angle)
    dx, dy = math.cos(radians), math.sin(radians)
    max_projection = abs(dx) * base.width + abs(dy) * base.height
    for y in range(base.height):
        for x in range(base.width):
            projection = dx * x + dy * y
            if projection < 0:
                projection = 0
            t = min(1.0, projection / max(1.0, max_projection))
            pixels[x, y] = (
                round(top_left_rgb[0] * (1 - t) + bottom_right_rgb[0] * t),
                round(top_left_rgb[1] * (1 - t) + bottom_right_rgb[1] * t),
                round(top_left_rgb[2] * (1 - t) + bottom_right_rgb[2] * t),
            )
    return base.resize((width, height), Image.Resampling.BILINEAR)


def hex_to_rgb(color: str) -> tuple[int, int, int]:
    color = (color or "#000000").lstrip("#")
    if len(color) == 3:
        color = "".join(ch * 2 for ch in color)
    try:
        return tuple(int(color[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]
    except ValueError:
        return (0, 0, 0)


def mix_color(first: str, second: str, amount: float) -> str:
    a, b = hex_to_rgb(first), hex_to_rgb(second)
    amount = max(0.0, min(1.0, amount))
    return "#%02X%02X%02X" % tuple(
        round(a[i] * (1 - amount) + b[i] * amount) for i in range(3)
    )


def relative_luminance(color: str) -> float:
    r, g, b = [channel / 255 for channel in hex_to_rgb(color)]
    values = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in (r, g, b)]
    return 0.2126 * values[0] + 0.7152 * values[1] + 0.0722 * values[2]


def readable_on(background: str, light: str = "#FFFFFF", dark: str = "#121212") -> str:
    return dark if relative_luminance(background) > 0.52 else light


def truncate(text: str, limit: int = 120) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def wait_for_file(path: Path, timeout: float = 3.0) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        if path.exists() and path.stat().st_size > 0:
            return True
        time.sleep(0.08)
    return path.exists() and path.stat().st_size > 0


def parse_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def format_date(value: str | None) -> str:
    if not value:
        return "—"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return value[:16]


def safe_json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def remove_file(path: Path | None) -> None:
    if not path:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def ensure_inside(base: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def generate_avatar_hue(text: str) -> int:
    return int(hash_text(text)[:4], 16) % 360


def image_has_alpha(image: Image.Image) -> bool:
    return image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info)


def rounded_rectangle_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    return mask


def blur_image(image: Image.Image, radius: int = 20) -> Image.Image:
    return image.filter(ImageFilter.GaussianBlur(radius))
