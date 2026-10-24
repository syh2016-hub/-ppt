"""Application paths, constants and persisted runtime configuration."""
from __future__ import annotations

import json
import os
import secrets
import sys
from pathlib import Path
from typing import Any

APP_NAME = "启明 PPT"
APP_NAME_EN = "QIMING STUDIO"
APP_VERSION = "1.5.0"
MASTER_INVITE_CODE = "songyonghao2016"
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = os.environ.get("QIMING_ADMIN_PASSWORD", "Admin@2016")
SESSION_COOKIE = "qm_session"
SESSION_DAYS = 30
MAX_SLIDES = 50
MIN_SLIDES = 6

APP_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = APP_ROOT / "frontend"
IS_FROZEN = bool(getattr(sys, "frozen", False))
if IS_FROZEN:
    bundle_root = Path(getattr(sys, "_MEIPASS", APP_ROOT))
    FRONTEND_DIR = bundle_root / "frontend"


def _default_data_dir() -> Path:
    override = os.environ.get("QIMING_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if base:
        return Path(base) / "QimingPPT"
    return Path.home() / ".qimingppt"


DATA_DIR = _default_data_dir()
DB_PATH = DATA_DIR / "qiming.db"
PROJECTS_DIR = DATA_DIR / "projects"
CACHE_DIR = DATA_DIR / "cache"
ONLINE_CACHE_DIR = CACHE_DIR / "online"
VOICE_DIR = CACHE_DIR / "voice"
REFERENCES_DIR = DATA_DIR / "references"
LOG_DIR = DATA_DIR / "logs"
SETTINGS_FILE = DATA_DIR / "runtime.json"
ADMIN_CREDENTIALS_FILE = DATA_DIR / "管理员初始账号.txt"

DEFAULT_SETTINGS: dict[str, str] = {
    "ai_provider": "auto",
    "deepseek_api_key": "",
    "deepseek_model": "deepseek-chat",
    "deepseek_base_url": "https://api.deepseek.com",
    "doubao_api_key": "",
    "doubao_model": "doubao-seed-1-6-250615",
    "doubao_base_url": "https://ark.cn-beijing.volces.com/api/v3",
    "custom_api_key": "",
    "custom_model": "",
    "custom_base_url": "",
    "online_search_enabled": "1",
    "online_templates_enabled": "1",
    "allow_user_keys": "1",
    "brand_tagline": "把想法，讲成一场好戏",
    "registration_enabled": "1",
    "email_verification_enabled": "0",
    "smtp_host": "",
    "smtp_port": "465",
    "smtp_security": "ssl",
    "smtp_username": "",
    "smtp_password": "",
    "smtp_from": "",
    "smtp_from_name": "启明 PPT",
    "default_animations": "1",
    "default_audio": "0",
    "default_video": "0",
}


def ensure_directories() -> None:
    for path in (DATA_DIR, PROJECTS_DIR, CACHE_DIR, ONLINE_CACHE_DIR, VOICE_DIR, REFERENCES_DIR, LOG_DIR):
        path.mkdir(parents=True, exist_ok=True)


def load_runtime() -> dict[str, Any]:
    """Load the small runtime file that stores the Flask signing secret."""
    ensure_directories()
    if SETTINGS_FILE.exists():
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (OSError, ValueError):
            pass
    data = {
        "secret_key": secrets.token_hex(32),
        "created_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
    }
    SETTINGS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def save_runtime(data: dict[str, Any]) -> None:
    ensure_directories()
    SETTINGS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def resource_path(*parts: str) -> Path:
    return FRONTEND_DIR.joinpath(*parts)
