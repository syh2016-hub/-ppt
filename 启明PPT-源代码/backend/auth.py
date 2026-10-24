"""Invite-gated registration, login sessions and profile endpoints."""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Any, Callable

from flask import Blueprint, g, jsonify, make_response, request

from .config import ADMIN_CREDENTIALS_FILE, MASTER_INVITE_CODE, SESSION_COOKIE, SESSION_DAYS
from .db import (
    count_invite_uses,
    create_user,
    get_db,
    get_setting,
    get_user,
    get_user_by_email,
    get_user_by_username,
    log_event,
    update_last_login,
)
from .mailer import (
    MailConfigError,
    MailSendError,
    email_verification_ready,
    send_email,
    valid_email,
    verification_email,
)
from .security import (
    client_ip,
    login_throttle,
    new_session_token,
    safe_compare_invite,
    token_digest,
    valid_password,
    valid_username,
    verify_password,
)
from .utils import clean_text, generate_avatar_hue, now_iso

auth_bp = Blueprint("auth", __name__)

SESSION_LAST_SEEN_INTERVAL = 3600
CODE_TTL_SECONDS = 600
CODE_COOLDOWN_SECONDS = 60
CODE_MAX_ATTEMPTS = 5
CODE_IP_WINDOW_SECONDS = 600
CODE_IP_LIMIT = 10


def _hash_code(email: str, code: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256",
        f"{email.lower()}:{code}".encode("utf-8"),
        salt.encode("ascii"),
        90_000,
    ).hex()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _verify_email_code(email: str, code: str) -> tuple[bool, str, int | None]:
    db = get_db()
    row = db.execute(
        """SELECT id, code_hash, salt, expires_at, attempts, max_attempts
           FROM email_codes
           WHERE email = ? AND purpose = 'register' AND used_at IS NULL
           ORDER BY id DESC LIMIT 1""",
        (email.lower(),),
    ).fetchone()
    if row is None:
        return False, "请先获取邮箱验证码", None
    expires = _parse_iso(row["expires_at"])
    if expires is None or expires < datetime.now(timezone.utc):
        return False, "验证码已过期，请重新获取", None
    if int(row["attempts"]) >= int(row["max_attempts"]):
        return False, "验证码尝试次数过多，请重新获取", None
    expected = _hash_code(email, code, row["salt"])
    if not hmac.compare_digest(expected, row["code_hash"]):
        attempts = int(row["attempts"]) + 1
        db.execute("UPDATE email_codes SET attempts = ? WHERE id = ?", (attempts, row["id"]))
        db.commit()
        if attempts >= int(row["max_attempts"]):
            return False, "验证码尝试次数过多，请重新获取", None
        return False, f"验证码不正确，还可以尝试 {int(row['max_attempts']) - attempts} 次", None
    return True, "", int(row["id"])


def public_user(user: dict[str, Any] | None) -> dict[str, Any] | None:
    if not user:
        return None
    return {
        "id": user["id"],
        "username": user["username"],
        "display_name": user["display_name"],
        "email": user["email"],
        "role": user["role"],
        "avatar_hue": user["avatar_hue"],
        "created_at": user["created_at"],
        "last_login": user["last_login"],
        "must_change_password": bool(user.get("must_change_password")),
    }


def _session_query(token: str):
    return get_db().execute(
        """SELECT u.*, s.expires_at, s.token_hash
           FROM sessions s JOIN users u ON u.id = s.user_id
           WHERE s.token_hash = ?""",
        (token_digest(token),),
    ).fetchone()


def load_current_user() -> dict[str, Any] | None:
    if "current_user" in g:
        return g.current_user
    g.current_user = None
    token = request.cookies.get(SESSION_COOKIE, "")
    if not token or len(token) > 200:
        return None
    row = _session_query(token)
    if row is None:
        return None
    user = dict(row)
    expires_at = user.pop("expires_at", "")
    try:
        expiry = datetime.fromisoformat(expires_at)
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None
    if expiry < datetime.now(timezone.utc):
        try:
            get_db().execute("DELETE FROM sessions WHERE token_hash = ?", (token_digest(token),))
            get_db().commit()
        except Exception:
            pass
        return None
    if not user.get("is_active"):
        return None
    # Touch the session at most once an hour.
    try:
        last_seen = datetime.fromisoformat(user.get("last_seen") or now_iso())
        if (datetime.now(timezone.utc) - last_seen).total_seconds() > SESSION_LAST_SEEN_INTERVAL:
            get_db().execute(
                "UPDATE sessions SET last_seen = ? WHERE token_hash = ?",
                (now_iso(), token_digest(token)),
            )
            get_db().commit()
    except Exception:
        pass
    g.current_user = user
    return user


def current_user() -> dict[str, Any] | None:
    if "current_user" in g:
        return g.current_user
    return load_current_user()


def login_required(view: Callable):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_user() is None:
            return jsonify({"ok": False, "error": "请先登录后再继续", "code": "UNAUTHORIZED"}), 401
        return view(*args, **kwargs)

    return wrapped


def admin_required(view: Callable):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if user is None:
            return jsonify({"ok": False, "error": "请先登录管理员账号", "code": "UNAUTHORIZED"}), 401
        if user.get("role") != "admin":
            return jsonify({"ok": False, "error": "没有管理员权限", "code": "FORBIDDEN"}), 403
        return view(*args, **kwargs)

    return wrapped


def _start_session(user_id: int, response):
    token = new_session_token()
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=SESSION_DAYS)
    db = get_db()
    db.execute(
        """INSERT INTO sessions(token_hash, user_id, created_at, expires_at, last_seen, ip, user_agent)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            token_digest(token),
            user_id,
            now.isoformat(timespec="seconds"),
            expires.isoformat(timespec="seconds"),
            now.isoformat(timespec="seconds"),
            client_ip(request),
            request.headers.get("User-Agent", "")[:300],
        ),
    )
    db.commit()
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_DAYS * 24 * 3600,
        httponly=True,
        samesite="Lax",
        secure=request.is_secure,
        path="/",
    )
    return response


def _revoke_current_session() -> None:
    token = request.cookies.get(SESSION_COOKIE, "")
    if token:
        db = get_db()
        db.execute("DELETE FROM sessions WHERE token_hash = ?", (token_digest(token),))
        db.commit()


@auth_bp.get("/api/auth/me")
def me():
    user = current_user()
    return jsonify(
        {
            "ok": True,
            "user": public_user(user),
            "admin": bool(user and user.get("role") == "admin"),
        }
    )


@auth_bp.post("/api/auth/send-code")
def send_code():
    if get_setting("registration_enabled", "1") != "1":
        return jsonify({"ok": False, "error": "管理员已暂停新用户注册"}), 403
    if get_setting("email_verification_enabled", "0") != "1":
        return jsonify({"ok": False, "error": "当前未开启邮箱验证码"}), 403
    payload = request.get_json(silent=True) or {}
    invite = clean_text(payload.get("invite_code"), 80).strip()
    if not safe_compare_invite(invite, MASTER_INVITE_CODE):
        return jsonify({"ok": False, "error": "邀请码不正确，无法获取验证码", "field": "invite_code"}), 400
    email = clean_text(payload.get("email"), 120).strip().lower()
    if not valid_email(email):
        return jsonify({"ok": False, "error": "请输入有效的邮箱地址", "field": "email"}), 400
    if get_user_by_email(email):
        return jsonify({"ok": False, "error": "这个邮箱已经注册过", "field": "email"}), 409

    db = get_db()
    ip = client_ip(request)
    now = datetime.now(timezone.utc)
    cutoff_ip = (now - timedelta(seconds=CODE_IP_WINDOW_SECONDS)).isoformat(timespec="seconds")
    ip_count = db.execute(
        "SELECT COUNT(*) FROM events WHERE kind = 'send_code' AND ip = ? AND created_at >= ?",
        (ip, cutoff_ip),
    ).fetchone()
    if ip_count and int(ip_count[0]) >= CODE_IP_LIMIT:
        return jsonify({"ok": False, "error": "发送过于频繁，请稍后再试"}), 429

    last = db.execute(
        "SELECT created_at FROM email_codes WHERE email = ? ORDER BY id DESC LIMIT 1",
        (email,),
    ).fetchone()
    last_time = _parse_iso(last["created_at"]) if last else None
    if last_time is not None:
        elapsed = (now - last_time).total_seconds()
        if elapsed < CODE_COOLDOWN_SECONDS:
            wait = max(1, int(CODE_COOLDOWN_SECONDS - elapsed))
            return (
                jsonify({"ok": False, "error": f"请 {wait} 秒后再发送验证码", "cooldown": wait}),
                429,
            )
    hour_cutoff = (now - timedelta(hours=1)).isoformat(timespec="seconds")
    hour_count = db.execute(
        "SELECT COUNT(*) FROM email_codes WHERE email = ? AND created_at >= ?",
        (email, hour_cutoff),
    ).fetchone()
    if hour_count and int(hour_count[0]) >= 5:
        return jsonify({"ok": False, "error": "该邮箱发送次数过多，请一小时后再试"}), 429

    if not email_verification_ready():
        return jsonify({"ok": False, "error": "管理员尚未完成发件邮箱配置，请联系管理员"}), 503

    code = f"{secrets.randbelow(1_000_000):06d}"
    salt = secrets.token_hex(16)
    created = now.isoformat(timespec="seconds")
    expires = (now + timedelta(seconds=CODE_TTL_SECONDS)).isoformat(timespec="seconds")
    db.execute(
        "UPDATE email_codes SET used_at = ? WHERE email = ? AND purpose = 'register' AND used_at IS NULL",
        (created, email),
    )
    cursor = db.execute(
        """INSERT INTO email_codes
           (email, code_hash, salt, purpose, expires_at, attempts, max_attempts, created_at, ip)
           VALUES (?, ?, ?, 'register', ?, 0, ?, ?, ?)""",
        (
            email,
            _hash_code(email, code, salt),
            salt,
            expires,
            CODE_MAX_ATTEMPTS,
            created,
            ip,
        ),
    )
    db.commit()
    log_event("send_code", f"发送注册验证码到 {email}", ip=ip)
    subject, text, html = verification_email(code, minutes=CODE_TTL_SECONDS // 60)
    try:
        send_email(email, subject, text, html)
    except (MailConfigError, MailSendError) as exc:
        db.execute("UPDATE email_codes SET used_at = ? WHERE id = ?", (now_iso(), cursor.lastrowid))
        db.commit()
        return jsonify({"ok": False, "error": str(exc)}), 503
    return jsonify(
        {
            "ok": True,
            "message": "验证码已发送，请检查收件箱和垃圾邮件",
            "cooldown": CODE_COOLDOWN_SECONDS,
            "expires_in": CODE_TTL_SECONDS,
        }
    )


@auth_bp.post("/api/auth/register")
def register():
    if get_setting("registration_enabled", "1") != "1":
        return jsonify({"ok": False, "error": "管理员已暂停新用户注册"}), 403
    payload = request.get_json(silent=True) or {}
    invite = clean_text(payload.get("invite_code"), 80).strip()
    if not safe_compare_invite(invite, MASTER_INVITE_CODE):
        log_event("register_denied", "邀请码不正确", ip=client_ip(request))
        return jsonify({"ok": False, "error": "邀请码不正确，无法注册", "field": "invite_code"}), 400
    username = clean_text(payload.get("username"), 40).strip()
    display_name = clean_text(payload.get("display_name"), 40).strip() or username
    email = clean_text(payload.get("email"), 120).strip().lower()
    password = str(payload.get("password") or "")
    code_required = get_setting("email_verification_enabled", "0") == "1"
    email_code = clean_text(payload.get("email_code"), 12).strip()
    if not valid_username(username):
        return jsonify({"ok": False, "error": "用户名需为 3—20 位中文、字母、数字或下划线", "field": "username"}), 400
    if not valid_password(password):
        return jsonify({"ok": False, "error": "密码长度需为 6—72 位", "field": "password"}), 400
    if code_required and not email:
        return jsonify({"ok": False, "error": "请填写用于接收验证码的邮箱", "field": "email"}), 400
    if email and not valid_email(email):
        return jsonify({"ok": False, "error": "邮箱格式不正确", "field": "email"}), 400
    if get_user_by_username(username):
        return jsonify({"ok": False, "error": "这个用户名已经被使用", "field": "username"}), 409
    if email and get_user_by_email(email):
        return jsonify({"ok": False, "error": "这个邮箱已经注册过", "field": "email"}), 409
    code_row_id: int | None = None
    if code_required:
        if not email_code:
            return jsonify({"ok": False, "error": "请填写邮箱验证码", "field": "email_code"}), 400
        valid, message, code_row_id = _verify_email_code(email, email_code)
        if not valid:
            return jsonify({"ok": False, "error": message, "field": "email_code"}), 400
    user = create_user(
        username=username,
        display_name=display_name[:30],
        email=email,
        password=password,
        avatar_hue=generate_avatar_hue(username),
        ip=client_ip(request),
        code=MASTER_INVITE_CODE,
    )
    if code_row_id is not None:
        db = get_db()
        db.execute(
            "UPDATE email_codes SET used_at = ? WHERE id = ? AND used_at IS NULL",
            (now_iso(), code_row_id),
        )
        db.commit()
    log_event("register", f"使用邀请码注册：{username}", user_id=user["id"], ip=client_ip(request))
    log_event("invite_used", f"邀请码 {MASTER_INVITE_CODE} 已使用", user_id=user["id"], ip=client_ip(request))
    response = make_response(
        jsonify(
            {
                "ok": True,
                "user": public_user(user),
                "message": "注册成功，欢迎来到启明 PPT",
                "invite_uses": count_invite_uses(MASTER_INVITE_CODE),
            }
        )
    )
    update_last_login(user["id"])
    return _start_session(int(user["id"]), response)


@auth_bp.post("/api/auth/login")
def login():
    payload = request.get_json(silent=True) or {}
    username = clean_text(payload.get("username"), 80).strip()
    password = str(payload.get("password") or "")
    ip = client_ip(request)
    if not username or not password:
        return jsonify({"ok": False, "error": "请输入账号和密码"}), 400
    if not login_throttle.allowed(ip, username):
        wait = login_throttle.retry_after(ip, username)
        return (
            jsonify({"ok": False, "error": f"尝试次数过多，请 {max(1, wait // 60)} 分钟后再试"}),
            429,
        )
    user = get_user_by_username(username)
    if user is None or not verify_password(password, user["password_hash"]):
        login_throttle.record_failure(ip, username)
        log_event("login_failed", f"登录失败：{username}", ip=ip)
        return jsonify({"ok": False, "error": "账号或密码不正确"}), 401
    if not user.get("is_active"):
        return jsonify({"ok": False, "error": "该账号已被停用，请联系管理员"}), 403
    login_throttle.clear(ip, username)
    update_last_login(int(user["id"]))
    log_event("login", f"登录成功：{user['username']}", user_id=int(user["id"]), ip=ip)
    response = make_response(
        jsonify(
            {
                "ok": True,
                "user": public_user(user),
                "message": "登录成功",
                "must_change_password": bool(user.get("must_change_password")),
            }
        )
    )
    return _start_session(int(user["id"]), response)


@auth_bp.post("/api/auth/logout")
def logout():
    user = current_user()
    if user:
        log_event("logout", f"退出登录：{user['username']}", user_id=int(user["id"]), ip=client_ip(request))
    _revoke_current_session()
    response = make_response(jsonify({"ok": True, "message": "已退出登录"}))
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@auth_bp.post("/api/auth/password")
@login_required
def change_password():
    user = current_user()
    payload = request.get_json(silent=True) or {}
    current = str(payload.get("current_password") or "")
    new = str(payload.get("new_password") or "")
    if not verify_password(current, user["password_hash"]):
        return jsonify({"ok": False, "error": "当前密码不正确"}), 400
    if not valid_password(new):
        return jsonify({"ok": False, "error": "新密码长度需为 6—72 位"}), 400
    if current == new:
        return jsonify({"ok": False, "error": "新密码不能与当前密码相同"}), 400
    from .security import hash_password

    db = get_db()
    db.execute(
        "UPDATE users SET password_hash = ?, must_change_password = 0 WHERE id = ?",
        (hash_password(new), user["id"]),
    )
    # Keep the current session, revoke all others.
    token = request.cookies.get(SESSION_COOKIE, "")
    db.execute(
        "DELETE FROM sessions WHERE user_id = ? AND token_hash <> ?",
        (user["id"], token_digest(token)),
    )
    db.commit()
    if user.get("role") == "admin":
        try:
            ADMIN_CREDENTIALS_FILE.unlink(missing_ok=True)
        except OSError:
            pass
    log_event("password_changed", "用户修改密码", user_id=int(user["id"]), ip=client_ip(request))
    return jsonify({"ok": True, "message": "密码已更新，其他设备上的登录已失效"})


@auth_bp.patch("/api/auth/profile")
@login_required
def update_profile():
    user = current_user()
    payload = request.get_json(silent=True) or {}
    display_name = clean_text(payload.get("display_name"), 30).strip()
    email = clean_text(payload.get("email"), 120).strip().lower()
    if not display_name:
        return jsonify({"ok": False, "error": "昵称不能为空"}), 400
    if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return jsonify({"ok": False, "error": "邮箱格式不正确"}), 400
    existing = get_user_by_email(email) if email else None
    if existing and existing["id"] != user["id"]:
        return jsonify({"ok": False, "error": "这个邮箱已被其他账号使用"}), 409
    db = get_db()
    db.execute(
        "UPDATE users SET display_name = ?, email = ? WHERE id = ?",
        (display_name, email, user["id"]),
    )
    db.commit()
    return jsonify({"ok": True, "user": public_user(get_user(int(user["id"]))), "message": "资料已保存"})


@auth_bp.get("/api/auth/sessions")
@login_required
def sessions():
    user = current_user()
    rows = get_db().execute(
        """SELECT token_hash, created_at, last_seen, ip, user_agent
           FROM sessions WHERE user_id = ? ORDER BY last_seen DESC""",
        (user["id"],),
    ).fetchall()
    current_hash = token_digest(request.cookies.get(SESSION_COOKIE, ""))
    return jsonify(
        {
            "ok": True,
            "sessions": [
                {
                    "current": row["token_hash"] == current_hash,
                    "created_at": row["created_at"],
                    "last_seen": row["last_seen"],
                    "ip": row["ip"],
                    "device": "当前设备" if row["token_hash"] == current_hash else (row["user_agent"][:80] or "其他设备"),
                }
                for row in rows
            ],
        }
    )


@auth_bp.post("/api/auth/sessions/revoke")
@login_required
def revoke_other_sessions():
    user = current_user()
    token = request.cookies.get(SESSION_COOKIE, "")
    db = get_db()
    db.execute(
        "DELETE FROM sessions WHERE user_id = ? AND token_hash <> ?",
        (user["id"], token_digest(token)),
    )
    db.commit()
    return jsonify({"ok": True, "message": "其他设备已全部退出"})
