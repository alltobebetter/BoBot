"""Gyazo 图片上传（用于 Wordle 结果图）。"""
from __future__ import annotations

from typing import Optional

import requests

from config import config
from utils.logger import log


def upload_to_gyazo(image_data: bytes) -> Optional[str]:
    """上传 PNG 图片到 Gyazo，返回直链 URL，失败返回 None。"""
    token = config.api.gyazo_token
    if not token:
        log.warning("Gyazo token 未配置，无法上传图片")
        return None

    try:
        resp = requests.post(
            "https://upload.gyazo.com/api/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"imagedata": ("wordle.png", image_data, "image/png")},
            timeout=30,
        )
        if resp.status_code == 200:
            url = resp.json().get("url", "")
            # 转换为直链格式
            if "://gyazo.com/" in url:
                url = url.replace("://gyazo.com/", "://i.gyazo.com/")
                if not url.endswith(".png"):
                    url += ".png"
            return url
        log.error("Gyazo 上传失败", error=f"{resp.status_code} {resp.text[:200]}")
        return None
    except Exception as e:
        log.error("Gyazo 上传异常", exc=e)
        return None
