from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage
from typing import Any, Dict, List

from .base import BaseNotifier, Message, NotificationError


def _value(config: Dict[str, Any], key: str, default: str = "") -> str:
    direct = config.get(key)
    if direct is not None and str(direct).strip():
        return str(direct).strip()
    env_name = config.get(f"{key}_env")
    return os.getenv(str(env_name), "").strip() if env_name else default


class EmailNotifier(BaseNotifier):
    name = "email"

    def __init__(self, config: Dict[str, Any], timeout: float = 30) -> None:
        self.config = config
        self.timeout = timeout

    def _settings(self) -> Dict[str, Any]:
        host = _value(self.config, "host")
        username = _value(self.config, "username")
        password = _value(self.config, "password")
        sender = _value(self.config, "from") or username
        recipients: List[str] = [
            item.strip()
            for item in _value(self.config, "to").replace(";", ",").split(",")
            if item.strip()
        ]
        missing = [
            name
            for name, value in (
                ("SMTP_HOST", host),
                ("SMTP_USERNAME", username),
                ("SMTP_PASSWORD", password),
                ("SMTP_FROM", sender),
                ("SMTP_TO", recipients),
            )
            if not value
        ]
        if missing:
            raise NotificationError("邮件配置缺失: " + ", ".join(missing))
        return {
            "host": host,
            "port": int(_value(self.config, "port", "465")),
            "username": username,
            "password": password,
            "sender": sender,
            "recipients": recipients,
        }

    def send(self, message: Message) -> None:
        settings = self._settings()
        email = EmailMessage()
        email["Subject"] = message.subject
        email["From"] = settings["sender"]
        email["To"] = ", ".join(settings["recipients"])
        email.set_content(message.text)
        email.add_alternative(message.html, subtype="html")

        try:
            if bool(self.config.get("use_ssl", True)):
                with smtplib.SMTP_SSL(
                    settings["host"],
                    settings["port"],
                    timeout=self.timeout,
                    context=ssl.create_default_context(),
                ) as smtp:
                    smtp.login(settings["username"], settings["password"])
                    smtp.send_message(email)
            else:
                with smtplib.SMTP(
                    settings["host"], settings["port"], timeout=self.timeout
                ) as smtp:
                    smtp.ehlo()
                    if bool(self.config.get("use_starttls", True)):
                        smtp.starttls(context=ssl.create_default_context())
                        smtp.ehlo()
                    smtp.login(settings["username"], settings["password"])
                    smtp.send_message(email)
        except Exception as exc:
            raise NotificationError(f"SMTP 发送失败: {exc}") from exc

