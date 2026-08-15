from __future__ import annotations

import os
from typing import Any, Dict

import requests

from .base import BaseNotifier, Message, NotificationError


class PushPlusNotifier(BaseNotifier):
    name = "pushplus"

    def __init__(
        self,
        config: Dict[str, Any],
        session: requests.Session,
        timeout: float = 30,
    ) -> None:
        self.config = config
        self.session = session
        self.timeout = timeout

    def send(self, message: Message) -> None:
        token = str(self.config.get("token") or "").strip()
        if not token:
            token = os.getenv(str(self.config.get("token_env") or "PUSHPLUS_TOKEN"), "").strip()
        if not token:
            raise NotificationError("微信通知配置缺失: PUSHPLUS_TOKEN")

        endpoint = str(self.config.get("endpoint") or "https://www.pushplus.plus/send")
        payload = {
            "token": token,
            "title": message.subject,
            "content": message.html,
            "template": "html",
            "channel": str(self.config.get("channel") or "wechat"),
        }
        try:
            response = self.session.post(endpoint, json=payload, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            if int(data.get("code", -1)) != 200:
                raise NotificationError(f"PushPlus 返回失败: {data}")
        except NotificationError:
            raise
        except Exception as exc:
            raise NotificationError(f"PushPlus 发送失败: {exc}") from exc

