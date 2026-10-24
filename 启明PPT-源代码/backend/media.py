"""Local visual, video, narration and PDF helpers used by the deck generator."""
from __future__ import annotations

import hashlib
import asyncio
import math
import os
import random
import re
import shutil
import subprocess
import tempfile
import time
import wave
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .config import CACHE_DIR, VOICE_DIR
from .voices import (
    DEFAULT_EN_VOICE,
    DEFAULT_ZH_VOICE,
    EDGE_VOICE_IDS,
    get_voice,
    is_english_text,
    normalize_voice,
    voice_for_text,
)
from .utils import (
    cover_image,
    hex_to_rgb,
    save_background_image,
)

try:
    import edge_tts  # type: ignore
except Exception:  # pragma: no cover - optional network voice
    edge_tts = None

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
_FFMPEG_CACHE: str | None = None
_VIDEO_ERROR: str = ""
_PPTX_SOFFICE_CANDIDATES = [
    Path(r"C:\Program Files\LibreOffice\program\soffice.exe"),
    Path(r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"),
]
_POWERPOINT_CANDIDATES = [
    Path(r"C:\Program Files\Microsoft Office\root\Office16\POWERPNT.EXE"),
    Path(r"C:\Program Files (x86)\Microsoft Office\root\Office16\POWERPNT.EXE"),
]


def ffmpeg_path() -> str | None:
    global _FFMPEG_CACHE
    if _FFMPEG_CACHE:
        return _FFMPEG_CACHE
    for candidate in (
        shutil.which("ffmpeg"),
        str(Path(__file__).resolve().parent.parent / "tools" / "ffmpeg.exe"),
    ):
        if candidate and Path(candidate).exists():
            _FFMPEG_CACHE = candidate
            return candidate
    try:
        import imageio_ffmpeg

        path = imageio_ffmpeg.get_ffmpeg_exe()
        if path and Path(path).exists():
            _FFMPEG_CACHE = path
            return path
    except Exception:
        pass
    return None


def _hex_rgb(color: str) -> tuple[int, int, int]:
    return hex_to_rgb(color)


def _radial_layer(size: tuple[int, int], center: tuple[float, float], radius: float, color: str, alpha: int) -> Image.Image:
    width, height = size
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    r, g, b = _hex_rgb(color)
    draw.ellipse(
        (
            int(center[0] - radius),
            int(center[1] - radius),
            int(center[0] + radius),
            int(center[1] + radius),
        ),
        fill=(r, g, b, alpha),
    )
    return layer.filter(ImageFilter.GaussianBlur(max(5, int(radius * 0.42))))


def _gradient(size: tuple[int, int], start: str, end: str, angle: float = 135) -> Image.Image:
    width, height = size
    start_rgb = np.array(_hex_rgb(start), dtype=np.float32)
    end_rgb = np.array(_hex_rgb(end), dtype=np.float32)
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    angle_rad = math.radians(angle)
    projection = math.cos(angle_rad) * xx + math.sin(angle_rad) * yy
    projection -= projection.min()
    projection /= max(1.0, float(projection.max()))
    t = projection[..., None]
    array = start_rgb[None, None, :] * (1 - t) + end_rgb[None, None, :] * t
    return Image.fromarray(np.clip(array, 0, 255).astype(np.uint8), "RGB")


def generate_background_art(
    theme: dict[str, Any],
    path: Path,
    *,
    variant: str = "cover",
    size: tuple[int, int] = (1600, 900),
    cover_image_path: Path | None = None,
) -> Path:
    """Create a rich, watermark-free background from theme tokens."""
    width, height = size
    colors = theme["colors"]
    motif = str(theme.get("motif") or "orbit")
    randomizer = random.Random(f"{theme.get('id')}|{variant}|{width}x{height}")

    if cover_image_path and cover_image_path.exists():
        try:
            base = cover_image(Image.open(cover_image_path), size).convert("RGBA")
            # Dark or light veil keeps text readable without hiding the photo.
            dark = theme.get("is_dark", True)
            veil = _gradient(
                size,
                colors["bg"] if dark else "#FFFFFF",
                colors["bg2"] if dark else colors["bg2"],
                angle=110,
            ).convert("RGBA")
            alpha = 132 if dark else 88
            veil.putalpha(alpha)
            base = Image.alpha_composite(base, veil)
        except Exception:
            cover_image_path = None
    if not cover_image_path or not cover_image_path.exists():
        base = _gradient(size, colors["bg"], colors["bg2"], angle=125).convert("RGBA")

    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    primary = colors["primary"]
    accent = colors["accent"]
    soft = colors["primary_soft"]
    is_dark = bool(theme.get("is_dark"))
    strength = 150 if is_dark else 105

    if motif in {"orbit", "rings"}:
        for index, (x_factor, y_factor, radius_factor, color) in enumerate(
            [
                (0.82, 0.20, 0.36, primary),
                (0.92, 0.76, 0.26, accent),
                (0.62, 0.92, 0.20, soft),
            ]
        ):
            layer = Image.alpha_composite(
                layer,
                _radial_layer(
                    size,
                    (width * x_factor, height * y_factor),
                    width * radius_factor,
                    str(color),
                    strength if index == 0 else max(40, strength - 40),
                ),
            )
        draw = ImageDraw.Draw(layer)
        for index in range(3):
            radius = width * (0.13 + index * 0.075)
            cx = width * 0.80
            cy = height * 0.48
            draw.ellipse(
                (cx - radius, cy - radius, cx + radius, cy + radius),
                outline=(*_hex_rgb(colors["ink"] if not is_dark else "#FFFFFF"), 24 + index * 12),
                width=2,
            )
    elif motif == "grid":
        draw = ImageDraw.Draw(layer)
        step = max(48, width // 18)
        line_color = (*_hex_rgb(colors["ink"] if not is_dark else "#FFFFFF"), 14)
        for x in range(0, width, step):
            draw.line((x, 0, x, height), fill=line_color, width=1)
        for y in range(0, height, step):
            draw.line((0, y, width, y), fill=line_color, width=1)
        layer = Image.alpha_composite(
            layer,
            _radial_layer(size, (width * 0.83, height * 0.25), width * 0.4, primary, strength),
        )
    elif motif == "wave":
        draw = ImageDraw.Draw(layer)
        for index in range(4):
            points = []
            amplitude = height * (0.10 + index * 0.018)
            baseline = height * (0.58 + index * 0.09)
            for x in range(0, width + 20, 20):
                y = baseline + math.sin(x / width * math.pi * 2 + index * 0.9) * amplitude
                points.append((x, y))
            points += [(width, height), (0, height)]
            color = (*_hex_rgb(primary if index % 2 == 0 else accent), 22 if not is_dark else 32)
            draw.polygon(points, fill=color)
        layer = layer.filter(ImageFilter.GaussianBlur(1.2))
    elif motif == "arc":
        draw = ImageDraw.Draw(layer)
        for index in range(5):
            bbox = (
                width * 0.55 - index * 42,
                -height * 0.30 - index * 20,
                width * 1.25 + index * 30,
                height * 0.95 + index * 20,
            )
            draw.arc(
                bbox,
                start=195,
                end=340,
                fill=(*_hex_rgb(primary if index < 2 else accent), 40 if not is_dark else 55),
                width=max(2, 3 + index),
            )
        layer = Image.alpha_composite(
            layer,
            _radial_layer(size, (width * 0.18, height * 0.15), width * 0.25, accent, strength // 2),
        )
    elif motif == "dots":
        draw = ImageDraw.Draw(layer)
        for row in range(9):
            for col in range(14):
                x = width * 0.56 + col * width * 0.028
                y = height * 0.12 + row * height * 0.075
                radius = 1.8 + ((row + col) % 4)
                draw.ellipse(
                    (x - radius, y - radius, x + radius, y + radius),
                    fill=(*_hex_rgb(primary if (row + col) % 7 == 0 else accent), 70),
                )
        layer = Image.alpha_composite(
            layer,
            _radial_layer(size, (width * 0.88, height * 0.72), width * 0.30, primary, strength // 2),
        )
    elif motif == "blocks":
        draw = ImageDraw.Draw(layer)
        blocks = [
            (0.62, 0.10, 0.34, 0.40, accent, 88),
            (0.72, 0.44, 0.24, 0.32, primary, 110),
            (0.54, 0.62, 0.20, 0.20, soft, 120),
        ]
        for x, y, w, h, color, alpha in blocks:
            draw.rectangle(
                (width * x, height * y, width * (x + w), height * (y + h)),
                fill=(*_hex_rgb(color), alpha),
            )
        layer = layer.rotate(-2, resample=Image.Resampling.BICUBIC, expand=False)
    else:
        layer = Image.alpha_composite(
            layer,
            _radial_layer(size, (width * 0.78, height * 0.30), width * 0.34, primary, strength // 2),
        )

    composed = Image.alpha_composite(base, layer)

    # Fine grain, deliberately subtle.
    grain = np.random.default_rng(int(hashlib.sha1(str(path).encode()).hexdigest()[:8], 16)).normal(
        0, 5.2, (height, width, 1)
    )
    array = np.asarray(composed.convert("RGB"), dtype=np.float32) + grain
    composed = Image.fromarray(np.clip(array, 0, 255).astype(np.uint8), "RGB")

    # Soft vignette.
    vignette = Image.new("L", size, 0)
    ImageDraw.Draw(vignette).ellipse(
        (-width * 0.15, -height * 0.22, width * 1.15, height * 1.22),
        fill=255,
    )
    vignette = vignette.filter(ImageFilter.GaussianBlur(width // 14))
    dark = Image.new("RGB", size, _hex_rgb(colors["bg"] if is_dark else "#FFFFFF"))
    composed = Image.composite(composed, dark, vignette)

    path.parent.mkdir(parents=True, exist_ok=True)
    composed.save(path, "JPEG", quality=92, optimize=True)
    return path


def make_overlay(path: Path, size: tuple[int, int], color: str, top_alpha: int, bottom_alpha: int) -> Path:
    """Vertical translucent gradient saved as RGBA PNG for readable text over photos."""
    width, height = size
    rgb = _hex_rgb(color)
    alpha = np.linspace(top_alpha, bottom_alpha, height).astype(np.uint8)[:, None]
    alpha = np.repeat(alpha, width, axis=1)
    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    rgba[..., 0] = rgb[0]
    rgba[..., 1] = rgb[1]
    rgba[..., 2] = rgb[2]
    rgba[..., 3] = alpha
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba, "RGBA").save(path, "PNG")
    return path


def download_background(url: str, target: Path) -> Path | None:
    return save_background_image(url, target)


def generate_motion_video(theme: dict[str, Any], path: Path, *, duration: float = 4.5, fps: int = 15) -> Path | None:
    """Render a short abstract loop and encode it with ffmpeg."""
    ffmpeg = ffmpeg_path()
    if not ffmpeg:
        return None
    colors = theme["colors"]
    width, height = 960, 540
    frames = max(12, int(duration * fps))
    temp_dir = CACHE_DIR / "video_frames" / f"{path.stem}_{int(time.time())}"
    temp_dir.mkdir(parents=True, exist_ok=True)
    start = time.time()
    try:
        base = np.asarray(_gradient((width, height), colors["bg"], colors["bg2"], angle=120), dtype=np.float32)
        yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
        xx /= width
        yy /= height
        primary = np.array(_hex_rgb(colors["primary"]), dtype=np.float32)
        accent = np.array(_hex_rgb(colors["accent"]), dtype=np.float32)
        soft = np.array(_hex_rgb(colors["primary_soft"]), dtype=np.float32)
        rng = np.random.default_rng(7)
        for index in range(frames):
            t = index / max(1, frames - 1)
            frame = base.copy()
            blobs = [
                (0.76 + 0.08 * math.sin(t * math.tau), 0.24 + 0.07 * math.cos(t * math.tau), 0.38, primary, 0.45),
                (0.24 + 0.10 * math.cos(t * math.tau + 1.2), 0.70 + 0.08 * math.sin(t * math.tau), 0.32, accent, 0.35),
                (0.55 + 0.14 * math.sin(t * math.tau + 2.4), 0.40 + 0.12 * math.cos(t * math.tau + 0.4), 0.24, soft, 0.28),
            ]
            for cx, cy, radius, color, strength in blobs:
                dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
                mask = np.clip(1 - dist / radius, 0, 1) ** 2 * strength
                frame += mask[..., None] * (color[None, None, :] - frame) * 0.7
            # Thin moving orbit line.
            line_mask = np.abs(np.sqrt((xx - 0.80) ** 2 + (yy - 0.35) ** 2) - (0.24 + 0.02 * math.sin(t * math.tau))) < 0.0018
            frame[line_mask] = frame[line_mask] * 0.65 + np.array([255, 255, 255], dtype=np.float32) * 0.35
            grain = rng.normal(0, 2.5, (height, width, 1))
            frame = np.clip(frame + grain, 0, 255).astype(np.uint8)
            Image.fromarray(frame, "RGB").save(temp_dir / f"frame_{index:04d}.jpg", "JPEG", quality=90)
        command = [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-framerate",
            str(fps),
            "-i",
            str(temp_dir / "frame_%04d.jpg"),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-movflags",
            "+faststart",
            str(path),
        ]
        result = subprocess.run(
            command,
            capture_output=True,
            timeout=90,
            creationflags=CREATE_NO_WINDOW,
        )
        if result.returncode != 0 or not path.exists() or path.stat().st_size == 0:
            global _VIDEO_ERROR
            _VIDEO_ERROR = result.stderr.decode("utf-8", errors="ignore")[-600:]
            return None
        return path
    except Exception as exc:
        _VIDEO_ERROR = f"{type(exc).__name__}: {exc}"
        return None
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


_TTS_SCRIPT = r"""param([string]$TextPath,[string]$OutPath,[string]$Culture='zh')
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$v = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -like "$Culture*" } | Select-Object -First 1
if ($v) { $s.SelectVoice($v.VoiceInfo.Name) }
$s.Rate = 0
$s.Volume = 100
$s.SetOutputToWaveFile($OutPath)
$text = [System.IO.File]::ReadAllText($TextPath, [System.Text.Encoding]::UTF8)
$s.Speak($text)
$s.Dispose()
"""


def _edge_tts(text: str, voice: str, target: Path, timeout: int = 90) -> bool:
    if edge_tts is None or voice not in EDGE_VOICE_IDS:
        return False
    try:
        async def run() -> None:
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(str(target))

        asyncio.run(asyncio.wait_for(run(), timeout=timeout))
        return target.exists() and target.stat().st_size > 1000
    except Exception:
        target.unlink(missing_ok=True)
        return False


def synthesize_narration(
    text: str,
    cache_key: str,
    *,
    timeout: int = 90,
    voice: str | None = None,
    en_voice: str | None = None,
) -> Path | None:
    """Synthesize narration with a selected natural voice.

    Uses Microsoft Edge neural voices when network is available and falls back
    to the installed Windows SAPI voice. English text is automatically routed
    to the selected English voice.
    """
    text = (text or "").strip()
    if not text:
        return None
    selected = voice_for_text(text, voice, en_voice)
    voice_info = get_voice(selected) or {}
    language = "en" if voice_info.get("language") == "en" or is_english_text(text) else "zh"
    VOICE_DIR.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(f"{text}|v3|{selected}|{cache_key}".encode("utf-8")).hexdigest()[:20]
    mp3_target = VOICE_DIR / f"{digest}.mp3"
    wav_target = VOICE_DIR / f"{digest}.wav"
    if mp3_target.exists() and mp3_target.stat().st_size > 1500:
        return mp3_target
    if wav_target.exists() and wav_target.stat().st_size > 1500:
        return wav_target

    if _edge_tts(text, selected, mp3_target, timeout=timeout):
        return mp3_target

    script = VOICE_DIR / "sapi_tts.ps1"
    if not script.exists():
        script.write_text(_TTS_SCRIPT, encoding="utf-8-sig")
    text_path = VOICE_DIR / f"text_{digest}.txt"
    text_path.write_text(text, encoding="utf-8")
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if not powershell:
        return None
    culture = "en" if language == "en" else "zh"
    try:
        result = subprocess.run(
            [
                powershell,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
                "-TextPath",
                str(text_path),
                "-OutPath",
                str(wav_target),
                "-Culture",
                culture,
            ],
            capture_output=True,
            timeout=max(30, timeout),
            creationflags=CREATE_NO_WINDOW,
        )
        if result.returncode != 0 or not wav_target.exists() or wav_target.stat().st_size < 1000:
            return None
        return wav_target
    except Exception:
        return None
    finally:
        try:
            text_path.unlink(missing_ok=True)
        except OSError:
            pass


def _ffmpeg_duration(path: Path) -> float:
    ffmpeg = ffmpeg_path()
    if not ffmpeg:
        return 0.0
    try:
        result = subprocess.run(
            [str(ffmpeg), "-i", str(path)],
            capture_output=True,
            timeout=20,
            creationflags=CREATE_NO_WINDOW,
        )
        match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", result.stderr.decode("utf-8", errors="ignore"))
        if match:
            hours, minutes, seconds = match.groups()
            return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    except Exception:
        pass
    return 0.0


def wav_duration(path: Path | None) -> float:
    if not path or not path.exists():
        return 0.0
    if path.suffix.lower() != ".wav":
        return _ffmpeg_duration(path) or video_duration(path)
    try:
        with wave.open(str(path), "rb") as handle:
            rate = handle.getframerate() or 22050
            return handle.getnframes() / float(rate)
    except Exception:
        return 0.0


def video_duration(path: Path | None) -> float:
    if not path or not path.exists():
        return 0.0
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        # imageio's binary folder usually includes ffprobe in recent releases.
        ffmpeg = ffmpeg_path()
        if ffmpeg:
            candidate = str(Path(ffmpeg).with_name("ffprobe.exe"))
            if Path(candidate).exists():
                ffprobe = candidate
    if not ffprobe:
        return 4.5
    try:
        result = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=nw=1:nk=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=20,
            creationflags=CREATE_NO_WINDOW,
        )
        return float((result.stdout or "0").strip() or 0)
    except Exception:
        return 4.5


def find_soffice() -> Path | None:
    for candidate in _PPTX_SOFFICE_CANDIDATES:
        if candidate.exists():
            return candidate
    found = shutil.which("soffice")
    return Path(found) if found else None


def export_pdf(pptx_path: Path, output_dir: Path, *, timeout: int = 150) -> Path | None:
    """Convert with LibreOffice if available. PDF export is best-effort."""
    soffice = find_soffice()
    if not soffice or not pptx_path.exists():
        return None
    output_dir.mkdir(parents=True, exist_ok=True)
    profile = CACHE_DIR / "lo_profile"
    profile.mkdir(parents=True, exist_ok=True)
    command = [
        str(soffice),
        "--headless",
        "--norestore",
        "--invisible",
        f"-env:UserInstallation=file:///{profile.as_posix()}",
        "--convert-to",
        "pdf",
        "--outdir",
        str(output_dir),
        str(pptx_path),
    ]
    try:
        subprocess.run(command, capture_output=True, timeout=timeout, creationflags=CREATE_NO_WINDOW)
    except Exception:
        return None
    candidate = output_dir / f"{pptx_path.stem}.pdf"
    return candidate if candidate.exists() and candidate.stat().st_size > 2000 else None


def render_pdf_preview(pdf_path: Path, output_dir: Path, *, pages: int = 4) -> list[Path]:
    try:
        import fitz  # PyMuPDF

        output_dir.mkdir(parents=True, exist_ok=True)
        results: list[Path] = []
        with fitz.open(str(pdf_path)) as doc:
            for index in range(min(pages, len(doc))):
                page = doc.load_page(index)
                pix = page.get_pixmap(matrix=fitz.Matrix(1.4, 1.4), alpha=False)
                target = output_dir / f"preview_{index + 1}.jpg"
                pix.save(str(target))
                results.append(target)
        return results
    except Exception:
        return []


def make_poster(color: str, path: Path, size: tuple[int, int] = (32, 32)) -> Path:
    image = Image.new("RGB", size, _hex_rgb(color))
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, "PNG")
    return path


def make_gradient_image(theme: dict[str, Any], path: Path, size: tuple[int, int] = (1200, 675)) -> Path:
    image = _gradient(size, theme["colors"]["bg"], theme["colors"]["bg2"], angle=130)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, "JPEG", quality=92)
    return path


def safe_rmtree(path: Path) -> None:
    try:
        shutil.rmtree(path, ignore_errors=True)
    except OSError:
        pass


def last_video_error() -> str:
    return _VIDEO_ERROR
