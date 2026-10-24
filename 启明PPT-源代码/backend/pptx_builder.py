"""PowerPoint writer: branded themes, editable text, animation, narration and video."""
from __future__ import annotations

import io
import math
import re
import shutil
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

from lxml import etree
from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

from .animations import build_animation_timing, build_transition, insert_transition_and_timing
from .media import (
    download_background,
    generate_background_art,
    generate_motion_video,
    make_overlay,
    make_poster,
    synthesize_narration,
    wav_duration,
)
from .utils import make_gradient, mix_color, truncate
from .voices import voice_for_text

SLIDE_W = 13.333
SLIDE_H = 7.5
MARGIN = 0.78
Progress = Callable[[int, str], None]


def _rgb(color: str) -> RGBColor:
    color = (color or "#000000").lstrip("#")
    if len(color) == 3:
        color = "".join(ch * 2 for ch in color)
    return RGBColor(int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16))


def _bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "有"}


def _set_font(run, *, font: str, size: float, bold: bool = False, color: str = "#000000", spacing: int = 0) -> None:
    run.font.name = font
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = _rgb(color)
    rpr = run._r.get_or_add_rPr()
    rpr.set("lang", "zh-CN")
    rpr.set("altLang", "en-US")
    if spacing:
        rpr.set("spc", str(spacing))
    for tag in ("a:ea", "a:cs"):
        element = rpr.find(qn(tag))
        if element is None:
            element = etree.SubElement(rpr, qn(tag))
        element.set("typeface", font)


def _fill(shape, color: str | None) -> None:
    if color:
        shape.fill.solid()
        shape.fill.fore_color.rgb = _rgb(color)
    else:
        shape.fill.background()


def _line(shape, color: str | None, width: float = 1.0) -> None:
    if color:
        shape.line.color.rgb = _rgb(color)
        shape.line.width = Pt(width)
    else:
        shape.line.fill.background()


def _add_text(
    slide,
    text: str,
    left: float,
    top: float,
    width: float,
    height: float,
    *,
    size: float = 16,
    color: str = "#111111",
    font: str = "微软雅黑",
    bold: bool = False,
    align: PP_ALIGN = PP_ALIGN.LEFT,
    anchor: MSO_ANCHOR = MSO_ANCHOR.TOP,
    spacing: int = 0,
    line_spacing: float = 1.08,
    margins: tuple[float, float, float, float] = (0, 0, 0, 0),
):
    box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    frame = box.text_frame
    frame.clear()
    frame.word_wrap = True
    frame.margin_left = Inches(margins[0])
    frame.margin_right = Inches(margins[1])
    frame.margin_top = Inches(margins[2])
    frame.margin_bottom = Inches(margins[3])
    frame.vertical_anchor = anchor
    paragraph = frame.paragraphs[0]
    paragraph.alignment = align
    paragraph.line_spacing = line_spacing
    run = paragraph.add_run()
    run.text = str(text or "")
    _set_font(run, font=font, size=size, bold=bold, color=color, spacing=spacing)
    return box


def _add_multiline(
    slide,
    lines: list[dict[str, Any]],
    left: float,
    top: float,
    width: float,
    height: float,
    *,
    anchor: MSO_ANCHOR = MSO_ANCHOR.TOP,
    margins: tuple[float, float, float, float] = (0, 0, 0, 0),
):
    box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    frame = box.text_frame
    frame.clear()
    frame.word_wrap = True
    frame.margin_left = Inches(margins[0])
    frame.margin_right = Inches(margins[1])
    frame.margin_top = Inches(margins[2])
    frame.margin_bottom = Inches(margins[3])
    frame.vertical_anchor = anchor
    for index, line in enumerate(lines):
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        paragraph.alignment = line.get("align", PP_ALIGN.LEFT)
        paragraph.line_spacing = line.get("line_spacing", 1.1)
        paragraph.space_before = Pt(line.get("space_before", 0))
        paragraph.space_after = Pt(line.get("space_after", 0))
        run = paragraph.add_run()
        run.text = str(line.get("text", ""))
        _set_font(
            run,
            font=line.get("font", "微软雅黑"),
            size=line.get("size", 16),
            bold=line.get("bold", False),
            color=line.get("color", "#111111"),
            spacing=line.get("spacing", 0),
        )
    return box


def _add_rect(
    slide,
    left: float,
    top: float,
    width: float,
    height: float,
    *,
    fill: str | None,
    line: str | None = None,
    radius: bool = False,
    line_width: float = 1.0,
):
    shape_type = MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE
    shape = slide.shapes.add_shape(shape_type, Inches(left), Inches(top), Inches(width), Inches(height))
    if radius:
        try:
            shape.adjustments[0] = 0.07
        except Exception:
            pass
    _fill(shape, fill)
    _line(shape, line, line_width)
    try:
        shape.shadow.inherit = False
    except Exception:
        pass
    # Drop the theme shape style so LibreOffice and PowerPoint do not add a
    # default drop shadow through p:style/effectRef.
    style = shape._element.find(qn("p:style"))
    if style is not None:
        shape._element.remove(style)
    shape.text_frame.text = ""
    return shape


def _add_oval(slide, left: float, top: float, width: float, height: float, *, fill: str | None, line: str | None, line_width: float = 1.0):
    shape = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(left), Inches(top), Inches(width), Inches(height))
    _fill(shape, fill)
    _line(shape, line, line_width)
    try:
        shape.shadow.inherit = False
    except Exception:
        pass
    style = shape._element.find(qn("p:style"))
    if style is not None:
        shape._element.remove(style)
    return shape


def _add_picture(slide, path: Path, left: float = 0, top: float = 0, width: float = SLIDE_W, height: float = SLIDE_H):
    return slide.shapes.add_picture(str(path), Inches(left), Inches(top), Inches(width), Inches(height))


def _narration_text(notes: str, limit: int = 100) -> str:
    text = re.sub(r"\s+", " ", notes or "").strip()
    if not text:
        return ""
    if limit >= 1000:
        return text[:limit]
    if len(text) <= limit:
        return text
    sentences = re.split(r"(?<=[。！？!?])", text)
    result = ""
    for sentence in sentences:
        if len(result) + len(sentence) > limit:
            break
        result += sentence
    if not result:
        result = text[:limit]
    return result.rstrip("，,；;") + "。"


class DeckBuilder:
    def __init__(
        self,
        *,
        theme: dict[str, Any],
        options: dict[str, Any],
        project_dir: Path,
        progress: Progress,
        title: str,
        reference_cover: Path | None = None,
    ) -> None:
        self.theme = theme
        self.colors = theme["colors"]
        self.options = options
        self.project_dir = project_dir
        self.assets_dir = project_dir / "assets"
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        self.progress = progress
        self.title = title
        self.reference_cover = reference_cover
        self.prs = Presentation()
        self.prs.slide_width = Inches(SLIDE_W)
        self.prs.slide_height = Inches(SLIDE_H)
        self.animations: dict[int, list[tuple[int, str, int, int]]] = {}
        self.media: dict[int, list[dict[str, Any]]] = {}
        self.audio_durations: dict[int, float] = {}
        self.warnings: list[str] = []
        self.cover_source: Path | None = None
        self.video_path: Path | None = None
        self.anim_level = str(options.get("animation_level") or "standard")
        self.with_animations = _bool(options.get("animations"), True)
        self.with_audio = _bool(options.get("audio"), False)
        self.with_video = _bool(options.get("video"), False)
        self.auto_advance = _bool(options.get("auto_advance"), True)
        self.poster = make_poster(theme["colors"]["surface_alt"], self.assets_dir / "media_poster.png")
        self.art_cache: dict[str, Path] = {}
        self._audio_paths: dict[int, Path] = {}

    # ------------------------------------------------------------------ media
    def prepare_assets(self, slide_count: int) -> None:
        self.progress(10, "正在准备主题视觉")
        if self.reference_cover and self.reference_cover.exists():
            self.cover_source = self.reference_cover
        else:
            image_url = str(self.theme.get("cover_image_url") or "")
            if image_url:
                self.progress(12, "正在下载在线模板图片")
                downloaded = download_background(image_url, self.assets_dir / "online_cover.jpg")
                if downloaded:
                    self.cover_source = downloaded
                else:
                    self.warnings.append("在线模板图片下载失败，已改用主题内置视觉。")

        for variant in ("cover", "section", "quote", "end"):
            path = self.assets_dir / f"bg_{variant}.jpg"
            try:
                generate_background_art(
                    self.theme,
                    path,
                    variant=variant,
                    cover_image_path=self.cover_source if variant in {"cover", "section"} else None,
                )
                self.art_cache[variant] = path
            except Exception:
                self.warnings.append("部分背景图生成失败，已使用纯色背景。")
        try:
            self.overlay = make_overlay(
                self.assets_dir / "overlay.png",
                (1600, 900),
                self.colors["bg"],
                82 if self.theme.get("is_dark") else 104,
                220 if self.theme.get("is_dark") else 196,
            )
        except Exception:
            self.overlay = None

        if self.with_video:
            self.progress(16, "正在生成动态封面视频")
            try:
                self.video_path = generate_motion_video(self.theme, self.assets_dir / "cover_loop.mp4")
            except Exception:
                self.video_path = None
            if not self.video_path:
                self.warnings.append("本机视频生成组件不可用，已跳过动态视频（不影响导出 PPT）。")
                self.with_video = False

        if self.with_audio:
            self._prepare_audio(slide_count)

    def _prepare_audio(self, slide_count: int) -> None:
        self.progress(18, "正在合成逐页旁白")
        # Import here so the API layer owns outline/slide data.
        slides = self.options.get("_slides") or []
        jobs: dict[int, str] = {}
        for index, slide in enumerate(slides[:slide_count]):
            limit = 1800 if slide.get("type") == "reading" else 100
            text = _narration_text(slide.get("notes", ""), limit=limit)
            if text:
                jobs[index] = text
        if not jobs:
            self.warnings.append("没有可用的演讲者备注，已跳过音频。")
            self.with_audio = False
            return
        done = 0
        voice_zh = self.options.get("voice_zh")
        voice_en = self.options.get("voice_en")
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(
                    synthesize_narration,
                    text,
                    f"p{index + 1}",
                    timeout=120,
                    voice=voice_zh,
                    en_voice=voice_en,
                ): index
                for index, text in jobs.items()
            }
            for future in as_completed(futures):
                index = futures[future]
                try:
                    path = future.result()
                except Exception:
                    path = None
                done += 1
                self.progress(18 + int(12 * done / max(1, len(jobs))), f"正在合成旁白 {done}/{len(jobs)}")
                if path:
                    self._audio_paths[index] = path
                    self.audio_durations[index] = wav_duration(path)
        if not self._audio_paths:
            self.warnings.append("所选声音合成失败，已跳过音频。可在生成设置里换一个声音后重试。")
            self.with_audio = False

    # ----------------------------------------------------------------- slides
    def new_slide(self, *, art: str | None = None, animate_bg: bool = False):
        slide = self.prs.slides.add_slide(self.prs.slide_layouts[6])
        index = len(self.prs.slides) - 1
        self.animations[index] = []
        self.media[index] = []
        try:
            slide.background.fill.solid()
            slide.background.fill.fore_color.rgb = _rgb(self.colors["bg"])
        except Exception:
            pass
        if art and art in self.art_cache:
            try:
                _add_picture(slide, self.art_cache[art])
            except Exception:
                pass
        return slide

    def animate(self, slide, shape, kind: str = "fade") -> None:
        if not self.with_animations or shape is None:
            return
        index = len(self.prs.slides) - 1
        effect, duration = self._effect_for(kind)
        self.animations[index].append((shape.shape_id, effect, duration, 0))

    def _effect_for(self, kind: str) -> tuple[str, int]:
        if self.anim_level == "subtle":
            return ("fade", 420) if kind != "number" else ("zoom", 480)
        if self.anim_level == "dynamic":
            mapping = {
                "title": ("fly", 620),
                "body": ("fly", 520),
                "fade": ("fade", 450),
                "zoom": ("zoom", 600),
                "number": ("zoom", 650),
                "line": ("wipe", 380),
                "quote": ("dissolve", 600),
            }
        else:
            mapping = {
                "title": ("fly", 560),
                "body": ("fly", 470),
                "fade": ("fade", 420),
                "zoom": ("zoom", 540),
                "number": ("zoom", 580),
                "line": ("wipe", 350),
                "quote": ("fade", 520),
            }
        return mapping.get(kind, ("fade", 450))

    def add_footer(self, slide, number: int) -> None:
        line = _add_rect(slide, 0.78, 7.02, 11.75, 0.008, fill=mix_color(self.colors["line"], self.colors["bg"], 0.25))
        label = _add_text(slide, f"{number:02d}", 12.1, 7.08, 0.45, 0.25, size=8.5, color=self.colors["muted"], align=PP_ALIGN.RIGHT)
        return line, label

    def add_top_meta(self, slide, eyebrow: str, title: str, *, title_size: float | None = None, width: float = 9.8):
        eyebrow_shape = _add_text(
            slide,
            eyebrow.upper() if eyebrow.isascii() else eyebrow,
            0.8,
            0.60,
            7.8,
            0.28,
            size=8.8,
            color=self.colors["primary"],
            bold=True,
            spacing=150,
        )
        size = title_size or (34 if len(title) <= 22 else 29 if len(title) <= 34 else 25)
        title_shape = _add_text(
            slide,
            title,
            0.8,
            0.95,
            width,
            0.9 if size >= 30 else 1.05,
            size=size,
            color=self.colors["ink"],
            bold=True,
            line_spacing=1.06,
        )
        accent = _add_rect(slide, 0.8, 1.93 if size < 30 else 1.86, 0.62, 0.055, fill=self.colors["primary"])
        self.animate(slide, eyebrow_shape, "fade")
        self.animate(slide, title_shape, "title")
        self.animate(slide, accent, "line")
        return title_shape

    # ------------------------------------------------------------------ pages
    def build_cover(self, slide_data: dict[str, Any], index: int) -> None:
        slide = self.new_slide()
        if self.with_video and self.video_path:
            try:
                video = slide.shapes.add_movie(
                    str(self.video_path),
                    0,
                    0,
                    Inches(SLIDE_W),
                    Inches(SLIDE_H),
                    poster_frame_image=str(self.art_cache.get("cover", self.poster)),
                    mime_type="video/mp4",
                )
                video.name = "动态封面"
                self.media[index].append({"kind": "video", "shape_id": video.shape_id, "delay_ms": 0, "loop": True})
            except Exception:
                self.warnings.append("视频嵌入失败，已改用静态封面。")
                if "cover" in self.art_cache:
                    _add_picture(slide, self.art_cache["cover"])
        elif "cover" in self.art_cache:
            _add_picture(slide, self.art_cache["cover"])

        if self.overlay:
            try:
                _add_picture(slide, self.overlay)
            except Exception:
                pass
        # Decorative rings.
        ring = _add_oval(slide, 9.55, 1.10, 3.25, 3.25, fill=None, line=mix_color(self.colors["accent"], self.colors["bg"], 0.20), line_width=1.1)
        ring_small = _add_oval(slide, 10.55, 2.10, 1.25, 1.25, fill=None, line=mix_color(self.colors["primary"], self.colors["bg"], 0.15), line_width=1.0)
        self.animate(slide, ring, "zoom")
        self.animate(slide, ring_small, "zoom")

        eyebrow = slide_data.get("eyebrow") or "2026 · 主题分享"
        eyebrow_shape = _add_text(slide, eyebrow, 0.88, 1.20, 7.3, 0.3, size=9.2, color=self.colors["primary"], bold=True, spacing=170)
        title = slide_data.get("title") or self.title
        title_size = 45 if len(title) <= 15 else 39 if len(title) <= 20 else 34 if len(title) <= 27 else 30
        title_shape = _add_text(slide, title, 0.84, 1.66, 8.15, 2.45, size=title_size, color=self.colors["ink"], bold=True, line_spacing=1.04)
        line_shape = _add_rect(slide, 0.88, 4.42, 1.05, 0.07, fill=self.colors["primary"])
        subtitle = slide_data.get("subtitle") or "从洞察到行动的一份完整提案"
        subtitle_shape = _add_text(slide, subtitle, 0.88, 4.72, 6.7, 0.95, size=15.5, color=self.colors["muted"], line_spacing=1.25)
        meta = "2026 · PRESENTATION"
        meta_shape = _add_text(slide, meta, 0.88, 6.42, 4.2, 0.28, size=8.6, color=self.colors["muted"], spacing=120)
        big_index = _add_text(slide, "01", 8.55, 5.05, 3.2, 1.7, size=92, color=mix_color(self.colors["bg"], self.colors["ink"], 0.15), bold=True, align=PP_ALIGN.RIGHT)
        self.animate(slide, eyebrow_shape, "fade")
        self.animate(slide, title_shape, "title")
        self.animate(slide, line_shape, "line")
        self.animate(slide, subtitle_shape, "fade")
        self.animate(slide, meta_shape, "fade")
        self._add_audio(slide, index)

    def build_agenda(self, slide_data: dict[str, Any], index: int) -> None:
        slide = self.new_slide()
        self._soft_background(slide)
        eyebrow = _add_text(slide, (slide_data.get("eyebrow") or "CONTENTS"), 0.8, 0.78, 4.5, 0.3, size=9.2, color=self.colors["primary"], bold=True, spacing=180)
        title = slide_data.get("title") or "今天，我们这样展开"
        title_shape = _add_text(slide, title, 0.8, 1.18, 4.25, 1.2, size=31, color=self.colors["ink"], bold=True)
        subtitle = _add_text(slide, slide_data.get("subtitle") or "", 0.8, 2.38, 3.8, 0.8, size=11.5, color=self.colors["muted"], line_spacing=1.3)
        huge = _add_text(slide, "目录", 0.8, 5.15, 2.8, 1.1, size=66, color=mix_color(self.colors["bg"], self.colors["primary_soft"], 0.48), bold=True)
        self.animate(slide, eyebrow, "fade")
        self.animate(slide, title_shape, "title")
        self.animate(slide, subtitle, "fade")
        self.animate(slide, huge, "zoom")

        bullets = slide_data.get("bullets") or []
        entries: list[tuple[str, str]] = []
        for raw in bullets[:6]:
            text = str(raw)
            match = re.match(r"(\d{1,2})\s+(.*?)\s*[·\-]\s*(.*)", text)
            if match:
                entries.append((match.group(2), match.group(3)))
            else:
                entries.append((text, ""))
        if not entries:
            entries = [("内容展开", "从一个清晰的问题开始")]
        top = 1.20 if len(entries) >= 5 else 1.28
        gap = 0.11 if len(entries) >= 5 else 0.22
        height = 1.34 if len(entries) <= 3 else 1.10 if len(entries) == 4 else 0.84
        for position, (name, desc) in enumerate(entries):
            y = top + position * (height + gap)
            card = _add_rect(slide, 5.32, y, 7.18, height, fill=self.colors["surface"], line=self.colors["line"], radius=True)
            if len(entries) >= 5:
                number = _add_text(slide, f"{position + 1:02d}", 5.50, y + 0.13, 0.8, 0.5, size=20, color=self.colors["primary"], bold=True)
                name_shape = _add_text(slide, name, 6.28, y + 0.10, 5.95, 0.34, size=13, color=self.colors["ink"], bold=True)
                desc_shape = _add_text(slide, desc, 6.28, y + 0.43, 5.95, 0.30, size=8.6, color=self.colors["muted"])
            else:
                number = _add_text(slide, f"{position + 1:02d}", 5.56, y + 0.20, 0.9, 0.62, size=27, color=self.colors["primary"], bold=True)
                name_shape = _add_text(slide, name, 6.45, y + 0.18, 5.5, 0.42, size=16, color=self.colors["ink"], bold=True)
                desc_shape = _add_text(slide, desc, 6.45, y + 0.65, 5.55, 0.38, size=9.8, color=self.colors["muted"])
            self.animate(slide, card, "body")
            self.animate(slide, number, "number")
            self.animate(slide, name_shape, "fade")
            self.animate(slide, desc_shape, "fade")
        self.add_footer(slide, index + 1)
        self._add_audio(slide, index)

    def build_section(self, slide_data: dict[str, Any], index: int) -> None:
        slide = self.new_slide(art="section")
        if self.overlay:
            try:
                _add_picture(slide, self.overlay)
            except Exception:
                pass
        _add_oval(slide, 9.55, 1.35, 3.65, 3.65, fill=None, line=mix_color(self.colors["accent"], self.colors["bg"], 0.28), line_width=1.0)
        number = re.sub(r"\D", "", str(slide_data.get("eyebrow") or "")) or f"{index:02d}"
        section_number = _add_text(slide, number[:2].zfill(2), 8.75, 1.10, 3.5, 2.5, size=118, color=mix_color(self.colors["bg"], self.colors["primary"], 0.26), bold=True, align=PP_ALIGN.CENTER)
        eyebrow = _add_text(slide, slide_data.get("eyebrow") or "SECTION", 0.88, 1.22, 6.5, 0.3, size=9.2, color=self.colors["primary"], bold=True, spacing=170)
        title = _add_text(slide, slide_data.get("title") or "新的章节", 0.84, 1.68, 7.0, 1.4, size=44 if len(slide_data.get("title", "")) <= 8 else 36, color=self.colors["ink"], bold=True)
        line = _add_rect(slide, 0.88, 3.62, 1.05, 0.07, fill=self.colors["primary"])
        subtitle = _add_text(slide, slide_data.get("subtitle") or "", 0.88, 3.90, 6.5, 0.9, size=14.5, color=self.colors["muted"], line_spacing=1.3)
        self.animate(slide, section_number, "number")
        self.animate(slide, eyebrow, "fade")
        self.animate(slide, title, "title")
        self.animate(slide, line, "line")
        self.animate(slide, subtitle, "fade")
        self.add_footer(slide, index + 1)
        self._add_audio(slide, index)

    def build_bullets(self, slide_data: dict[str, Any], index: int) -> None:
        slide = self.new_slide()
        self._soft_background(slide)
        title = slide_data.get("title") or "关键洞察"
        variant = index % 3
        if variant == 1:
            self._bullets_cards(slide, slide_data, index, title)
        else:
            self._bullets_editorial(slide, slide_data, index, title)
        self.add_footer(slide, index + 1)
        self._add_audio(slide, index)

    def _bullets_editorial(self, slide, slide_data: dict[str, Any], index: int, title: str) -> None:
        eyebrow = _add_text(
            slide,
            (slide_data.get("eyebrow") or "").upper() if str(slide_data.get("eyebrow") or "").isascii() else (slide_data.get("eyebrow") or ""),
            0.8,
            0.70,
            4.2,
            0.28,
            size=8.8,
            color=self.colors["primary"],
            bold=True,
            spacing=150,
        )
        size = 29 if len(title) <= 18 else 25 if len(title) <= 28 else 21
        title_shape = _add_text(slide, title, 0.8, 1.06, 4.25, 1.7, size=size, color=self.colors["ink"], bold=True, line_spacing=1.08)
        subtitle = _add_text(slide, slide_data.get("subtitle") or "", 0.8, 2.88, 4.0, 0.8, size=10.8, color=self.colors["muted"], line_spacing=1.28)
        big = _add_text(slide, f"{index + 1:02d}", 0.75, 4.55, 2.7, 1.6, size=88, color=mix_color(self.colors["bg"], self.colors["primary_soft"], 0.34), bold=True)
        self.animate(slide, eyebrow, "fade")
        self.animate(slide, title_shape, "title")
        self.animate(slide, subtitle, "fade")
        self.animate(slide, big, "number")

        bullets = slide_data.get("bullets") or []
        if not bullets:
            bullets = ["把问题定义清楚", "找到关键变量", "开始一个最小行动"]
        top = 1.16
        row_height = min(1.25, (6.05 - top) / max(1, len(bullets)))
        for position, text in enumerate(bullets[:4]):
            y = top + position * row_height
            chip = _add_oval(slide, 5.38, y + 0.12, 0.42, 0.42, fill=self.colors["primary"], line=None)
            chip_label = _add_text(slide, str(position + 1), 5.38, y + 0.16, 0.42, 0.28, size=10.5, color=self.colors["on_primary"], bold=True, align=PP_ALIGN.CENTER)
            body = _add_text(slide, text, 5.98, y + 0.08, 6.55, 0.86, size=13.2 if len(text) < 46 else 12.2, color=self.colors["ink"], line_spacing=1.25)
            separator = _add_rect(slide, 5.98, y + row_height - 0.12, 6.52, 0.007, fill=self.colors["line"])
            self.animate(slide, chip, "zoom")
            self.animate(slide, chip_label, "fade")
            self.animate(slide, body, "body")
            self.animate(slide, separator, "line")

    def _bullets_cards(self, slide, slide_data: dict[str, Any], index: int, title: str) -> None:
        eyebrow = _add_text(slide, slide_data.get("eyebrow") or "", 0.8, 0.62, 6.0, 0.28, size=8.8, color=self.colors["primary"], bold=True, spacing=150)
        title_shape = _add_text(slide, title, 0.8, 0.95, 11.6, 0.9, size=28 if len(title) <= 24 else 24, color=self.colors["ink"], bold=True)
        subtitle = _add_text(slide, slide_data.get("subtitle") or "", 0.8, 1.82, 8.5, 0.36, size=10.5, color=self.colors["muted"])
        self.animate(slide, eyebrow, "fade")
        self.animate(slide, title_shape, "title")
        self.animate(slide, subtitle, "fade")
        bullets = slide_data.get("bullets") or []
        if not bullets:
            bullets = ["把问题定义清楚", "找到关键变量", "开始一个最小行动"]
        cards = bullets[:4]
        columns = 2 if len(cards) > 2 else len(cards)
        rows = math.ceil(len(cards) / columns)
        gap = 0.24
        card_w = (11.78 - gap * (columns - 1)) / max(1, columns)
        card_h = 1.72 if rows == 2 else 2.35
        for position, text in enumerate(cards):
            row = position // columns
            col = position % columns
            x = 0.8 + col * (card_w + gap)
            y = 2.38 + row * (card_h + gap)
            card = _add_rect(slide, x, y, card_w, card_h, fill=self.colors["surface"], line=self.colors["line"], radius=True)
            accent = _add_rect(slide, x + 0.28, y + 0.27, 0.34, 0.055, fill=self.colors["accent"])
            number = _add_text(slide, f"{position + 1:02d}", x + 0.27, y + 0.42, 0.7, 0.38, size=15, color=self.colors["primary"], bold=True)
            body = _add_text(slide, text, x + 1.02, y + 0.44, card_w - 1.28, card_h - 0.68, size=12.6 if len(text) < 48 else 11.6, color=self.colors["ink"], line_spacing=1.28)
            self.animate(slide, card, "body")
            self.animate(slide, accent, "line")
            self.animate(slide, number, "number")
            self.animate(slide, body, "fade")

    def build_stats(self, slide_data: dict[str, Any], index: int) -> None:
        slide = self.new_slide()
        self._soft_background(slide)
        self.add_top_meta(slide, slide_data.get("eyebrow") or "MEASURE", slide_data.get("title") or "关键指标", width=10.6)
        subtitle = _add_text(slide, slide_data.get("subtitle") or "", 0.8, 2.05, 10.5, 0.5, size=11.5, color=self.colors["muted"])
        self.animate(slide, subtitle, "fade")
        stats = slide_data.get("stats") or []
        if not stats:
            stats = [
                {"value": "3", "label": "关键场景", "note": "先聚焦"},
                {"value": "90", "label": "验证天数", "note": "小步快跑"},
                {"value": "1", "label": "反馈机制", "note": "持续复盘"},
            ]
        count = min(3, len(stats))
        gap = 0.28
        card_w = (11.78 - gap * (count - 1)) / count
        for position, stat in enumerate(stats[:count]):
            x = 0.8 + position * (card_w + gap)
            card = _add_rect(slide, x, 2.70, card_w, 3.22, fill=self.colors["surface"], line=self.colors["line"], radius=True)
            bar = _add_rect(slide, x + 0.34, 2.70, 0.72, 0.07, fill=self.colors["primary"])
            value = _add_text(slide, str(stat.get("value") or "—"), x + 0.34, 3.06, card_w - 0.68, 1.05, size=48 if len(str(stat.get("value"))) <= 4 else 33, color=self.colors["primary"], bold=True)
            label = _add_text(slide, str(stat.get("label") or ""), x + 0.34, 4.30, card_w - 0.68, 0.45, size=14.5, color=self.colors["ink"], bold=True)
            note = _add_text(slide, str(stat.get("note") or ""), x + 0.34, 4.92, card_w - 0.68, 0.66, size=10, color=self.colors["muted"], line_spacing=1.2)
            self.animate(slide, card, "body")
            self.animate(slide, bar, "line")
            self.animate(slide, value, "number")
            self.animate(slide, label, "fade")
            self.animate(slide, note, "fade")
        self.add_footer(slide, index + 1)
        self._add_audio(slide, index)

    def build_quote(self, slide_data: dict[str, Any], index: int) -> None:
        slide = self.new_slide(art="quote")
        if self.overlay:
            try:
                _add_picture(slide, self.overlay)
            except Exception:
                pass
        mark = _add_text(slide, "“", 0.82, 0.30, 1.7, 1.4, size=112, color=mix_color(self.colors["bg"], self.colors["primary"], 0.30), bold=True, font="Georgia")
        quote = slide_data.get("quote") or "把问题讲清楚，答案就已经出现了一半。"
        size = 31 if len(quote) <= 32 else 26 if len(quote) <= 54 else 21
        quote_shape = _add_text(slide, quote, 1.08, 2.00, 10.55, 2.45, size=size, color=self.colors["ink"], bold=True, line_spacing=1.32)
        line = _add_rect(slide, 1.12, 4.42, 0.9, 0.06, fill=self.colors["primary"])
        author = slide_data.get("author") or "本次分享"
        author_shape = _add_text(slide, f"—— {author}", 1.12, 4.70, 6.0, 0.36, size=11, color=self.colors["muted"])
        self.animate(slide, mark, "zoom")
        self.animate(slide, quote_shape, "quote")
        self.animate(slide, line, "line")
        self.animate(slide, author_shape, "fade")
        self.add_footer(slide, index + 1)
        self._add_audio(slide, index)

    def build_summary(self, slide_data: dict[str, Any], index: int) -> None:
        slide = self.new_slide()
        self._soft_background(slide)
        eyebrow = _add_text(slide, slide_data.get("eyebrow") or "TAKEAWAYS", 0.8, 0.68, 5.0, 0.28, size=9, color=self.colors["primary"], bold=True, spacing=170)
        title = slide_data.get("title") or "带走这三件事"
        title_shape = _add_text(slide, title, 0.8, 1.02, 6.5, 0.85, size=31, color=self.colors["ink"], bold=True)
        subtitle = _add_text(slide, slide_data.get("subtitle") or "", 0.8, 1.88, 9.0, 0.42, size=10.6, color=self.colors["muted"])
        self.animate(slide, eyebrow, "fade")
        self.animate(slide, title_shape, "title")
        self.animate(slide, subtitle, "fade")
        bullets = slide_data.get("bullets") or []
        if not bullets:
            bullets = ["定义问题", "建立方法", "盯住反馈"]
        top = 2.55
        height = min(1.22, 4.0 / max(1, len(bullets)))
        for position, text in enumerate(bullets[:4]):
            y = top + position * (height + 0.16)
            number = _add_text(slide, f"{position + 1:02d}", 0.86, y + 0.14, 0.8, 0.55, size=23, color=self.colors["primary"], bold=True)
            body = _add_text(slide, text, 1.80, y + 0.10, 10.1, height - 0.1, size=14.2 if len(text) < 54 else 12.8, color=self.colors["ink"], line_spacing=1.25)
            separator = _add_rect(slide, 1.80, y + height - 0.02, 9.95, 0.007, fill=self.colors["line"])
            self.animate(slide, number, "number")
            self.animate(slide, body, "body")
            self.animate(slide, separator, "line")
        self.add_footer(slide, index + 1)
        self._add_audio(slide, index)

    def build_reading(self, slide_data: dict[str, Any], index: int) -> None:
        slide = self.new_slide()
        self._soft_background(slide)
        eyebrow = _add_text(slide, slide_data.get("eyebrow") or "READING · 课文朗读", 0.8, 0.58, 7.0, 0.28, size=9, color=self.colors["primary"], bold=True, spacing=150)
        title = slide_data.get("title") or "课文朗读"
        title_shape = _add_text(slide, title, 0.8, 0.95, 8.2, 0.75, size=30 if len(title) <= 26 else 24, color=self.colors["ink"], bold=True)
        source = _add_text(slide, slide_data.get("subtitle") or "请跟着旁白朗读", 0.8, 1.72, 9.0, 0.3, size=9.8, color=self.colors["muted"])
        passage = str(slide_data.get("reading_text") or slide_data.get("notes") or "").strip()
        if len(passage) > 900:
            passage = passage[:900].rstrip() + "……"
        size = 19 if len(passage) <= 180 else 16 if len(passage) <= 380 else 13.5 if len(passage) <= 650 else 11.5
        body = _add_text(
            slide,
            passage or "课文内容会显示在这里。",
            0.84,
            2.20,
            11.55,
            4.35,
            size=size,
            color=self.colors["ink"],
            line_spacing=1.55,
        )
        self.animate(slide, eyebrow, "fade")
        self.animate(slide, title_shape, "title")
        self.animate(slide, source, "fade")
        self.animate(slide, body, "body")
        self.add_footer(slide, index + 1)
        self._add_audio(slide, index)

    def build_end(self, slide_data: dict[str, Any], index: int) -> None:
        slide = self.new_slide(art="end")
        if self.overlay:
            try:
                _add_picture(slide, self.overlay)
            except Exception:
                pass
        circle = _add_oval(slide, 10.2, -1.20, 4.35, 4.35, fill=None, line=mix_color(self.colors["accent"], self.colors["bg"], 0.25), line_width=1.1)
        eyebrow = _add_text(slide, slide_data.get("eyebrow") or "THANK YOU", 4.3, 2.25, 4.75, 0.3, size=9.5, color=self.colors["primary"], bold=True, align=PP_ALIGN.CENTER, spacing=220)
        title = slide_data.get("title") or "谢谢聆听"
        title_shape = _add_text(slide, title, 2.2, 2.70, 8.9, 1.25, size=48 if len(title) <= 8 else 38, color=self.colors["ink"], bold=True, align=PP_ALIGN.CENTER)
        line = _add_rect(slide, 6.12, 4.05, 1.1, 0.06, fill=self.colors["primary"])
        subtitle = _add_text(slide, slide_data.get("subtitle") or "欢迎交流与提问", 3.1, 4.35, 7.1, 0.6, size=14.5, color=self.colors["muted"], align=PP_ALIGN.CENTER)
        self.animate(slide, circle, "zoom")
        self.animate(slide, eyebrow, "fade")
        self.animate(slide, title_shape, "title")
        self.animate(slide, line, "line")
        self.animate(slide, subtitle, "fade")
        self._add_audio(slide, index)

    def _soft_background(self, slide) -> None:
        # A large low-contrast orb adds depth without looking like a watermark.
        color = mix_color(self.colors["bg"], self.colors["primary_soft"], 0.35)
        _add_oval(slide, 10.45, -1.40, 4.65, 4.65, fill=color, line=None)
        _add_rect(slide, 0.42, 0.8, 0.045, 5.9, fill=mix_color(self.colors["bg"], self.colors["primary_soft"], 0.55))

    def _add_audio(self, slide, index: int) -> None:
        if not self.with_audio:
            return
        path = self._audio_paths.get(index)
        if not path:
            return
        try:
            shape = slide.shapes.add_movie(
                str(path),
                Inches(0.30),
                Inches(6.62),
                Inches(0.42),
                Inches(0.42),
                poster_frame_image=str(self.poster),
                mime_type="audio/mpeg" if str(path).lower().endswith(".mp3") else "audio/wav",
            )
            shape.name = f"旁白 {index + 1:02d}"
            for element in shape._element.iter(qn("a:videoFile")):
                element.tag = qn("a:audioFile")
            self.media[index].append(
                {
                    "kind": "audio",
                    "shape_id": shape.shape_id,
                    "delay_ms": 650,
                    "loop": False,
                }
            )
        except Exception:
            self.warnings.append("部分旁白未能嵌入，请检查音频组件。")

    # ------------------------------------------------------------------- save
    def finish(self, output_path: Path, slide_count: int) -> dict[str, Any]:
        self.progress(34, "正在排版幻灯片")
        # Populate actual slide data in the order created.
        self._apply_timing(slide_count)
        # Update document properties (not visible on slides).
        try:
            self.prs.core_properties.title = self.title
            self.prs.core_properties.subject = "由启明 PPT 生成"
            self.prs.core_properties.author = "启明 PPT"
            self.prs.core_properties.comments = "无水印导出"
        except Exception:
            pass
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self.prs.save(str(output_path))
        self.progress(90, "正在优化 PowerPoint 兼容性")
        _postprocess_package(output_path)
        return {
            "warnings": list(dict.fromkeys(self.warnings)),
            "audio_slides": len(self._audio_paths),
            "video": bool(self.with_video and self.video_path),
            "animations": self.with_animations,
        }

    def _apply_timing(self, slide_count: int) -> None:
        transition_cycle = ["fade", "push", "wipe", "fade"]
        for index, slide in enumerate(self.prs.slides):
            # Remove media timings python-pptx added while embedding files.
            for timing in slide._element.findall(qn("p:timing")):
                slide._element.remove(timing)
            transition = None
            if index < slide_count:
                advance_ms = None
                if self.with_audio and self.auto_advance and index in self.audio_durations:
                    advance_ms = max(4200, int((self.audio_durations[index] + 1.4) * 1000))
                elif self.auto_advance and _bool(self.options.get("auto_advance_without_audio"), False):
                    advance_ms = 9000
                if index == slide_count - 1:
                    advance_ms = None
                if self.with_animations:
                    effect = transition_cycle[index % len(transition_cycle)]
                    transition = build_transition(effect, advance_ms=advance_ms)
                elif advance_ms:
                    # Timed advance still needs a transition carrier, but no visual effect.
                    transition = build_transition("none", advance_ms=advance_ms)
            timing = build_animation_timing(
                targets=self.animations.get(index, []),
                media=self.media.get(index, []),
                gap_ms=100,
            )
            insert_transition_and_timing(slide._element, transition, timing)


def _postprocess_package(path: Path) -> None:
    """Rewrite package details python-pptx does not expose: audio rel types/timings."""
    temp_path = path.with_suffix(".tmp.pptx")
    with zipfile.ZipFile(path, "r") as source, zipfile.ZipFile(
        temp_path, "w", zipfile.ZIP_DEFLATED
    ) as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename.startswith("ppt/slides/_rels/") and item.filename.endswith(".rels"):
                text = data.decode("utf-8")
                # Audio embedded by add_movie is initially relationship type video.
                text = re.sub(
                    r'(Type="[^"]*/video")([^>]*Target="[^"]+\.(?:wav|mp3|m4a)")',
                    lambda match: match.group(1).replace("/video", "/audio") + match.group(2),
                    text,
                    flags=re.I,
                )
                data = text.encode("utf-8")
            elif item.filename == "ppt/presProps.xml":
                text = data.decode("utf-8")
                if "<p:showPr" in text and "useTimings" not in text:
                    text = re.sub(r"<p:showPr\b", '<p:showPr useTimings="1"', text, count=1)
                elif "<p:showPr" not in text:
                    show_pr = '<p:showPr useTimings="1"/>'
                    if "<p:extLst" in text:
                        text = text.replace("<p:extLst", show_pr + "<p:extLst", 1)
                    else:
                        text = text.replace("</p:presentationPr>", show_pr + "</p:presentationPr>", 1)
                data = text.encode("utf-8")
            target.writestr(item, data)
    temp_path.replace(path)


def validate_presentation(path: Path) -> dict[str, Any]:
    """Reopen the file and inspect package-level animation/media markers."""
    result = {"ok": False, "slides": 0, "animations": 0, "transitions": 0, "media": 0, "error": ""}
    try:
        presentation = Presentation(str(path))
        result["slides"] = len(presentation.slides)
        result["ok"] = result["slides"] > 0
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            result["media"] = len([name for name in names if name.startswith("ppt/media/")])
            for name in names:
                if name.startswith("ppt/slides/slide") and name.endswith(".xml"):
                    xml = archive.read(name)
                    root = etree.fromstring(xml)
                    if root.find(qn("p:timing")) is not None:
                        result["animations"] += 1
                    if root.find(qn("p:transition")) is not None:
                        result["transitions"] += 1
        return result
    except Exception as exc:
        result["error"] = str(exc)[:300]
        return result


def build_presentation(
    *,
    project_dir: Path,
    title: str,
    outline: dict[str, Any],
    theme: dict[str, Any],
    options: dict[str, Any],
    reference_cover: Path | None = None,
    progress: Progress | None = None,
) -> tuple[Path, dict[str, Any]]:
    slides = outline.get("slides") or []
    if not slides:
        raise ValueError("大纲中没有可生成的页面")
    project_dir.mkdir(parents=True, exist_ok=True)

    def report(percent: int, message: str) -> None:
        if progress:
            progress(max(0, min(99, percent)), message)

    option_copy = dict(options)
    option_copy["_slides"] = slides
    builder = DeckBuilder(
        theme=theme,
        options=option_copy,
        project_dir=project_dir,
        progress=report,
        title=title,
        reference_cover=reference_cover,
    )
    report(5, "正在启动生成引擎")
    builder.prepare_assets(len(slides))
    report(30, "正在搭建页面结构")
    for index, slide_data in enumerate(slides):
        kind = slide_data.get("type") or "bullets"
        if kind == "cover":
            builder.build_cover(slide_data, index)
        elif kind == "agenda":
            builder.build_agenda(slide_data, index)
        elif kind == "section":
            builder.build_section(slide_data, index)
        elif kind == "stats":
            builder.build_stats(slide_data, index)
        elif kind == "quote":
            builder.build_quote(slide_data, index)
        elif kind == "summary":
            builder.build_summary(slide_data, index)
        elif kind == "reading":
            builder.build_reading(slide_data, index)
        elif kind == "end":
            builder.build_end(slide_data, index)
        else:
            builder.build_bullets(slide_data, index)
        try:
            builder.prs.slides[-1].notes_slide.notes_text_frame.text = str(slide_data.get("notes") or "")
        except Exception:
            pass
        report(30 + int(55 * (index + 1) / max(1, len(slides))), f"正在排版第 {index + 1}/{len(slides)} 页")

    output = project_dir / "presentation.pptx"
    meta = builder.finish(output, len(slides))
    report(94, "正在校验文件")
    validation = validate_presentation(output)
    meta["validation"] = validation
    if not validation["ok"]:
        raise RuntimeError(f"PPT 文件校验失败：{validation['error']}")
    meta["size"] = output.stat().st_size
    report(100, "生成完成")
    return output, meta
