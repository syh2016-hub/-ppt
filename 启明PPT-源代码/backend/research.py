"""Bing-based web research and an online visual-inspiration template gallery."""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

from .config import CACHE_DIR, ONLINE_CACHE_DIR
from .themes import get_theme
from .utils import (
    IMAGE_HEADERS,
    USER_AGENT,
    cover_image,
    dominant_colors,
    normalize_image_url,
    request_image,
    save_online_thumbnail,
    truncate,
    validate_download_url,
)

BING_SEARCH = "https://cn.bing.com/search"
BING_IMAGES = "https://cn.bing.com/images/search"
DEFAULT_IMAGE_QUERY = "极简 PPT 背景 高级感"
_CACHE_LOCK = threading.Lock()
_SEARCH_CACHE: dict[str, tuple[float, Any]] = {}
IMAGE_CACHE_TTL = 60 * 60 * 6
TEXT_CACHE_TTL = 60 * 30


def _cache_get(key: str, ttl: int) -> Any | None:
    with _CACHE_LOCK:
        stored = _SEARCH_CACHE.get(key)
    if not stored:
        return None
    timestamp, value = stored
    if time.time() - timestamp > ttl:
        return None
    return value


def _cache_set(key: str, value: Any) -> None:
    with _CACHE_LOCK:
        _SEARCH_CACHE[key] = (time.time(), value)
        if len(_SEARCH_CACHE) > 80:
            oldest = sorted(_SEARCH_CACHE.items(), key=lambda item: item[1][0])[:20]
            for old_key, _ in oldest:
                _SEARCH_CACHE.pop(old_key, None)


def _headers(referer: str = "https://cn.bing.com/") -> dict[str, str]:
    return {
        "User-Agent": USER_AGENT,
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6",
        "Referer": referer,
    }


def bing_web_search(query: str, limit: int = 5) -> tuple[list[dict[str, str]], str]:
    """Return clean Bing result snippets. Never raises to the caller."""
    query = (query or "").strip()[:160]
    if not query:
        return [], ""
    cache_key = f"web:{query}:{limit}"
    cached = _cache_get(cache_key, TEXT_CACHE_TTL)
    if cached is not None:
        return cached
    notice = ""
    results: list[dict[str, str]] = []
    try:
        response = requests.get(
            BING_SEARCH,
            params={"q": query, "setlang": "zh-hans", "cc": "cn", "count": "10"},
            headers=_headers(),
            timeout=12,
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")
        for item in soup.select("li.b_algo"):
            link = item.select_one("h2 a")
            if not link:
                continue
            href = (link.get("href") or "").strip()
            if not href.startswith("http"):
                continue
            snippet_el = item.select_one(".b_caption p") or item.select_one(".b_snippet")
            snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
            title = link.get_text(" ", strip=True)
            if not title:
                continue
            results.append(
                {
                    "title": truncate(title, 120),
                    "url": href,
                    "snippet": truncate(snippet, 320),
                }
            )
            if len(results) >= limit:
                break
        if not results:
            notice = "此次联网检索没有拿到有效结果，已使用本地知识继续生成。"
    except Exception:
        notice = "联网检索暂时不可用，已使用本地知识继续生成。"
    _cache_set(cache_key, (results, notice))
    return results, notice


def _parse_bing_images(query: str, limit: int = 36) -> list[dict[str, str]]:
    response = requests.get(
        BING_IMAGES,
        params={"q": query, "form": "HDRSC2", "first": "1"},
        headers=_headers(),
        timeout=15,
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "lxml")
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for anchor in soup.select("a.iusc"):
        raw = anchor.get("m") or ""
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            continue
        image_url = str(data.get("murl") or "").strip()
        thumb_url = str(data.get("turl") or "").strip()
        page_url = str(data.get("purl") or "").strip()
        title = str(data.get("t") or "").strip()
        if not image_url or not validate_download_url(image_url):
            continue
        key = hashlib.sha1(normalize_image_url(image_url).encode("utf-8")).hexdigest()[:20]
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "key": key,
                "image_url": image_url,
                "thumb_url": thumb_url,
                "page_url": page_url,
                "title": truncate(title, 90),
            }
        )
        if len(rows) >= limit:
            break
    return rows


def _parse_baidu_images(query: str, limit: int = 30) -> list[dict[str, Any]]:
    """Baidu image search gives far better Chinese PPT-template results than Bing."""
    params = {
        "tn": "resultjson_com", "logid": "123", "ipn": "rj", "ct": "201326592",
        "is": "", "fp": "result", "fr": "", "word": query, "queryWord": query,
        "cl": "2", "lm": "-1", "ie": "utf-8", "oe": "utf-8", "adpicid": "",
        "st": "-1", "z": "", "ic": "", "hd": "", "latest": "", "copyright": "",
        "s": "", "se": "", "tab": "", "width": "", "height": "", "face": "0",
        "istype": "2", "qc": "", "nc": "1", "expermode": "", "nojc": "",
        "isAsync": "", "pn": "0", "rn": str(max(20, limit * 2)), "gsm": "1e",
    }
    response = requests.get(
        "https://image.baidu.com/search/acjson",
        params=params,
        headers={
            "User-Agent": USER_AGENT,
            "Referer": "https://image.baidu.com/",
            "Accept-Language": "zh-CN,zh;q=0.9",
        },
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in payload.get("data") or []:
        if not isinstance(item, dict):
            continue
        image_url = str(item.get("middleURL") or item.get("thumbURL") or "").strip()
        thumb_url = str(item.get("thumbURL") or item.get("hoverURL") or image_url).strip()
        if not image_url or not validate_download_url(image_url):
            continue
        key = hashlib.sha1(normalize_image_url(image_url).encode("utf-8")).hexdigest()[:20]
        if key in seen:
            continue
        seen.add(key)
        page_url = ""
        replace = item.get("replaceUrl")
        if isinstance(replace, list) and replace and isinstance(replace[0], dict):
            page_url = str(replace[0].get("FromURL") or replace[0].get("FromUrl") or "")
        width = int(item.get("width") or 0)
        height = int(item.get("height") or 0)
        rows.append(
            {
                "key": key,
                "image_url": image_url,
                "thumb_url": thumb_url,
                "page_url": page_url,
                "title": truncate(str(item.get("fromPageTitleEnc") or item.get("fromPageTitle") or ""), 90),
                "width": width,
                "height": height,
                "suggest_image": bool(width and height and width / max(1, height) >= 1.2),
            }
        )
        if len(rows) >= limit:
            break
    return rows


def _online_colors(image_path) -> tuple[list[str], dict[str, Any]]:
    theme = get_theme("ink-paper")
    colors: list[str] = []
    try:
        from PIL import Image, ImageStat

        with Image.open(image_path) as image:
            raw = dominant_colors(image, 7)
            gray = image.convert("L").resize((1, 1))
            average = gray.getpixel((0, 0))
        for value in raw:
            rgb = tuple(int(value.lstrip("#")[i : i + 2], 16) / 255 for i in (0, 2, 4))
            high, low = max(rgb), min(rgb)
            saturation = 0 if high == 0 else (high - low) / high
            brightness = sum(rgb) / 3
            if saturation >= 0.12 and 0.12 <= brightness <= 0.90:
                colors.append(value)
        if not colors:
            # Choose the least washed-out palette entry even for monochrome photos.
            for value in raw:
                rgb = tuple(int(value.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
                if max(rgb) < 245 and min(rgb) > 12:
                    colors.append(value)
                    break
    except Exception:
        colors = []
    palette = theme["colors"].copy()
    if len(colors) >= 2:
        palette["primary"] = colors[0]
        palette["accent"] = colors[1]
        palette["primary_soft"] = colors[2] if len(colors) > 2 else palette["primary_soft"]
    return colors, palette


def online_templates(query: str = "", limit: int = 10) -> tuple[list[dict[str, Any]], str]:
    """Search Bing Images, cache thumbnails and derive editable colour palettes."""
    query = (query or "").strip()[:100]
    effective_query = f"{query} PPT 模板" if query else "极简 商务 PPT 模板"
    cache_key = f"images:v3:{effective_query}:{limit}"
    cached = _cache_get(cache_key, IMAGE_CACHE_TTL)
    if cached is not None:
        return cached
    notice = ""
    raw_items: list[dict[str, Any]] = []
    try:
        raw_items = _parse_baidu_images(effective_query, limit=min(40, max(18, limit * 3)))
    except Exception:
        raw_items = []
    if len(raw_items) < 4:
        try:
            raw_items.extend(_parse_bing_images(effective_query, limit=min(40, max(12, limit * 3))))
        except Exception:
            pass
    if not raw_items:
        return [], "没有检索到合适的在线模板，换一个关键词试试。"

    selected = raw_items[: max(limit * 2, limit + 4)]
    results: list[dict[str, Any]] = []

    def build(item: dict[str, str]) -> dict[str, Any] | None:
        thumb_source = item.get("thumb_url") or item.get("image_url")
        local_thumb = save_online_thumbnail(thumb_source, item["key"])
        if not local_thumb:
            return None
        thumb_path = ONLINE_CACHE_DIR / f"{item['key']}.jpg"
        try:
            from PIL import Image

            with Image.open(thumb_path) as probe:
                w, h = probe.size
                if w < 260 or h < 160:
                    return None
        except Exception:
            return None
        raw_colors, palette = _online_colors(thumb_path)
        is_dark = False
        try:
            from PIL import Image

            with Image.open(thumb_path) as image:
                gray = image.convert("L").resize((1, 1))
                is_dark = gray.getpixel((0, 0)) < 92
        except Exception:
            pass
        base_id = "midnight" if is_dark else "ink-paper"
        base = get_theme(base_id)
        base_palette = base["colors"].copy()
        if raw_colors:
            base_palette["primary"] = raw_colors[0]
            base_palette["accent"] = raw_colors[1] if len(raw_colors) > 1 else base_palette["accent"]
        title = item.get("title") or "在线灵感图"
        return {
            "id": f"online-{item['key']}",
            "name": "在线灵感",
            "english": "Web Inspiration",
            "category": "联网",
            "description": "由联网图片提取配色生成的专属模板，导出时自动适配文字对比度。",
            "tags": ["联网", "图片", "专属配色"],
            "colors": base_palette,
            "base_id": base_id,
            "thumb_url": local_thumb,
            "image_url": item["image_url"],
            "source_url": item.get("page_url", ""),
            "source_title": truncate(title, 70),
            "suggest_image": bool(item.get("suggest_image", True)),
            "source_width": item.get("width", 0),
            "source_height": item.get("height", 0),
            "dominant": raw_colors,
            "custom": True,
            "cover_style": "split" if not is_dark else "framed",
            "motif": "wave" if not is_dark else "orbit",
        }

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(build, item) for item in selected]
        for future in as_completed(futures):
            try:
                result = future.result()
            except Exception:
                continue
            if result:
                results.append(result)
    results.sort(key=lambda item: item["name"])
    results = results[:limit]
    for index, item in enumerate(results, 1):
        item["name"] = f"在线灵感 {index:02d}"
    if not results:
        notice = "在线图片下载失败，已展示内置模板。"
    _cache_set(cache_key, (results, notice))
    return results, notice


def research_brief(query: str, limit: int = 5) -> dict[str, Any]:
    results, notice = bing_web_search(query, limit=limit)
    return {
        "query": query,
        "results": results,
        "notice": notice,
        "source_count": len(results),
    }
