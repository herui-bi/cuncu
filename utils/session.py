"""登录态复用：保存/读取聊惠保等 H5 的 localStorage 登录信息。

H5 登录后把 token、userId、openId 写入 localStorage，再次打开页面时
只要这些键存在，缴费人信息就会自动带出为只读模式，无需重新填写与短信验证。
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUTH_DIR = ROOT / "auth"

# 复用登录态所需的关键键，缺任意一个都视为未登录
CORE_KEYS = ("token", "userId", "openId")


def state_path(env: str) -> Path:
    """按环境隔离的登录态文件路径。"""
    return AUTH_DIR / f"{env}_state.json"


def read_local_storage(path: Path, url: str = "") -> list[dict[str, str]]:
    """从 storage_state 文件里取出指定站点的 localStorage 键值。"""
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    origins = data.get("origins") or []
    for origin in origins:
        if url and origin.get("origin", "").rstrip("/") == url.rstrip("/"):
            return origin.get("localStorage") or []
    return (origins[0].get("localStorage") if origins else []) or []


def has_session(items: list[dict[str, str]]) -> bool:
    """localStorage 中是否具备完整的登录标识。"""
    keys = {item.get("name") for item in items}
    return all(key in keys for key in CORE_KEYS)
