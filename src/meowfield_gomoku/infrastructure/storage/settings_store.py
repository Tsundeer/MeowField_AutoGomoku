# -*- coding: utf-8 -*-
"""存储基础设施：用户设置（原子写入 + 备份）与应用数据目录。

数据位置镜像 MeowField_AutoPiano 约定：
  %LocalAppData%\\MeowField_AutoGomoku\\
    ├── settings.json   用户偏好（UI 持久化）
    └── logs\\          按日滚动的运行日志
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

SCHEMA_VERSION = 1

DEFAULT_SETTINGS = {
    "schema_version": SCHEMA_VERSION,
    "our_color": "auto",
    "engine": "auto",
    "move_delay": 1.0,
    "engine_threads": 0,
}


def app_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    d = Path(base) / "MeowField_AutoGomoku"
    d.mkdir(parents=True, exist_ok=True)
    return d


def logs_dir() -> Path:
    d = app_data_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def atomic_write_json(path: Path, data: dict) -> None:
    """临时文件 -> 落盘 -> FileReplace 风格替换，保留 .bak 备份。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp",
                                    dir=str(path.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        bak = path.with_suffix(path.suffix + ".bak")
        if path.exists():
            if bak.exists():
                bak.unlink()
            os.replace(str(path), str(bak))
        os.replace(str(tmp), str(path))
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def read_json(path: Path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


class SettingsStore:
    """用户设置：读（带默认值合并与旧版迁移）、写（原子 + .bak）。"""

    def __init__(self, path: Path | None = None):
        self.path = path or (app_data_dir() / "settings.json")

    def load(self) -> dict:
        data = read_json(self.path, None)
        if data is None:
            data = self._read_legacy_project_config()
        merged = dict(DEFAULT_SETTINGS)
        if isinstance(data, dict):
            for k in DEFAULT_SETTINGS:
                if k in data:
                    merged[k] = data[k]
        merged["schema_version"] = SCHEMA_VERSION
        return merged

    def save(self, settings: dict) -> None:
        data = dict(DEFAULT_SETTINGS)
        data.update({k: settings[k] for k in DEFAULT_SETTINGS if k in settings})
        data["schema_version"] = SCHEMA_VERSION
        atomic_write_json(self.path, data)

    def _read_legacy_project_config(self) -> dict | None:
        """迁移 v1.0 的项目根 config.json（读取后不再回写）。"""
        legacy = Path(__file__).resolve().parents[3] / "config.json"
        data = read_json(legacy, None)
        return data if isinstance(data, dict) else None
