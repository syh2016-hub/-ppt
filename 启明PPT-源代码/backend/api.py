"""User-facing, template, AI, project and admin JSON APIs."""
from __future__ import annotations

import csv
import io
import json
import os
import re
import secrets
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import Blueprint, Response, current_app, jsonify, request, send_file, send_from_directory

from . import __version__
from .ai import (
    generate_outline,
    provider_health,
    public_ai_settings,
    regenerate_slide,
    save_ai_settings,
)
from .auth import admin_required, current_user, login_required
from .config import (
    ADMIN_CREDENTIALS_FILE,
    APP_NAME,
    APP_NAME_EN,
    DATA_DIR,
    MASTER_INVITE_CODE,
    MAX_SLIDES,
    MIN_SLIDES,
    ONLINE_CACHE_DIR,
    PROJECTS_DIR,
)
from .db import (
    admin_projects,
    admin_users,
    count_invite_uses,
    create_project,
    delete_project,
    get_project,
    get_setting,
    get_settings,
    get_stats,
    get_user,
    increment_download,
    invite_use_rows,
    list_projects,
    log_event,
    recent_events,
    set_settings,
    update_project,
)
from .jobs import generation_manager
from .mailer import (
    MailConfigError,
    MailSendError,
    email_verification_ready,
    send_email,
    smtp_config,
    valid_email,
)
from .media import export_pdf, last_video_error, synthesize_narration
from .voices import public_voices, get_voice, normalize_voice, DEFAULT_ZH_VOICE, DEFAULT_EN_VOICE
from .references import (
    MAX_FILES,
    delete_reference,
    extract_reading_material,
    get_reference,
    list_references,
    public_reference,
    reference_material,
    reference_snippets,
    save_upload,
    thumb_path,
    validate_reference_ids,
)
from .research import online_templates
from .security import client_ip
from .themes import CATEGORIES, FEATURED_IDS, THEMES, get_theme, public_themes, resolve_template
from .utils import (
    clean_multiline,
    clean_text,
    ensure_inside,
    format_date,
    human_size,
    json_loads,
    now_iso,
    safe_filename,
    safe_json_dumps,
    truncate,
)

api_bp = Blueprint("api", __name__)

DEFAULTS = {
    "animations": True,
    "audio": False,
    "video": False,
    "auto_advance": True,
    "animation_level": "standard",
    "reference_ids": [],
    "use_reference_cover": False,
    "voice_zh": DEFAULT_ZH_VOICE,
    "voice_en": DEFAULT_EN_VOICE,
    "reading_text": "",
    "reading_title": "",
}


def fail(message: str, status: int = 400, code: str = "BAD_REQUEST", **extra):
    payload = {"ok": False, "error": message, "code": code}
    payload.update(extra)
    return jsonify(payload), status


def ok(**payload):
    payload.setdefault("ok", True)
    return jsonify(payload)


def _json_body() -> dict[str, Any]:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _normalize_options(raw: Any) -> dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    options = {
        "animations": bool(raw.get("animations", DEFAULTS["animations"])),
        "audio": bool(raw.get("audio", DEFAULTS["audio"])),
        "video": bool(raw.get("video", DEFAULTS["video"])),
        "auto_advance": bool(raw.get("auto_advance", DEFAULTS["auto_advance"])),
        "auto_advance_without_audio": bool(raw.get("auto_advance_without_audio", False)),
        "animation_level": str(raw.get("animation_level") or "standard"),
        "reference_ids": [],
        "use_reference_cover": bool(raw.get("use_reference_cover", False)),
        "voice_zh": normalize_voice(raw.get("voice_zh"), "zh"),
        "voice_en": normalize_voice(raw.get("voice_en"), "en"),
        "reading_text": clean_multiline(raw.get("reading_text"), 4000),
        "reading_title": clean_text(raw.get("reading_title"), 80),
    }
    for value in (raw.get("reference_ids") or [])[:MAX_FILES]:
        try:
            reference_id = int(value)
        except (TypeError, ValueError):
            continue
        if reference_id not in options["reference_ids"]:
            options["reference_ids"].append(reference_id)
    if options["animation_level"] not in {"subtle", "standard", "dynamic"}:
        options["animation_level"] = "standard"
    if not options["audio"] and not options["auto_advance_without_audio"]:
        options["auto_advance"] = False
    if not options["animations"]:
        options["auto_advance_without_audio"] = False
    return options


def _validate_outline(outline: Any) -> dict[str, Any]:
    if not isinstance(outline, dict):
        raise ValueError("大纲数据不完整")
    slides = outline.get("slides")
    if not isinstance(slides, list) or len(slides) < MIN_SLIDES:
        raise ValueError(f"大纲至少需要 {MIN_SLIDES} 页")
    if len(slides) > MAX_SLIDES:
        raise ValueError(f"大纲最多支持 {MAX_SLIDES} 页")
    cleaned: list[dict[str, Any]] = []
    for slide in slides:
        if not isinstance(slide, dict):
            continue
        slide_type = str(slide.get("type") or "bullets")
        if slide_type not in {"cover", "agenda", "section", "bullets", "stats", "quote", "summary", "reading", "end"}:
            slide_type = "bullets"
        bullets = slide.get("bullets") if isinstance(slide.get("bullets"), list) else []
        stats = slide.get("stats") if isinstance(slide.get("stats"), list) else []
        cleaned.append(
            {
                "type": slide_type,
                "eyebrow": clean_text(slide.get("eyebrow"), 44),
                "title": clean_text(slide.get("title"), 88) or "未命名页面",
                "subtitle": clean_text(slide.get("subtitle"), 180),
                "bullets": [clean_text(item, 140) for item in bullets[:5] if clean_text(item, 140)],
                "stats": [
                    {
                        "value": clean_text(item.get("value"), 16),
                        "label": clean_text(item.get("label"), 26),
                        "note": clean_text(item.get("note"), 44),
                    }
                    for item in stats[:4]
                    if isinstance(item, dict) and clean_text(item.get("value"), 16)
                ],
                "quote": clean_text(slide.get("quote"), 180),
                "author": clean_text(slide.get("author"), 50),
                "notes": clean_multiline(slide.get("notes"), 1200),
                "reading_text": clean_multiline(slide.get("reading_text"), 3000),
                "section": slide.get("section") if isinstance(slide.get("section"), int) else 0,
            }
        )
    if len(cleaned) < MIN_SLIDES:
        raise ValueError(f"有效页面不足 {MIN_SLIDES} 页")
    return {
        "title": clean_text(outline.get("title"), 72) or cleaned[0]["title"],
        "subtitle": clean_text(outline.get("subtitle"), 160),
        "audience": clean_text(outline.get("audience"), 60),
        "narrative": clean_text(outline.get("narrative"), 300),
        "provider_used": clean_text(outline.get("provider_used"), 60),
        "language": "en" if str(outline.get("language") or "zh").startswith("en") else "zh",
        "sources": [
            {
                "title": clean_text(item.get("title"), 120),
                "url": clean_text(item.get("url"), 500),
                "snippet": clean_text(item.get("snippet"), 300),
            }
            for item in (outline.get("sources") or [])[:6]
            if isinstance(item, dict) and clean_text(item.get("url"), 500).startswith("http")
        ],
        "warnings": [clean_text(item, 200) for item in (outline.get("warnings") or [])[:6] if item],
        "slides": cleaned,
    }


def _sanitize_template(template_id: str, template: Any) -> tuple[str, dict[str, Any]]:
    template = template if isinstance(template, dict) else {}
    if template_id in {theme["id"] for theme in THEMES}:
        return template_id, get_theme(template_id)
    if template.get("custom"):
        image_url = clean_text(template.get("image_url"), 500)
        if image_url and not image_url.startswith(("http://", "https://")):
            raise ValueError("在线模板图片地址无效")
        payload = {
            "id": clean_text(template.get("id"), 80) or "online-custom",
            "name": clean_text(template.get("name"), 40) or "在线灵感模板",
            "custom": True,
            "base_id": clean_text(template.get("base_id"), 40) or "ink-paper",
            "image_url": image_url,
            "source_url": clean_text(template.get("source_url"), 500),
            "colors": template.get("colors") if isinstance(template.get("colors"), dict) else {},
            "motif": clean_text(template.get("motif"), 20) or "wave",
            "cover_style": clean_text(template.get("cover_style"), 20) or "split",
        }
        return payload["id"], resolve_template(payload["id"], payload)
    raise ValueError("请选择一个有效模板")


def _project_payload(project: dict[str, Any], *, include_outline: bool = True) -> dict[str, Any]:
    outline = json_loads(project.get("outline_json"), {}) or {}
    template = json_loads(project.get("template_json"), {}) or {}
    options = json_loads(project.get("options_json"), {}) or {}
    job = generation_manager.status(int(project["id"]))
    theme = resolve_template(project.get("template_id") or "ink-paper", template)
    status = project.get("status") or "draft"
    if job and job.get("state") in {"queued", "running"}:
        status = job["state"]
    payload: dict[str, Any] = {
        "id": project["id"],
        "title": project["title"],
        "prompt": project.get("prompt", ""),
        "status": status,
        "template_id": project.get("template_id"),
        "template": theme,
        "options": {**DEFAULTS, **options},
        "slide_count": project.get("slide_count") or len(outline.get("slides") or []),
        "file_size": project.get("file_size") or 0,
        "file_size_human": human_size(project.get("file_size") or 0),
        "download_count": project.get("download_count") or 0,
        "provider_used": project.get("provider_used") or outline.get("provider_used", ""),
        "created_at": project.get("created_at"),
        "updated_at": project.get("updated_at"),
        "generated_at": project.get("generated_at"),
        "created_at_text": format_date(project.get("created_at")),
        "updated_at_text": format_date(project.get("updated_at")),
        "error": project.get("error") or "",
        "progress": job.get("progress", 100 if status == "ready" else 0) if job else (100 if status == "ready" else 0),
        "message": job.get("message", "") if job else ("" if status != "ready" else "生成完成"),
        "warnings": job.get("warnings", []) if job else [],
    }
    if include_outline:
        payload["outline"] = outline
    reference_ids = options.get("reference_ids") or []
    if reference_ids:
        payload["references"] = [
            public_reference(row)
            for row in list_references(int(project["user_id"]), reference_ids)
        ]
    else:
        payload["references"] = []
    if status == "ready":
        payload["download_url"] = f"/api/projects/{project['id']}/download?format=pptx"
        payload["pdf_url"] = f"/api/projects/{project['id']}/download?format=pdf"
    return payload


def _owned_project(project_id: int, *, allow_admin: bool = False) -> dict[str, Any] | None:
    project = get_project(project_id)
    if not project:
        return None
    user = current_user()
    if not user:
        return None
    if int(project["user_id"]) != int(user["id"]) and not (allow_admin and user.get("role") == "admin"):
        return None
    return project


# --------------------------------------------------------------------- meta
@api_bp.get("/api/health")
def health():
    return ok(status="running", version=__version__, time=now_iso())


@api_bp.get("/api/meta")
def meta():
    user = current_user()
    themes = public_themes()
    return ok(
        app={
            "name": APP_NAME,
            "name_en": APP_NAME_EN,
            "version": __version__,
            "tagline": get_setting("brand_tagline", "把想法，讲成一场好戏"),
            "free": True,
        },
        user=user and {
            "id": user["id"],
            "username": user["username"],
            "display_name": user["display_name"],
            "role": user["role"],
            "avatar_hue": user["avatar_hue"],
            "email": user["email"],
            "created_at": user["created_at"],
            "must_change_password": bool(user.get("must_change_password")),
        },
        registration_enabled=get_setting("registration_enabled", "1") == "1",
        invite_required=True,
        email_verification_enabled=get_setting("email_verification_enabled", "0") == "1",
        email_verification_ready=email_verification_ready(),
        online_search_enabled=get_setting("online_search_enabled", "1") == "1",
        online_templates_enabled=get_setting("online_templates_enabled", "1") == "1",
        allow_user_keys=get_setting("allow_user_keys", "1") == "1",
        active_provider=public_ai_settings(user["id"])["active_provider"] if user else "local",
        categories=CATEGORIES,
        featured=FEATURED_IDS,
        theme_count=len(themes),
        default_options={
            "animations": get_setting("default_animations", "1") == "1",
            "audio": get_setting("default_audio", "0") == "1",
            "video": get_setting("default_video", "0") == "1",
        },
    )


# ---------------------------------------------------------------- templates
@api_bp.get("/api/templates")
def templates():
    items = public_themes()
    return ok(items=items, categories=CATEGORIES, featured=FEATURED_IDS)


@api_bp.get("/api/templates/online")
@login_required
def templates_online():
    if get_setting("online_templates_enabled", "1") != "1":
        return fail("管理员已关闭联网模板搜索", 403, "ONLINE_DISABLED")
    query = clean_text(request.args.get("q"), 100)
    started = time.time()
    items, notice = online_templates(query, limit=10)
    return ok(
        items=items,
        notice=notice,
        query=query,
        elapsed_ms=int((time.time() - started) * 1000),
    )


@api_bp.get("/api/templates/online/thumb/<key>")
def template_thumb(key: str):
    if not re.fullmatch(r"[a-f0-9]{20}", key or ""):
        return fail("缩略图不存在", 404, "NOT_FOUND")
    target = ONLINE_CACHE_DIR / f"{key}.jpg"
    if not target.exists():
        return fail("缩略图已过期，请重新搜索", 404, "NOT_FOUND")
    return send_from_directory(ONLINE_CACHE_DIR, f"{key}.jpg", mimetype="image/jpeg", max_age=3600)


# --------------------------------------------------------------- references
@api_bp.post("/api/references/upload")
@login_required
def references_upload():
    user = current_user()
    files = request.files.getlist("files")
    if not files:
        return fail("请选择要上传的参考文件", 400, "NO_FILES")
    if len(files) > MAX_FILES:
        return fail(f"一次最多上传 {MAX_FILES} 个文件", 400, "TOO_MANY")
    items: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for upload in files:
        if not upload or not upload.filename:
            continue
        try:
            item = save_upload(int(user["id"]), upload)
            items.append(item)
        except Exception as exc:
            errors.append({"filename": clean_text(upload.filename, 140), "error": clean_text(str(exc), 260)})
    if items:
        log_event(
            "reference_upload",
            f"上传参考素材 {len(items)} 个：" + "、".join(item["filename"] for item in items[:4]),
            user_id=int(user["id"]),
            ip=client_ip(request),
        )
    return ok(items=items, errors=errors, message=f"已处理 {len(items)} 个文件")


@api_bp.get("/api/references")
@login_required
def references_list():
    user = current_user()
    ids: list[int] = []
    raw_ids = request.args.get("ids", "")
    if raw_ids:
        for part in raw_ids.split(","):
            try:
                ids.append(int(part))
            except ValueError:
                continue
    rows = list_references(int(user["id"]), ids or None)
    return ok(items=[public_reference(row) for row in rows])


@api_bp.post("/api/references/reading")
@login_required
def references_reading():
    user = current_user()
    payload = _json_body()
    ids = validate_reference_ids(int(user["id"]), payload.get("reference_ids"))
    material = extract_reading_material(int(user["id"]), ids)
    return ok(reading=material)


@api_bp.delete("/api/references/<int:reference_id>")
@login_required
def references_delete(reference_id: int):
    user = current_user()
    if not delete_reference(int(user["id"]), reference_id):
        return fail("参考文件不存在", 404, "NOT_FOUND")
    return ok(message="参考文件已删除")


@api_bp.get("/api/references/<int:reference_id>/thumb")
@login_required
def references_thumb(reference_id: int):
    user = current_user()
    target = thumb_path(int(user["id"]), reference_id)
    if not target:
        return fail("缩略图不存在", 404, "NOT_FOUND")
    return send_file(target, mimetype="image/jpeg", conditional=True)


# --------------------------------------------------------------------- voices
@api_bp.get("/api/voices")
@login_required
def voices_api():
    return ok(items=public_voices())


@api_bp.post("/api/voice/preview")
@login_required
def voice_preview():
    payload = _json_body()
    voice = get_voice(payload.get("voice"))
    if not voice:
        return fail("请选择有效的旁白声音", 400, "INVALID_VOICE")
    text = clean_text(payload.get("text"), 180) or voice.get("sample") or "你好，这是旁白试听。"
    path = synthesize_narration(text, f"preview_{voice['id']}", voice=voice["id"], en_voice=voice["id"], timeout=45)
    if not path:
        return fail("声音试听生成失败，请检查网络或稍后重试", 503, "TTS_FAILED")
    mimetype = "audio/mpeg" if path.suffix.lower() == ".mp3" else "audio/wav"
    return send_file(path, mimetype=mimetype, conditional=True)


# ------------------------------------------------------------------ AI APIs
@api_bp.post("/api/ai/outline")
@login_required
def ai_outline():
    user = current_user()
    payload = _json_body()
    prompt = clean_multiline(payload.get("prompt"), 3000).strip()
    if len(prompt) < 4:
        return fail("请再多写一点你的 PPT 需求", 400, "VALIDATION", field="prompt")
    target = payload.get("slides", 10)
    try:
        target = max(MIN_SLIDES, min(MAX_SLIDES, int(target)))
    except (TypeError, ValueError):
        target = 10
    audience = clean_text(payload.get("audience"), 60)
    tone = str(payload.get("tone") or "professional")
    if tone not in {"professional", "inspiring", "story", "academic", "friendly"}:
        tone = "professional"
    provider = str(payload.get("provider") or "auto")
    if provider not in {"auto", "deepseek", "doubao", "custom", "local"}:
        provider = "auto"
    language = "en" if str(payload.get("language") or "zh").lower().startswith("en") else "zh"
    enable_search = bool(payload.get("enable_search", False))
    reference_ids = validate_reference_ids(int(user["id"]), payload.get("reference_ids"))
    reference_data = reference_material(int(user["id"]), reference_ids)
    reference_notes = reference_snippets(int(user["id"]), reference_ids, limit=5)
    options = {
        "include_agenda": bool(payload.get("include_agenda", True)),
        "include_summary": bool(payload.get("include_summary", True)),
        "include_qa": bool(payload.get("include_qa", True)),
    }
    try:
        outline = generate_outline(
            prompt,
            user_id=int(user["id"]),
            target_slides=target,
            audience=audience,
            tone=tone,
            provider=provider,
            language=language,
            enable_search=enable_search,
            reference_text=reference_data["text"],
            reference_files=reference_data["files"],
            reference_notes=reference_notes,
            **options,
        )
        outline["language"] = language
        outline["reference_files"] = reference_data["files"]
        outline["reference_snippets"] = reference_notes
        outline["warnings"] = list(dict.fromkeys((outline.get("warnings") or []) + reference_data["warnings"]))
    except Exception as exc:
        current_app.logger.exception("outline generation failed")
        return fail(f"大纲生成失败：{str(exc)[:160]}", 500, "AI_FAILED")
    log_event(
        "outline",
        f"生成大纲：{truncate(outline.get('title'), 50)} / {len(outline.get('slides', []))}页 / {outline.get('provider_used')}",
        user_id=int(user["id"]),
        ip=client_ip(request),
    )
    return ok(outline=outline, provider_used=outline.get("provider_used"), warnings=outline.get("warnings", []))


@api_bp.post("/api/ai/slide")
@login_required
def ai_slide():
    user = current_user()
    payload = _json_body()
    outline = _validate_outline(payload.get("outline")) if payload.get("outline") else None
    if not outline:
        return fail("当前大纲无效")
    index = payload.get("index")
    try:
        index = int(index)
    except (TypeError, ValueError):
        return fail("页面序号无效")
    if not (0 <= index < len(outline["slides"])):
        return fail("页面不存在")
    provider = str(payload.get("provider") or "auto")
    try:
        replacement = regenerate_slide(
            outline.get("title") or "",
            outline,
            index,
            user_id=int(user["id"]),
            provider=provider,
        )
    except Exception as exc:
        return fail(f"重写失败：{str(exc)[:160]}", 500, "AI_FAILED")
    outline["slides"][index] = replacement
    return ok(slide=replacement, outline=outline)


@api_bp.get("/api/ai/settings")
@login_required
def ai_settings():
    user = current_user()
    return ok(settings=public_ai_settings(int(user["id"])))


@api_bp.put("/api/ai/settings")
@login_required
def ai_settings_save():
    user = current_user()
    try:
        settings = save_ai_settings(int(user["id"]), _json_body())
    except PermissionError as exc:
        return fail(str(exc), 403, "FORBIDDEN")
    log_event("ai_settings", "更新个人模型设置", user_id=int(user["id"]), ip=client_ip(request))
    return ok(settings=settings, message="模型设置已保存")


@api_bp.post("/api/ai/test")
@login_required
def ai_test():
    user = current_user()
    payload = _json_body()
    provider = str(payload.get("provider") or "auto")
    result = provider_health(int(user["id"]), provider)
    return ok(result=result)


# ------------------------------------------------------------------ projects
@api_bp.get("/api/projects")
@login_required
def projects_list():
    user = current_user()
    items = list_projects(int(user["id"]))
    for item in items:
        item["created_at_text"] = format_date(item.get("created_at"))
        item["updated_at_text"] = format_date(item.get("updated_at"))
        item["file_size_human"] = human_size(item.get("file_size"))
        item["template"] = get_theme(item.get("template_id") or "ink-paper")
        job = generation_manager.status(int(item["id"]))
        if job and job.get("state") in {"queued", "running"}:
            item["status"] = job["state"]
        item["progress"] = job.get("progress", 100 if item["status"] == "ready" else 0) if job else (100 if item["status"] == "ready" else 0)
        item["download_url"] = f"/api/projects/{item['id']}/download?format=pptx" if item["status"] == "ready" else ""
    return ok(items=items)


@api_bp.get("/api/projects/<int:project_id>")
@login_required
def project_detail(project_id: int):
    project = _owned_project(project_id, allow_admin=True)
    if not project:
        return fail("项目不存在或没有权限", 404, "NOT_FOUND")
    return ok(project=_project_payload(project))


@api_bp.post("/api/projects")
@login_required
def project_create():
    user = current_user()
    payload = _json_body()
    try:
        outline = _validate_outline(payload.get("outline"))
        template_id, template = _sanitize_template(
            clean_text(payload.get("template_id"), 80) or "ink-paper",
            payload.get("template"),
        )
    except ValueError as exc:
        return fail(str(exc), 400, "VALIDATION")
    title = clean_text(payload.get("title"), 72) or outline["title"]
    prompt = clean_multiline(payload.get("prompt"), 3000) or title
    options = _normalize_options(payload.get("options"))
    options["reference_ids"] = validate_reference_ids(int(user["id"]), options.get("reference_ids"))
    if not options["reference_ids"]:
        options["use_reference_cover"] = False
    project = create_project(
        int(user["id"]),
        title,
        prompt,
        outline,
        template_id,
        template,
        options,
    )
    log_event("project_created", f"创建项目：{title}", user_id=int(user["id"]), ip=client_ip(request))
    return ok(project=_project_payload(project), message="项目已创建")


@api_bp.patch("/api/projects/<int:project_id>")
@login_required
def project_update(project_id: int):
    user = current_user()
    project = _owned_project(project_id)
    if not project:
        return fail("项目不存在或没有权限", 404, "NOT_FOUND")
    payload = _json_body()
    fields: dict[str, Any] = {}
    if "title" in payload:
        title = clean_text(payload.get("title"), 72)
        if not title:
            return fail("标题不能为空")
        fields["title"] = title
    if "outline" in payload:
        try:
            outline = _validate_outline(payload.get("outline"))
        except ValueError as exc:
            return fail(str(exc), 400, "VALIDATION")
        fields["outline_json"] = safe_json_dumps(outline)
        fields["slide_count"] = len(outline["slides"])
        fields["title"] = fields.get("title") or outline["title"]
    if "template_id" in payload or "template" in payload:
        try:
            template_id, template = _sanitize_template(
                clean_text(payload.get("template_id"), 80) or project.get("template_id"),
                payload.get("template"),
            )
        except ValueError as exc:
            return fail(str(exc), 400, "VALIDATION")
        fields["template_id"] = template_id
        fields["template_json"] = safe_json_dumps(template)
    if "options" in payload:
        normalized = _normalize_options(payload.get("options"))
        normalized["reference_ids"] = validate_reference_ids(int(user["id"]), normalized.get("reference_ids"))
        if not normalized["reference_ids"]:
            normalized["use_reference_cover"] = False
        fields["options_json"] = safe_json_dumps(normalized)
    if not fields:
        return fail("没有需要保存的内容")
    if any(key in fields for key in ("outline_json", "template_id", "options_json")) and project.get("status") == "ready":
        fields["status"] = "draft"
        fields["error"] = ""
    update_project(project_id, **fields)
    project = get_project(project_id)
    return ok(project=_project_payload(project), message="已保存")


@api_bp.post("/api/projects/<int:project_id>/duplicate")
@login_required
def project_duplicate(project_id: int):
    user = current_user()
    project = _owned_project(project_id)
    if not project:
        return fail("项目不存在或没有权限", 404, "NOT_FOUND")
    outline = json_loads(project.get("outline_json"), {}) or {}
    template = json_loads(project.get("template_json"), {}) or {}
    options = json_loads(project.get("options_json"), {}) or {}
    copy = create_project(
        int(user["id"]),
        f"{project['title']}（副本）"[:72],
        project.get("prompt") or "",
        outline,
        project.get("template_id") or "ink-paper",
        template,
        options,
    )
    return ok(project=_project_payload(copy), message="已创建副本")


@api_bp.delete("/api/projects/<int:project_id>")
@login_required
def project_delete(project_id: int):
    user = current_user()
    project = _owned_project(project_id)
    if not project:
        return fail("项目不存在或没有权限", 404, "NOT_FOUND")
    if generation_manager.is_running(project_id):
        return fail("项目正在生成，暂时不能删除", 409, "BUSY")
    generation_manager.cleanup_files(project_id)
    delete_project(project_id)
    log_event("project_deleted", f"删除项目：{project['title']}", user_id=int(user["id"]), ip=client_ip(request))
    return ok(message="项目已删除")


@api_bp.post("/api/projects/<int:project_id>/generate")
@login_required
def project_generate(project_id: int):
    user = current_user()
    project = _owned_project(project_id)
    if not project:
        return fail("项目不存在或没有权限", 404, "NOT_FOUND")
    if generation_manager.is_running(project_id):
        return ok(project=_project_payload(project), message="项目已经在生成中", job=generation_manager.status(project_id))
    try:
        outline = _validate_outline(json_loads(project.get("outline_json"), {}))
    except ValueError as exc:
        return fail(str(exc), 400, "VALIDATION")
    if not outline["slides"]:
        return fail("请先生成或编辑大纲", 400, "NO_OUTLINE")
    if project.get("status") == "generating":
        update_project(project_id, status="draft", error="")
    job = generation_manager.start(current_app._get_current_object(), project_id, int(user["id"]))
    log_event(
        "generate",
        f"开始生成：{project['title']} / {len(outline['slides'])}页",
        user_id=int(user["id"]),
        ip=client_ip(request),
    )
    return ok(job=job, message="已开始生成", status_url=f"/api/projects/{project_id}/status")


@api_bp.get("/api/projects/<int:project_id>/status")
@login_required
def project_status(project_id: int):
    project = _owned_project(project_id, allow_admin=True)
    if not project:
        return fail("项目不存在或没有权限", 404, "NOT_FOUND")
    job = generation_manager.status(project_id) or {}
    return ok(
        id=project_id,
        status=job.get("state") or project.get("status"),
        progress=job.get("progress", 100 if project.get("status") == "ready" else 0),
        message=job.get("message") or project.get("error") or ("生成完成" if project.get("status") == "ready" else ""),
        error=job.get("error") or project.get("error") or "",
        warnings=job.get("warnings") or [],
        download_url=f"/api/projects/{project_id}/download?format=pptx" if project.get("status") == "ready" else "",
        pdf_url=f"/api/projects/{project_id}/download?format=pdf" if project.get("status") == "ready" else "",
    )


@api_bp.get("/api/projects/<int:project_id>/download")
@login_required
def project_download(project_id: int):
    project = _owned_project(project_id, allow_admin=True)
    if not project:
        return fail("项目不存在或没有权限", 404, "NOT_FOUND")
    fmt = (request.args.get("format") or "pptx").lower()
    title = safe_filename(project.get("title") or "启明演示")
    if fmt == "pptx":
        path = Path(project.get("pptx_path") or "")
        if not path.exists():
            return fail("文件还没有生成完成", 409, "NOT_READY")
        if not ensure_inside(PROJECTS_DIR, path):
            return fail("文件路径异常", 500, "UNSAFE_PATH")
        increment_download(project_id)
        log_event("download", f"下载 PPT：{project['title']}", user_id=int(current_user()["id"]), ip=client_ip(request))
        return send_file(path, as_attachment=True, download_name=f"{title}.pptx", mimetype="application/vnd.openxmlformats-officedocument.presentationml.presentation")
    if fmt == "pdf":
        existing = Path(project.get("pdf_path") or "")
        if existing.exists() and ensure_inside(PROJECTS_DIR, existing):
            increment_download(project_id)
            return send_file(existing, as_attachment=True, download_name=f"{title}.pdf", mimetype="application/pdf")
        source = Path(project.get("pptx_path") or "")
        if not source.exists():
            return fail("请先生成 PPT 文件", 409, "NOT_READY")
        pdf = export_pdf(source, source.parent)
        if not pdf:
            return fail("本机未检测到可用的 PDF 转换组件（LibreOffice），请直接下载 PPTX，或在装有 Office 的电脑上另存为 PDF。", 503, "PDF_UNAVAILABLE")
        update_project(project_id, pdf_path=str(pdf))
        increment_download(project_id)
        return send_file(pdf, as_attachment=True, download_name=f"{title}.pdf", mimetype="application/pdf")
    return fail("不支持的下载格式")


@api_bp.get("/api/dashboard")
@login_required
def dashboard():
    user = current_user()
    items = list_projects(int(user["id"]), limit=6)
    for item in items:
        item["updated_at_text"] = format_date(item.get("updated_at"))
        item["file_size_human"] = human_size(item.get("file_size"))
        item["template"] = get_theme(item.get("template_id") or "ink-paper")
    all_items = list_projects(int(user["id"]), limit=500)
    ready = [item for item in all_items if item["status"] == "ready"]
    return ok(
        user={
            "display_name": user["display_name"],
            "username": user["username"],
            "role": user["role"],
            "avatar_hue": user["avatar_hue"],
        },
        stats={
            "projects": len(all_items),
            "ready": len(ready),
            "slides": sum(int(item.get("slide_count") or 0) for item in all_items),
            "downloads": sum(int(item.get("download_count") or 0) for item in all_items),
        },
        recent=items,
        templates=public_themes()[:6],
    )


# -------------------------------------------------------------------- admin
def _masked(value: str) -> str:
    if not value:
        return ""
    return value[:4] + "••••••" + value[-4:] if len(value) > 10 else "••••••"


@api_bp.get("/api/admin/overview")
@admin_required
def admin_overview():
    stats = get_stats()
    stats["chart"] = stats.get("chart", {})
    values = get_settings()
    return ok(
        stats=stats,
        invite={"code": MASTER_INVITE_CODE, "uses": count_invite_uses(MASTER_INVITE_CODE)},
        app={
            "name": APP_NAME,
            "version": __version__,
            "data_dir": str(DATA_DIR),
            "free": True,
        },
        providers={
            "deepseek": bool(values.get("deepseek_api_key")),
            "doubao": bool(values.get("doubao_api_key")),
            "custom": bool(values.get("custom_api_key")),
            "active": values.get("ai_provider", "auto"),
            "online_search": values.get("online_search_enabled", "1") == "1",
            "online_templates": values.get("online_templates_enabled", "1") == "1",
            "email_verification": values.get("email_verification_enabled", "0") == "1",
            "smtp_ready": email_verification_ready(),
        },
        recent_events=recent_events(12),
        recent_projects=admin_projects(limit=8),
    )


@api_bp.get("/api/admin/users")
@admin_required
def admin_users_api():
    query = clean_text(request.args.get("q"), 80)
    try:
        limit = max(1, min(200, int(request.args.get("limit", 100))))
        offset = max(0, int(request.args.get("offset", 0)))
    except ValueError:
        limit, offset = 100, 0
    users = admin_users(query, limit, offset)
    return ok(items=users, query=query, total=len(users))


@api_bp.patch("/api/admin/users/<int:user_id>")
@admin_required
def admin_user_update(user_id: int):
    admin = current_user()
    target = get_user(user_id)
    if not target:
        return fail("用户不存在", 404, "NOT_FOUND")
    payload = _json_body()
    fields: dict[str, Any] = {}
    if "is_active" in payload:
        active = bool(payload.get("is_active"))
        if user_id == int(admin["id"]) and not active:
            return fail("不能停用当前管理员账号")
        if target.get("role") == "admin" and not active:
            return fail("不能停用管理员账号")
        fields["is_active"] = 1 if active else 0
    reset_password = str(payload.get("reset_password") or "").strip()
    generated = ""
    if reset_password:
        from .security import hash_password, valid_password

        if reset_password == "AUTO":
            reset_password = secrets.token_urlsafe(9)[:12]
            generated = reset_password
        if not valid_password(reset_password):
            return fail("新密码至少 6 位")
        fields["password_hash"] = hash_password(reset_password)
        fields["must_change_password"] = 1
    if not fields:
        return fail("没有需要修改的字段")
    from .db import get_db

    db = get_db()
    pairs = ", ".join(f"{key} = ?" for key in fields)
    db.execute(f"UPDATE users SET {pairs} WHERE id = ?", tuple(fields.values()) + (user_id,))
    if "is_active" in fields and not fields["is_active"]:
        db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    db.commit()
    if target.get("role") == "admin" and "password_hash" in fields:
        try:
            ADMIN_CREDENTIALS_FILE.unlink(missing_ok=True)
        except OSError:
            pass
    log_event("admin_user_update", f"更新用户 {target['username']}：{list(fields.keys())}", user_id=int(admin["id"]), ip=client_ip(request))
    return ok(
        message="用户信息已更新",
        generated_password=generated,
        user={"id": user_id, "username": target["username"], **{k: v for k, v in fields.items() if k != "password_hash"}},
    )


@api_bp.get("/api/admin/projects")
@admin_required
def admin_projects_api():
    query = clean_text(request.args.get("q"), 80)
    try:
        limit = max(1, min(200, int(request.args.get("limit", 100))))
        offset = max(0, int(request.args.get("offset", 0)))
    except ValueError:
        limit, offset = 100, 0
    items = admin_projects(query, limit, offset)
    for item in items:
        item["file_size_human"] = human_size(item.get("file_size"))
        item["created_at_text"] = format_date(item.get("created_at"))
    return ok(items=items, query=query)


@api_bp.delete("/api/admin/projects/<int:project_id>")
@admin_required
def admin_project_delete(project_id: int):
    project = get_project(project_id)
    if not project:
        return fail("项目不存在", 404, "NOT_FOUND")
    if generation_manager.is_running(project_id):
        return fail("项目正在生成，不能删除", 409, "BUSY")
    generation_manager.cleanup_files(project_id)
    delete_project(project_id)
    log_event("admin_project_delete", f"管理员删除项目：{project['title']}", user_id=int(current_user()["id"]), ip=client_ip(request))
    return ok(message="项目已删除")


@api_bp.get("/api/admin/invites")
@admin_required
def admin_invites_api():
    return ok(
        code=MASTER_INVITE_CODE,
        uses=count_invite_uses(MASTER_INVITE_CODE),
        items=invite_use_rows(100),
    )


@api_bp.get("/api/admin/events")
@admin_required
def admin_events_api():
    return ok(items=recent_events(120))


@api_bp.get("/api/admin/settings")
@admin_required
def admin_settings_get():
    values = get_settings()
    smtp = smtp_config()
    return ok(
        settings={
            "ai_provider": values.get("ai_provider", "auto"),
            "deepseek": {
                "has_key": bool(values.get("deepseek_api_key")),
                "key_masked": _masked(values.get("deepseek_api_key", "")),
                "model": values.get("deepseek_model", "deepseek-chat"),
                "base_url": values.get("deepseek_base_url", "https://api.deepseek.com"),
            },
            "doubao": {
                "has_key": bool(values.get("doubao_api_key")),
                "key_masked": _masked(values.get("doubao_api_key", "")),
                "model": values.get("doubao_model", ""),
                "base_url": values.get("doubao_base_url", ""),
            },
            "custom": {
                "has_key": bool(values.get("custom_api_key")),
                "key_masked": _masked(values.get("custom_api_key", "")),
                "model": values.get("custom_model", ""),
                "base_url": values.get("custom_base_url", ""),
            },
            "online_search_enabled": values.get("online_search_enabled", "1") == "1",
            "online_templates_enabled": values.get("online_templates_enabled", "1") == "1",
            "allow_user_keys": values.get("allow_user_keys", "1") == "1",
            "registration_enabled": values.get("registration_enabled", "1") == "1",
            "email_verification_enabled": values.get("email_verification_enabled", "0") == "1",
            "email_verification_ready": email_verification_ready(),
            "smtp": {
                "host": smtp["host"],
                "port": smtp["port"],
                "security": smtp["security"],
                "username": smtp["username"],
                "has_password": bool(smtp["password"]),
                "password_masked": _masked(smtp["password"]),
                "from_addr": smtp["from_addr"],
                "from_name": smtp["from_name"],
            },
            "brand_tagline": values.get("brand_tagline", "把想法，讲成一场好戏"),
            "default_animations": values.get("default_animations", "1") == "1",
            "default_audio": values.get("default_audio", "0") == "1",
            "default_video": values.get("default_video", "0") == "1",
        },
        invite_code=MASTER_INVITE_CODE,
    )


@api_bp.put("/api/admin/settings")
@admin_required
def admin_settings_put():
    admin = current_user()
    payload = _json_body()
    updates: dict[str, str] = {}
    provider = str(payload.get("ai_provider") or "").strip()
    if provider:
        if provider not in {"auto", "deepseek", "doubao", "custom", "local"}:
            return fail("AI 提供商无效")
        updates["ai_provider"] = provider
    for prefix in ("deepseek", "doubao", "custom"):
        block = payload.get(prefix) if isinstance(payload.get(prefix), dict) else {}
        key = str(block.get("api_key") or "").strip()
        if key == "CLEAR":
            updates[f"{prefix}_api_key"] = ""
        elif key:
            updates[f"{prefix}_api_key"] = key[:300]
        for field in ("model", "base_url"):
            value = str(block.get(field) or "").strip()
            if value:
                updates[f"{prefix}_{field}"] = value[:300]
    bool_fields = (
        "online_search_enabled",
        "online_templates_enabled",
        "allow_user_keys",
        "registration_enabled",
        "email_verification_enabled",
        "default_animations",
        "default_audio",
        "default_video",
    )
    for field in bool_fields:
        if field in payload:
            updates[field] = "1" if _truthy(payload.get(field)) else "0"
    smtp_payload = payload.get("smtp") if isinstance(payload.get("smtp"), dict) else {}
    if smtp_payload:
        host = str(smtp_payload.get("host") or "").strip()
        if host:
            if "://" in host or any(ch.isspace() for ch in host):
                return fail("SMTP 服务器地址格式不正确（只填主机名，例如 smtp.qq.com）")
            updates["smtp_host"] = host[:200]
        username = str(smtp_payload.get("username") or "").strip()
        if username:
            updates["smtp_username"] = username[:200]
        from_addr = str(smtp_payload.get("from_addr") or "").strip()
        if from_addr:
            if not valid_email(from_addr):
                return fail("发件邮箱格式不正确")
            updates["smtp_from"] = from_addr[:160]
        from_name = clean_text(smtp_payload.get("from_name"), 40)
        if from_name:
            updates["smtp_from_name"] = from_name
        security = str(smtp_payload.get("security") or "").strip().lower()
        if security:
            if security not in {"ssl", "starttls", "none"}:
                return fail("SMTP 加密方式无效")
            updates["smtp_security"] = security
        port_raw = smtp_payload.get("port")
        if port_raw not in (None, ""):
            try:
                port = int(port_raw)
            except (TypeError, ValueError):
                return fail("SMTP 端口必须是数字")
            if not (1 <= port <= 65535):
                return fail("SMTP 端口范围应为 1—65535")
            updates["smtp_port"] = str(port)
        password = str(smtp_payload.get("password") or "").strip()
        if password == "CLEAR":
            updates["smtp_password"] = ""
        elif password:
            updates["smtp_password"] = password[:300]
    tagline = clean_text(payload.get("brand_tagline"), 60)
    if tagline:
        updates["brand_tagline"] = tagline
    if not updates:
        return fail("没有需要保存的设置")
    final_enabled = updates.get("email_verification_enabled", get_setting("email_verification_enabled", "0")) == "1"
    final_host = updates.get("smtp_host", get_setting("smtp_host", ""))
    final_from = updates.get("smtp_from", get_setting("smtp_from", ""))
    if final_enabled and (not final_host or not valid_email(final_from)):
        return fail("开启邮箱验证码前，请先填写 SMTP 服务器和有效的发件邮箱")
    set_settings(updates)
    log_event("admin_settings", f"管理员更新设置：{', '.join(updates.keys())}", user_id=int(admin["id"]), ip=client_ip(request))
    return ok(message="设置已保存")


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"1", "true", "yes", "on"}


@api_bp.post("/api/admin/settings/test")
@admin_required
def admin_settings_test():
    payload = _json_body()
    provider = str(payload.get("provider") or "auto")
    result = provider_health(None, provider)
    return ok(result=result)


@api_bp.post("/api/admin/email/test")
@admin_required
def admin_email_test():
    payload = _json_body()
    to_addr = clean_text(payload.get("to"), 160).strip()
    if not valid_email(to_addr):
        return fail("请输入有效的测试收件邮箱")
    try:
        result = send_email(
            to_addr,
            "启明 PPT · 邮件配置测试",
            "这是一封来自启明 PPT 的测试邮件。\n\n"
            "如果你收到它，说明 SMTP 配置可以正常发送注册验证码。\n\n"
            "—— 启明 PPT",
            "<div style='font-family:Microsoft YaHei,sans-serif;padding:24px;background:#f4f0e7'>"
            "<div style='max-width:520px;margin:auto;background:#fffdf9;padding:28px;border-radius:16px'>"
            "<h2 style='margin:0 0 12px'>邮件配置成功</h2>"
            "<p style='color:#6e6a62;line-height:1.8'>这是一封来自 <strong>启明 PPT</strong> 的测试邮件。"
            "如果你收到它，说明 SMTP 配置可以正常发送注册验证码。</p></div></div>",
        )
    except (MailConfigError, MailSendError) as exc:
        return fail(str(exc), 503, "MAIL_FAILED")
    log_event("smtp_test", f"发送测试邮件到 {to_addr}", user_id=int(current_user()["id"]), ip=client_ip(request))
    return ok(message="测试邮件已发送，请检查收件箱", mode=result.get("mode"))


@api_bp.post("/api/admin/password")
@admin_required
def admin_change_password():
    admin = current_user()
    payload = _json_body()
    from .security import hash_password, valid_password, verify_password
    from .db import get_db

    current = str(payload.get("current_password") or "")
    new = str(payload.get("new_password") or "")
    if not verify_password(current, admin["password_hash"]):
        return fail("当前管理员密码不正确")
    if not valid_password(new):
        return fail("新密码至少 6 位")
    db = get_db()
    db.execute(
        "UPDATE users SET password_hash = ?, must_change_password = 0 WHERE id = ?",
        (hash_password(new), admin["id"]),
    )
    db.execute("DELETE FROM sessions WHERE user_id = ? AND token_hash <> ?", (admin["id"], admin["token_hash"]))
    db.commit()
    try:
        ADMIN_CREDENTIALS_FILE.unlink(missing_ok=True)
    except OSError:
        pass
    log_event("admin_password", "管理员修改密码", user_id=int(admin["id"]), ip=client_ip(request))
    return ok(message="管理员密码已更新")


@api_bp.get("/api/admin/export/users.csv")
@admin_required
def admin_export_users():
    users = admin_users(limit=10000)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "用户名", "昵称", "邮箱", "角色", "状态", "注册时间", "最后登录", "项目数"])
    for user in users:
        writer.writerow(
            [
                user["id"],
                user["username"],
                user["display_name"],
                user["email"],
                "管理员" if user["role"] == "admin" else "用户",
                "正常" if user["is_active"] else "停用",
                user["created_at"],
                user["last_login"] or "",
                user["project_count"],
            ]
        )
    data = "\ufeff" + output.getvalue()
    return Response(
        data,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=users.csv"},
    )


@api_bp.get("/api/admin/export/projects.csv")
@admin_required
def admin_export_projects():
    projects = admin_projects(limit=10000)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "标题", "用户", "模板", "状态", "页数", "文件大小", "下载次数", "AI 来源", "创建时间"])
    for item in projects:
        writer.writerow(
            [
                item["id"],
                item["title"],
                item["username"],
                item["template_id"],
                item["status"],
                item["slide_count"],
                item["file_size"],
                item["download_count"],
                item["provider_used"],
                item["created_at"],
            ]
        )
    data = "\ufeff" + output.getvalue()
    return Response(
        data,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=projects.csv"},
    )


@api_bp.post("/api/admin/test-generate")
@admin_required
def admin_test_generate():
    # A safe diagnostics endpoint used by the admin health panel.
    from .media import ffmpeg_path, find_soffice, synthesize_narration

    return ok(
        libreoffice=bool(find_soffice()),
        ffmpeg=bool(ffmpeg_path()),
        ffmpeg_error=last_video_error(),
        tts=bool(synthesize_narration("启明 PPT 语音测试。", "diagnostic", timeout=30)),
        python_version=os.sys.version.split()[0],
        data_dir=str(DATA_DIR),
    )
