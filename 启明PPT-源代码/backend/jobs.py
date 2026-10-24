"""Background deck-generation jobs with progress polling."""
from __future__ import annotations

import json
import shutil
import threading
import time
import traceback
from pathlib import Path
from typing import Any

from flask import Flask

from .config import PROJECTS_DIR
from .db import get_project, update_project
from .pptx_builder import build_presentation
from .references import first_image
from .themes import resolve_template
from .utils import json_loads, now_iso


class GenerationManager:
    def __init__(self) -> None:
        self._jobs: dict[int, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def status(self, project_id: int) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(project_id)
            return dict(job) if job else None

    def is_running(self, project_id: int) -> bool:
        with self._lock:
            job = self._jobs.get(project_id)
            return bool(job and job.get("state") in {"queued", "running"})

    def start(self, app: Flask, project_id: int, user_id: int) -> dict[str, Any]:
        with self._lock:
            existing = self._jobs.get(project_id)
            if existing and existing.get("state") in {"queued", "running"}:
                return dict(existing)
            job = {
                "state": "queued",
                "progress": 0,
                "message": "已加入生成队列",
                "error": "",
                "started_at": now_iso(),
                "finished_at": None,
            }
            self._jobs[project_id] = job
        thread = threading.Thread(
            target=self._run,
            args=(app, project_id, user_id),
            name=f"qiming-generation-{project_id}",
            daemon=True,
        )
        thread.start()
        return dict(job)

    def _update(self, project_id: int, **values: Any) -> None:
        with self._lock:
            job = self._jobs.setdefault(project_id, {})
            job.update(values)

    def _run(self, app: Flask, project_id: int, user_id: int) -> None:
        with app.app_context():
            project_dir = PROJECTS_DIR / str(project_id)
            try:
                self._update(project_id, state="running", progress=1, message="正在读取项目")
                project = get_project(project_id)
                if not project or int(project["user_id"]) != int(user_id):
                    raise RuntimeError("项目不存在或没有权限")
                update_project(project_id, status="generating", error="")
                outline = json_loads(project.get("outline_json"), {}) or {}
                template = json_loads(project.get("template_json"), {}) or {}
                options = json_loads(project.get("options_json"), {}) or {}
                theme = resolve_template(project.get("template_id") or "ink-paper", template)
                project_dir.mkdir(parents=True, exist_ok=True)
                # Clean any previous output but keep cached voice assets elsewhere.
                for name in ("presentation.pptx", "preview.pdf"):
                    target = project_dir / name
                    if target.exists():
                        target.unlink(missing_ok=True)
                (project_dir / "previews").mkdir(exist_ok=True)
                for old in (project_dir / "previews").glob("*.jpg"):
                    old.unlink(missing_ok=True)

                def progress(percent: int, message: str) -> None:
                    self._update(
                        project_id,
                        progress=max(0, min(99, int(percent))),
                        message=message,
                    )

                output, meta = build_presentation(
                    project_dir=project_dir,
                    title=project.get("title") or outline.get("title") or "启明演示",
                    outline=outline,
                    theme=theme,
                    options=options,
                    reference_cover=first_image(int(user_id), options.get("reference_ids") or [])
                    if options.get("use_reference_cover")
                    else None,
                    progress=progress,
                )
                validation = meta.get("validation") or {}
                update_project(
                    project_id,
                    status="ready",
                    error="",
                    pptx_path=str(output),
                    file_size=int(meta.get("size") or output.stat().st_size),
                    slide_count=int(validation.get("slides") or len(outline.get("slides") or [])),
                    provider_used=outline.get("provider_used", "") or project.get("provider_used", ""),
                    generated_at=now_iso(),
                    pdf_path="",
                )
                warnings = meta.get("warnings") or []
                self._update(
                    project_id,
                    state="ready",
                    progress=100,
                    message="生成完成" + (f"（{warnings[0]}）" if warnings else ""),
                    error="",
                    warnings=warnings,
                    finished_at=now_iso(),
                    size=int(meta.get("size") or 0),
                    audio_slides=int(meta.get("audio_slides") or 0),
                    video=bool(meta.get("video")),
                )
            except Exception as exc:
                message = str(exc)
                try:
                    update_project(project_id, status="failed", error=message[:800])
                except Exception:
                    pass
                self._update(
                    project_id,
                    state="failed",
                    progress=0,
                    message="生成失败",
                    error=message[:800],
                    finished_at=now_iso(),
                    traceback=traceback.format_exc()[-2000:],
                )

    def cleanup_files(self, project_id: int) -> None:
        project_dir = PROJECTS_DIR / str(project_id)
        if project_dir.exists():
            shutil.rmtree(project_dir, ignore_errors=True)
        with self._lock:
            self._jobs.pop(project_id, None)


generation_manager = GenerationManager()
