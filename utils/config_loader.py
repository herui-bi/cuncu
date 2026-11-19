"""配置加载：读取 config/config.yaml，支持环境切换与环境变量注入。"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
ENV_DIR = ROOT / "config" / "environments"
# 默认读取项目目录下的 test.yaml，可用环境变量 TEST_STAGE 切换到其他阶段
DEFAULT_STAGE = "test"

# 加载项目根目录 .env，供配置中的 ${变量} 占位符取值
load_dotenv(ROOT / ".env")

# 支持 ${VAR} 与 ${VAR:-默认值} 两种写法
_ENV_VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


def _resolve(value: Any) -> Any:
    if isinstance(value, str):

        def replace(match: re.Match[str]) -> str:
            current = os.getenv(match.group(1))
            if current:
                return current
            return match.group(2) or ""

        return _ENV_VAR.sub(replace, value)
    if isinstance(value, dict):
        return {key: _resolve(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_resolve(item) for item in value]
    return value


def _as_bool(value: Any, default: bool = False) -> bool:
    """把配置中的布尔值（含 "false"/"0"/"no" 字符串）转成 bool。"""
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() not in ("false", "0", "no", "off")
    return bool(value)


def _load_env(env: str, stage: str = DEFAULT_STAGE) -> dict[str, Any]:
    """读取项目测试地址配置。

    目录约定：config/environments/<项目>/<阶段>.yaml（如 huiqubao/test.yaml），
    --env 传项目名，阶段默认 test，可用 TEST_STAGE 覆盖；
    兼容旧的扁平文件 config/environments/<env>.yaml。
    """
    project_dir = ENV_DIR / env
    if project_dir.is_dir():
        env_file = project_dir / f"{stage}.yaml"
        if not env_file.exists():
            stages = ", ".join(sorted(path.stem for path in project_dir.glob("*.yaml")))
            raise ValueError(f"项目 [{env}] 不存在阶段 [{stage}]，可选阶段: {stages}")
        with env_file.open(encoding="utf-8") as file:
            return _resolve(yaml.safe_load(file) or {})

    env_file = ENV_DIR / f"{env}.yaml"
    if env_file.exists():
        with env_file.open(encoding="utf-8") as file:
            return _resolve(yaml.safe_load(file) or {})

    available = ", ".join(sorted(path.name for path in ENV_DIR.iterdir() if path.is_dir()))
    raise ValueError(f"配置中不存在项目 [{env}]，可选项目: {available}")


class Config:
    """单个运行环境的配置视图。"""

    def __init__(self, env: str | None = None):
        config_file = ROOT / "config" / "config.yaml"
        with config_file.open(encoding="utf-8") as file:
            self.raw: dict[str, Any] = _resolve(yaml.safe_load(file) or {})

        self.env = env or os.getenv("TEST_ENV") or self.raw.get("env", DEFAULT_STAGE)
        self.stage = (os.getenv("TEST_STAGE") or DEFAULT_STAGE).strip() or DEFAULT_STAGE
        self.env_data: dict[str, Any] = _load_env(self.env, self.stage)

        self.browser: dict[str, Any] = self.raw.get("browser") or {}
        self.timeouts: dict[str, Any] = self.raw.get("timeouts") or {}
        self.auth: dict[str, Any] = self.raw.get("auth") or {}

    # ---------- 环境 ----------
    @property
    def base_url(self) -> str:
        return str(self.env_data.get("base_url", "")).rstrip("/")

    def url(self, path: str = "") -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"{self.base_url}/{path.lstrip('/')}" if path else self.base_url

    # ---------- 浏览器 ----------
    @property
    def headless(self) -> bool:
        return _as_bool(self.browser.get("headless"), True)

    @property
    def is_mobile(self) -> bool:
        return _as_bool(self.browser.get("is_mobile"), False)

    @property
    def slow_mo(self) -> int:
        return int(self.browser.get("slow_mo", 0))

    @property
    def viewport(self) -> dict[str, int]:
        viewport = self.browser.get("viewport") or {}
        return {
            "width": int(viewport.get("width", 1440)),
            "height": int(viewport.get("height", 900)),
        }

    @property
    def locale(self) -> str:
        return str(self.browser.get("locale", "zh-CN"))

    @property
    def ignore_https_errors(self) -> bool:
        return bool(self.browser.get("ignore_https_errors", True))

    # ---------- 超时 ----------
    @property
    def default_timeout(self) -> int:
        return int(self.timeouts.get("default_ms", 15000))

    @property
    def navigation_timeout(self) -> int:
        return int(self.timeouts.get("navigation_ms", 30000))

    # ---------- 登录 ----------
    @property
    def auth_enabled(self) -> bool:
        return bool(self.auth.get("enabled", False))

    @property
    def auth_state_path(self) -> Path:
        return ROOT / str(self.auth.get("storage_state", "auth/storage_state.json"))

    @property
    def login_path(self) -> str:
        return str(self.auth.get("login_path", "/"))

    @property
    def auth_username(self) -> str:
        return str(self.auth.get("username", ""))

    @property
    def auth_password(self) -> str:
        return str(self.auth.get("password", ""))

    # ---------- 数据 ----------
    @property
    def excel_path(self) -> Path:
        return ROOT / str((self.raw.get("excel") or {}).get("path", "data/caseData.xlsx"))

    # ---------- 数据库 ----------
    @property
    def db(self) -> dict[str, Any]:
        return self.env_data.get("db") or {}


_active: Config | None = None


def get_config(env: str | None = None) -> Config:
    """获取配置单例；传入 env 时按该环境重新加载。"""
    global _active
    if _active is None or (env and env != _active.env):
        _active = Config(env)
    return _active


def set_active(config: Config) -> None:
    global _active
    _active = config
