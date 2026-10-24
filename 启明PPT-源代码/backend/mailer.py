"""SMTP delivery for registration verification codes.

The module is intentionally small and dependency-free so it can be bundled into
the desktop app. For automated tests, setting QIMING_EMAIL_CAPTURE_DIR writes
the email to a local .eml file instead of contacting an SMTP server.
"""
from __future__ import annotations

import os
import re
import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path
from typing import Any

from .db import get_settings

SMTP_SECURITY = {"ssl", "starttls", "none"}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class MailConfigError(RuntimeError):
    pass


class MailSendError(RuntimeError):
    pass


def valid_email(value: str) -> bool:
    return bool(EMAIL_RE.fullmatch((value or "").strip())) and len(value) <= 160


def smtp_config() -> dict[str, Any]:
    values = get_settings(
        [
            "smtp_host",
            "smtp_port",
            "smtp_security",
            "smtp_username",
            "smtp_password",
            "smtp_from",
            "smtp_from_name",
        ]
    )
    security = (values.get("smtp_security") or "ssl").lower()
    if security not in SMTP_SECURITY:
        security = "ssl"
    try:
        port = int(values.get("smtp_port") or (465 if security == "ssl" else 587))
    except (TypeError, ValueError):
        port = 465 if security == "ssl" else 587
    return {
        "host": (values.get("smtp_host") or "").strip(),
        "port": port,
        "security": security,
        "username": (values.get("smtp_username") or "").strip(),
        "password": values.get("smtp_password") or "",
        "from_addr": (values.get("smtp_from") or values.get("smtp_username") or "").strip(),
        "from_name": (values.get("smtp_from_name") or "启明 PPT").strip()[:40],
    }


def email_verification_ready() -> bool:
    config = smtp_config()
    return bool(config["host"] and valid_email(config["from_addr"]))


def _capture_path(to_addr: str) -> Path | None:
    capture = os.environ.get("QIMING_EMAIL_CAPTURE_DIR", "").strip()
    if not capture:
        return None
    root = Path(capture)
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    safe = re.sub(r"[^0-9A-Za-z_.@-]+", "_", to_addr)[:60]
    return root / f"{stamp}_{safe}.eml"


def send_email(to_addr: str, subject: str, text: str, html: str | None = None) -> dict[str, Any]:
    """Send one plain/HTML email. Raises MailConfigError/MailSendError."""
    to_addr = (to_addr or "").strip()
    if not valid_email(to_addr):
        raise MailConfigError("收件邮箱格式不正确")

    config = smtp_config()
    if not config["host"]:
        raise MailConfigError("管理员尚未配置 SMTP 邮件服务")
    if not valid_email(config["from_addr"]):
        raise MailConfigError("管理员尚未配置有效的发件邮箱")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr((config["from_name"], config["from_addr"]))
    message["To"] = to_addr
    message["Date"] = datetime.now().astimezone().strftime("%a, %d %b %Y %H:%M:%S %z")
    message.set_content(text)
    if html:
        message.add_alternative(html, subtype="html")

    capture = _capture_path(to_addr)
    if capture is not None:
        capture.write_bytes(message.as_bytes())
        return {"ok": True, "mode": "capture", "path": str(capture)}

    try:
        context = ssl.create_default_context()
        if config["security"] == "ssl":
            client: smtplib.SMTP = smtplib.SMTP_SSL(
                config["host"], config["port"], timeout=25, context=context
            )
        else:
            client = smtplib.SMTP(config["host"], config["port"], timeout=25)
            client.ehlo()
            if config["security"] == "starttls":
                client.starttls(context=context)
                client.ehlo()
        if config["username"]:
            client.login(config["username"], config["password"])
        client.send_message(message)
        try:
            client.quit()
        except Exception:
            pass
        return {"ok": True, "mode": "smtp"}
    except smtplib.SMTPAuthenticationError as exc:
        raise MailSendError("SMTP 登录失败，请检查邮箱地址和授权码（不是登录密码）") from exc
    except smtplib.SMTPException as exc:
        raise MailSendError(f"SMTP 发送失败：{str(exc)[:160]}") from exc
    except OSError as exc:
        raise MailSendError(f"无法连接 SMTP 服务器：{str(exc)[:160]}") from exc


def verification_email(code: str, minutes: int = 10) -> tuple[str, str, str]:
    subject = "启明 PPT 注册验证码"
    text = (
        f"你的启明 PPT 注册验证码是：{code}\n\n"
        f"验证码 {minutes} 分钟内有效，只能使用一次。\n"
        "如果这不是你的操作，请忽略这封邮件。\n\n"
        "—— 启明 PPT"
    )
    html = f"""<!doctype html>
<html><body style="margin:0;padding:0;background:#f4f0e7;font-family:'Microsoft YaHei',Arial,sans-serif;color:#16181d">
  <div style="max-width:560px;margin:28px auto;background:#fffdf9;border:1px solid #e5ded1;border-radius:18px;overflow:hidden">
    <div style="background:#0b0f19;color:#f8f3e8;padding:24px 28px">
      <div style="font-size:18px;font-weight:700;letter-spacing:.04em">启明 PPT</div>
      <div style="font-size:9px;letter-spacing:.22em;color:rgba(248,243,232,.4);margin-top:4px">QIMING STUDIO</div>
    </div>
    <div style="padding:30px 28px">
      <p style="font-size:13px;color:#6e6a62;margin:0 0 18px">你正在注册启明 PPT。请在注册页面输入下面的验证码：</p>
      <div style="font-size:34px;font-weight:700;letter-spacing:.24em;color:#e54b2a;background:#fff3ec;border:1px solid #ffd6c8;border-radius:12px;padding:16px 20px;text-align:center">{code}</div>
      <p style="font-size:11px;color:#9a948a;line-height:1.7;margin:18px 0 0">验证码 {minutes} 分钟内有效，只能使用一次。<br>如果这不是你的操作，请忽略这封邮件。</p>
    </div>
  </div>
</body></html>"""
    return subject, text, html
