"""SQLite storage for accounts, sessions, projects, settings and audit events."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from flask import g

from .config import (
    ADMIN_CREDENTIALS_FILE,
    DEFAULT_ADMIN_PASSWORD,
    DEFAULT_ADMIN_USERNAME,
    DEFAULT_SETTINGS,
    DB_PATH,
    ensure_directories,
)
from .security import hash_password
from .utils import now_iso, safe_json_dumps

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    display_name TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    is_active INTEGER NOT NULL DEFAULT 1,
    avatar_hue INTEGER NOT NULL DEFAULT 210,
    created_at TEXT NOT NULL,
    last_login TEXT,
    must_change_password INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    ip TEXT NOT NULL DEFAULT '',
    user_agent TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expiry ON sessions(expires_at);

CREATE TABLE IF NOT EXISTS invite_uses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    ip TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_invite_uses_code ON invite_uses(code);

CREATE TABLE IF NOT EXISTS email_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL COLLATE NOCASE,
    code_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    purpose TEXT NOT NULL DEFAULT 'register',
    expires_at TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 5,
    created_at TEXT NOT NULL,
    ip TEXT NOT NULL DEFAULT '',
    used_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_email_codes_email ON email_codes(email, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_email_codes_expiry ON email_codes(expires_at);

CREATE TABLE IF NOT EXISTS reference_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    ext TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL DEFAULT 'document',
    mime TEXT NOT NULL DEFAULT '',
    path TEXT NOT NULL,
    thumb_path TEXT NOT NULL DEFAULT '',
    text_path TEXT NOT NULL DEFAULT '',
    char_count INTEGER NOT NULL DEFAULT 0,
    width INTEGER NOT NULL DEFAULT 0,
    height INTEGER NOT NULL DEFAULT 0,
    palette_json TEXT NOT NULL DEFAULT '[]',
    size_bytes INTEGER NOT NULL DEFAULT 0,
    warning TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reference_files_user ON reference_files(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    prompt TEXT NOT NULL DEFAULT '',
    outline_json TEXT NOT NULL DEFAULT '{}',
    template_id TEXT NOT NULL DEFAULT 'ink-paper',
    template_json TEXT NOT NULL DEFAULT '{}',
    options_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'draft',
    error TEXT NOT NULL DEFAULT '',
    pptx_path TEXT NOT NULL DEFAULT '',
    pdf_path TEXT NOT NULL DEFAULT '',
    preview_path TEXT NOT NULL DEFAULT '',
    slide_count INTEGER NOT NULL DEFAULT 0,
    file_size INTEGER NOT NULL DEFAULT 0,
    download_count INTEGER NOT NULL DEFAULT 0,
    provider_used TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    generated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_projects_user ON projects(user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    kind TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    ip TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_user ON events(user_id, created_at DESC);
"""


def _connect(path: Path | None = None) -> sqlite3.Connection:
    ensure_directories()
    conn = sqlite3.connect(str(path or DB_PATH), timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = _connect()
    return g.db


def close_db(_error: Any = None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


@contextmanager
def standalone_db() -> Iterator[sqlite3.Connection]:
    """For background threads that do not run inside a Flask request."""
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def init_db() -> None:
    ensure_directories()
    conn = _connect()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
        now = now_iso()
        for key, value in DEFAULT_SETTINGS.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings(key, value, updated_at) VALUES (?, ?, ?)",
                (key, value, now),
            )
        admin = conn.execute(
            "SELECT id FROM users WHERE username = ?",
            (DEFAULT_ADMIN_USERNAME,),
        ).fetchone()
        if not admin:
            cursor = conn.execute(
                """INSERT INTO users
                   (username, display_name, email, password_hash, role, is_active,
                    avatar_hue, created_at, must_change_password)
                   VALUES (?, ?, ?, ?, 'admin', 1, 350, ?, 1)""",
                (
                    DEFAULT_ADMIN_USERNAME,
                    "系统管理员",
                    "",
                    hash_password(DEFAULT_ADMIN_PASSWORD),
                    now,
                ),
            )
            conn.commit()
            try:
                ADMIN_CREDENTIALS_FILE.write_text(
                    "启明 PPT 管理后台初始账号\n"
                    "========================\n"
                    f"地址：启动软件后访问 /admin\n"
                    f"账号：{DEFAULT_ADMIN_USERNAME}\n"
                    f"密码：{DEFAULT_ADMIN_PASSWORD}\n\n"
                    "首次登录后请在「后台设置」中修改密码。\n",
                    encoding="utf-8",
                )
            except OSError:
                pass
        conn.execute(
            "DELETE FROM sessions WHERE expires_at < ?",
            (now,),
        )
        conn.execute(
            "DELETE FROM email_codes WHERE expires_at < ? OR (used_at IS NOT NULL AND used_at < ?)",
            (now, (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(timespec="seconds")),
        )
        conn.execute(
            """UPDATE projects SET status = 'failed', error = ?,
               updated_at = ? WHERE status IN ('generating', 'queued')""",
            ("软件重启，上一轮生成任务已中断，请重新生成。", now),
        )
        conn.commit()
    finally:
        conn.close()


def get_setting(key: str, default: str = "") -> str:
    row = get_db().execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row is not None else default


def get_settings(keys: list[str] | None = None) -> dict[str, str]:
    if keys:
        placeholders = ",".join("?" for _ in keys)
        rows = get_db().execute(
            f"SELECT key, value FROM settings WHERE key IN ({placeholders})",
            tuple(keys),
        ).fetchall()
    else:
        rows = get_db().execute("SELECT key, value FROM settings").fetchall()
    result = dict(DEFAULT_SETTINGS)
    result.update({row["key"]: row["value"] for row in rows})
    return result


def set_setting(key: str, value: str) -> None:
    get_db().execute(
        """INSERT INTO settings(key, value, updated_at) VALUES (?, ?, ?)
           ON CONFLICT(key) DO UPDATE SET value = excluded.value,
           updated_at = excluded.updated_at""",
        (key, value, now_iso()),
    )
    get_db().commit()


def set_settings(values: dict[str, str]) -> None:
    timestamp = now_iso()
    for key, value in values.items():
        get_db().execute(
            """INSERT INTO settings(key, value, updated_at) VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value,
               updated_at = excluded.updated_at""",
            (key, value, timestamp),
        )
    get_db().commit()


def get_user_by_username(username: str) -> dict[str, Any] | None:
    row = get_db().execute(
        "SELECT * FROM users WHERE username = ? COLLATE NOCASE",
        (username,),
    ).fetchone()
    return row_to_dict(row)


def get_user_by_email(email: str) -> dict[str, Any] | None:
    email = (email or "").strip().lower()
    if not email:
        return None
    row = get_db().execute(
        "SELECT * FROM users WHERE lower(email) = ?",
        (email,),
    ).fetchone()
    return row_to_dict(row)


def get_user(user_id: int) -> dict[str, Any] | None:
    row = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return row_to_dict(row)


def create_user(
    username: str,
    display_name: str,
    email: str,
    password: str,
    avatar_hue: int,
    ip: str = "",
    code: str = "",
) -> dict[str, Any]:
    db = get_db()
    timestamp = now_iso()
    cursor = db.execute(
        """INSERT INTO users
           (username, display_name, email, password_hash, role, is_active,
            avatar_hue, created_at)
           VALUES (?, ?, ?, ?, 'user', 1, ?, ?)""",
        (username, display_name, email, hash_password(password), avatar_hue, timestamp),
    )
    user_id = cursor.lastrowid
    if code:
        db.execute(
            "INSERT INTO invite_uses(code, user_id, ip, created_at) VALUES (?, ?, ?, ?)",
            (code, user_id, ip, timestamp),
        )
    db.commit()
    user = get_user(int(user_id))
    assert user is not None
    return user


def count_invite_uses(code: str) -> int:
    row = get_db().execute(
        "SELECT COUNT(*) AS n FROM invite_uses WHERE code = ?",
        (code,),
    ).fetchone()
    return int(row["n"] if row else 0)


def update_last_login(user_id: int) -> None:
    db = get_db()
    db.execute("UPDATE users SET last_login = ? WHERE id = ?", (now_iso(), user_id))
    db.commit()


def create_project(
    user_id: int,
    title: str,
    prompt: str,
    outline: dict[str, Any],
    template_id: str,
    template: dict[str, Any],
    options: dict[str, Any],
) -> dict[str, Any]:
    db = get_db()
    timestamp = now_iso()
    cursor = db.execute(
        """INSERT INTO projects
           (user_id, title, prompt, outline_json, template_id, template_json,
            options_json, status, slide_count, created_at, updated_at, provider_used)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?, ?, ?)""",
        (
            user_id,
            title,
            prompt,
            safe_json_dumps(outline),
            template_id,
            safe_json_dumps(template),
            safe_json_dumps(options),
            len(outline.get("slides", []) or []),
            timestamp,
            timestamp,
            outline.get("provider_used", ""),
        ),
    )
    db.commit()
    return get_project(int(cursor.lastrowid))  # type: ignore[arg-type]


def get_project(project_id: int) -> dict[str, Any] | None:
    row = get_db().execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    return row_to_dict(row)


def list_projects(user_id: int, limit: int = 100) -> list[dict[str, Any]]:
    rows = get_db().execute(
        """SELECT id, title, prompt, template_id, status, slide_count, file_size,
                  download_count, provider_used, created_at, updated_at, generated_at,
                  substr(outline_json, 1, 0) AS _ignore
           FROM projects WHERE user_id = ? ORDER BY updated_at DESC LIMIT ?""",
        (user_id, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def update_project(project_id: int, **fields: Any) -> None:
    allowed = {
        "title",
        "prompt",
        "outline_json",
        "template_id",
        "template_json",
        "options_json",
        "status",
        "error",
        "pptx_path",
        "pdf_path",
        "preview_path",
        "slide_count",
        "file_size",
        "provider_used",
        "generated_at",
    }
    pairs = [(key, value) for key, value in fields.items() if key in allowed]
    if not pairs:
        return
    pairs.append(("updated_at", now_iso()))
    query = ", ".join(f"{key} = ?" for key, _ in pairs)
    get_db().execute(
        f"UPDATE projects SET {query} WHERE id = ?",
        tuple(value for _, value in pairs) + (project_id,),
    )
    get_db().commit()


def delete_project(project_id: int) -> None:
    get_db().execute("DELETE FROM projects WHERE id = ?", (project_id,))
    get_db().commit()


def increment_download(project_id: int) -> None:
    db = get_db()
    db.execute(
        "UPDATE projects SET download_count = download_count + 1 WHERE id = ?",
        (project_id,),
    )
    db.commit()


def log_event(kind: str, detail: str = "", user_id: int | None = None, ip: str = "") -> None:
    try:
        db = get_db()
        db.execute(
            "INSERT INTO events(user_id, kind, detail, ip, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, kind, detail[:1000], ip[:80], now_iso()),
        )
        db.commit()
    except Exception:
        # Audit logging must never break a user action.
        pass


def get_stats() -> dict[str, Any]:
    db = get_db()
    today = datetime.now(timezone.utc).date().isoformat()

    def scalar(query: str, params: tuple[Any, ...] = ()) -> int:
        row = db.execute(query, params).fetchone()
        return int(row[0]) if row else 0

    total_users = scalar("SELECT COUNT(*) FROM users WHERE role = 'user'")
    active_users = scalar("SELECT COUNT(*) FROM users WHERE role = 'user' AND is_active = 1")
    total_projects = scalar("SELECT COUNT(*) FROM projects")
    ready_projects = scalar("SELECT COUNT(*) FROM projects WHERE status = 'ready'")
    total_downloads = scalar("SELECT COALESCE(SUM(download_count), 0) FROM projects")
    today_users = scalar(
        "SELECT COUNT(*) FROM users WHERE role = 'user' AND substr(created_at, 1, 10) = ?",
        (today,),
    )
    today_projects = scalar(
        "SELECT COUNT(*) FROM projects WHERE substr(created_at, 1, 10) = ?",
        (today,),
    )
    invite_uses = scalar("SELECT COUNT(*) FROM invite_uses")
    total_bytes = scalar("SELECT COALESCE(SUM(file_size), 0) FROM projects WHERE status = 'ready'")

    labels: list[str] = []
    registrations: list[int] = []
    generations: list[int] = []
    for offset in range(6, -1, -1):
        day = (datetime.now(timezone.utc).date() - timedelta(days=offset)).isoformat()
        labels.append(day[5:])
        registrations.append(
            scalar(
                "SELECT COUNT(*) FROM users WHERE role = 'user' AND substr(created_at, 1, 10) = ?",
                (day,),
            )
        )
        generations.append(
            scalar(
                "SELECT COUNT(*) FROM projects WHERE substr(created_at, 1, 10) = ?",
                (day,),
            )
        )

    template_rows = db.execute(
        """SELECT template_id, COUNT(*) AS n FROM projects
           GROUP BY template_id ORDER BY n DESC LIMIT 5"""
    ).fetchall()
    recent_users = db.execute(
        """SELECT id, username, display_name, email, created_at, last_login, is_active
           FROM users WHERE role = 'user' ORDER BY id DESC LIMIT 6"""
    ).fetchall()
    return {
        "total_users": total_users,
        "active_users": active_users,
        "total_projects": total_projects,
        "ready_projects": ready_projects,
        "total_downloads": total_downloads,
        "today_users": today_users,
        "today_projects": today_projects,
        "invite_uses": invite_uses,
        "total_bytes": total_bytes,
        "chart": {
            "labels": labels,
            "registrations": registrations,
            "generations": generations,
        },
        "top_templates": [dict(row) for row in template_rows],
        "recent_users": [dict(row) for row in recent_users],
    }


def admin_users(query: str = "", limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    db = get_db()
    like = f"%{query.strip()}%"
    rows = db.execute(
        """SELECT u.id, u.username, u.display_name, u.email, u.role, u.is_active,
                  u.created_at, u.last_login, u.must_change_password,
                  (SELECT COUNT(*) FROM projects p WHERE p.user_id = u.id) AS project_count
           FROM users u
           WHERE (? = '' OR u.username LIKE ? OR u.display_name LIKE ? OR u.email LIKE ?)
           ORDER BY u.id DESC LIMIT ? OFFSET ?""",
        (query, like, like, like, limit, offset),
    ).fetchall()
    return [dict(row) for row in rows]


def admin_projects(query: str = "", limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    db = get_db()
    like = f"%{query.strip()}%"
    rows = db.execute(
        """SELECT p.id, p.title, p.template_id, p.status, p.slide_count, p.file_size,
                  p.download_count, p.provider_used, p.created_at, p.updated_at,
                  p.generated_at, u.username, u.display_name
           FROM projects p JOIN users u ON u.id = p.user_id
           WHERE (? = '' OR p.title LIKE ? OR u.username LIKE ? OR p.prompt LIKE ?)
           ORDER BY p.id DESC LIMIT ? OFFSET ?""",
        (query, like, like, like, limit, offset),
    ).fetchall()
    return [dict(row) for row in rows]


def recent_events(limit: int = 100) -> list[dict[str, Any]]:
    rows = get_db().execute(
        """SELECT e.id, e.kind, e.detail, e.ip, e.created_at,
                  u.username, u.display_name
           FROM events e LEFT JOIN users u ON u.id = e.user_id
           ORDER BY e.id DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def invite_use_rows(limit: int = 100) -> list[dict[str, Any]]:
    rows = get_db().execute(
        """SELECT i.id, i.code, i.ip, i.created_at, u.username, u.display_name
           FROM invite_uses i JOIN users u ON u.id = i.user_id
           ORDER BY i.id DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]
