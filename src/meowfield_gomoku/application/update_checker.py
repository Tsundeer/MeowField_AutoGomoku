# -*- coding: utf-8 -*-
"""GitHub Release 更新检查（多端点降级 + 本地缓存，不自动下载）。

端点优先级（任一成功即返回）：
1. REST API + ETag 条件请求：304 Not Modified 不消耗匿名限额（60 次/时/IP），
   并把最近一次结果（tag/ETag/时间）缓存到 %LocalAppData%；
2. releases.atom 订阅源：无 REST 限额，解析最新条目中的 /releases/tag/<tag>；
3. releases/latest 页面 302 重定向：最终 URL 含 /releases/tag/<tag>。

全部失败时返回 error，界面提示手动访问。检查结果本地缓存 1 小时内直接复用，
避免每次启动都打接口。
"""
from __future__ import annotations

import json
import logging
import re
import time
import urllib.request

logger = logging.getLogger("meowfield.update")

REPO = "Tsundeer/MeowField_AutoGomoku"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
ATOM_URL = f"https://github.com/{REPO}/releases.atom"
PAGE_URL = f"https://github.com/{REPO}/releases/latest"
RELEASES_URL = f"https://github.com/{REPO}/releases"
_USER_AGENT = "MeowField-AutoGomoku"

_CACHE_TTL = 3600  # 结果缓存 1 小时
_TAG_RE = re.compile(r"releases/tag/([^\"?<>\s]+)")


def _parse_version(v: str) -> tuple:
    m = re.search(r"(\d+(?:\.\d+)*)", v or "")
    if not m:
        return (0,)
    return tuple(int(x) for x in m.group(1).split("."))


def _cache_path():
    from ..infrastructure.storage.settings_store import app_data_dir
    return app_data_dir() / "update_cache.json"


def _load_cache() -> dict:
    try:
        with open(_cache_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cache(data: dict) -> None:
    try:
        with open(_cache_path(), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception:
        pass


def _http_get(url: str, headers: dict | None = None, timeout: float = 8.0):
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT,
                                               **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, dict(resp.headers), resp.read()


def _via_api(etag: str | None) -> dict | None:
    headers = {"Accept": "application/vnd.github+json"}
    if etag:
        headers["If-None-Match"] = etag
    try:
        status, hdrs, body = _http_get(API_URL, headers)
    except Exception as e:
        logger.info("api 端点失败: %s", e)
        return None
    if status == 304:
        return {"__not_modified__": True}
    if status != 200:
        return None
    try:
        data = json.loads(body.decode("utf-8", "replace"))
        return {"tag": data.get("tag_name") or "",
                "url": data.get("html_url") or RELEASES_URL,
                "notes": (data.get("body") or "")[:500],
                "etag": hdrs.get("ETag") or hdrs.get("etag") or ""}
    except Exception as e:
        logger.info("api 响应解析失败: %s", e)
        return None


def _via_atom() -> dict | None:
    try:
        status, _h, body = _http_get(ATOM_URL)
    except Exception as e:
        logger.info("atom 端点失败: %s", e)
        return None
    if status != 200:
        return None
    text = body.decode("utf-8", "replace")
    m = _TAG_RE.search(text)
    if not m:
        return None
    from urllib.parse import unquote
    return {"tag": unquote(m.group(1)), "url": RELEASES_URL, "notes": "", "etag": ""}


def _via_page() -> dict | None:
    try:
        status, _h, _body = _http_get(PAGE_URL)
    except Exception as e:
        logger.info("page 端点失败: %s", e)
        return None
    if status != 200:
        return None
    # urllib 自动跟随重定向后无法直接拿最终 URL，改从 opener 取；
    # 简化：请求 /releases/latest 已重定向到 tag 页，body 内含 canonical 链接
    try:
        status, _h, body = _http_get(RELEASES_URL + "/latest")
    except Exception:
        return None
    m = _TAG_RE.search(body.decode("utf-8", "replace"))
    if not m:
        return None
    from urllib.parse import unquote
    return {"tag": unquote(m.group(1)), "url": RELEASES_URL, "notes": "", "etag": ""}


def check_latest(current: str, force: bool = False, timeout: float = 8.0) -> dict:
    """查询最新 Release，带缓存与多端点降级。"""
    result = {"has_update": False, "latest": current, "url": RELEASES_URL,
              "notes": "", "error": None, "cached": False}

    cache = _load_cache()
    age_ok = (time.time() - cache.get("ts", 0)) < _CACHE_TTL
    if not force and age_ok and cache.get("tag"):
        result.update(latest=cache["tag"], url=cache.get("url", RELEASES_URL),
                      cached=True)
        result["has_update"] = _parse_version(result["latest"]) > _parse_version(current)
        return result

    # 1) API + ETag
    api = _via_api(cache.get("etag"))
    if api and api.get("__not_modified__"):
        tag = cache.get("tag")
        if tag:
            result.update(latest=tag, url=cache.get("url", RELEASES_URL))
            result["has_update"] = _parse_version(tag) > _parse_version(current)
            return result
        api = None  # 无缓存可用，降级
    if api and api.get("tag"):
        result.update(latest=api["tag"], url=api["url"], notes=api["notes"])
        result["has_update"] = _parse_version(api["tag"]) > _parse_version(current)
        _save_cache({"ts": time.time(), "tag": api["tag"], "url": api["url"],
                     "etag": api.get("etag", "")})
        return result

    # 2) atom
    atom = _via_atom()
    if atom and atom.get("tag"):
        result.update(latest=atom["tag"], url=atom["url"])
        result["has_update"] = _parse_version(atom["tag"]) > _parse_version(current)
        _save_cache({"ts": time.time(), "tag": atom["tag"], "url": atom["url"],
                     "etag": ""})
        return result

    # 3) HTML 页面
    page = _via_page()
    if page and page.get("tag"):
        result.update(latest=page["tag"], url=page["url"])
        result["has_update"] = _parse_version(page["tag"]) > _parse_version(current)
        _save_cache({"ts": time.time(), "tag": page["tag"], "url": page["url"],
                     "etag": ""})
        return result

    # 全部失败：1 小时内的旧缓存也拿来用（标注 cached）
    if cache.get("tag"):
        result.update(latest=cache["tag"], url=cache.get("url", RELEASES_URL),
                      cached=True)
        result["has_update"] = _parse_version(result["latest"]) > _parse_version(current)
        result["error"] = "网络失败，以下为缓存结果"
        return result

    result["error"] = "无法连接更新服务（网络受限），请手动访问发布页"
    return result
