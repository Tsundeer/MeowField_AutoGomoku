# -*- coding: utf-8 -*-
"""GitHub Release 更新检查（轻量：仅比较版本并给出链接，不自动下载）。"""
from __future__ import annotations

import json
import logging
import re
import urllib.request

logger = logging.getLogger("meowfield.update")

REPO = "Tsundeer/MeowField_AutoGomoku"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
_USER_AGENT = "MeowField-AutoGomoku"


def _parse_version(v: str) -> tuple:
    m = re.search(r"(\d+(?:\.\d+)*)", v or "")
    if not m:
        return (0,)
    return tuple(int(x) for x in m.group(1).split("."))


def check_latest(current: str, timeout: float = 8.0) -> dict:
    """查询最新 Release。

    返回 {"has_update": bool, "latest": str, "url": str, "notes": str}；
    网络失败等异常时 has_update=False 且 error 字段带原因。
    """
    result = {"has_update": False, "latest": current, "url": "", "notes": "",
              "error": None}
    try:
        req = urllib.request.Request(
            API_URL, headers={"User-Agent": _USER_AGENT,
                              "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.load(resp)
        tag = data.get("tag_name") or ""
        result["latest"] = tag
        result["url"] = data.get("html_url") or f"https://github.com/{REPO}/releases"
        result["notes"] = (data.get("body") or "")[:500]
        result["has_update"] = _parse_version(tag) > _parse_version(current)
    except Exception as e:  # 网络/接口问题不视为致命
        logger.info("更新检查失败: %s", e)
        result["error"] = str(e)
    return result
