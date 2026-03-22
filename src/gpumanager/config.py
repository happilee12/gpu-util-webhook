from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
from typing import Any, Dict, List, Optional

from gpumanager._compat import tomllib


APP_DIR_NAME = "gpumanager"
ENV_VAR_NAME = "GPUMANAGER_CONFIG"
DEFAULT_USER_CONFIG = Path.home() / ".config" / APP_DIR_NAME / "config.toml"
DEFAULT_SYSTEM_CONFIG = Path("/etc") / APP_DIR_NAME / "config.toml"
DEFAULT_CSV_DIR = Path.home() / ".local" / "share" / APP_DIR_NAME


@dataclass
class Config:
    webhook_url: str = ""
    csv_dir: Path = DEFAULT_CSV_DIR
    send_time: str = "09:00"
    interval: str = "1d"
    timezone: str = "Asia/Seoul"
    server_name: str = ""
    path: Optional[Path] = None


def candidate_config_paths(explicit_path: Optional[str] = None) -> List[Path]:
    candidates = []  # type: List[Path]
    if explicit_path:
        candidates.append(Path(explicit_path).expanduser())
    env_path = os.environ.get(ENV_VAR_NAME)
    if env_path:
        candidates.append(Path(env_path).expanduser())
    candidates.append(DEFAULT_USER_CONFIG)
    candidates.append(DEFAULT_SYSTEM_CONFIG)
    return candidates


def resolve_config_path(explicit_path: Optional[str] = None) -> Path:
    for path in candidate_config_paths(explicit_path):
        if path.exists():
            return path
    if explicit_path:
        return Path(explicit_path).expanduser()
    return DEFAULT_USER_CONFIG


def default_config() -> Config:
    return Config()


def load_config(explicit_path: Optional[str] = None, allow_missing: bool = False) -> Config:
    path = resolve_config_path(explicit_path)
    if not path.exists():
        if allow_missing:
            cfg = default_config()
            cfg.path = path
            return cfg
        raise FileNotFoundError("Config file not found: {0}".format(path))

    with path.open("rb") as handle:
        raw = tomllib.load(handle)

    cfg = Config(
        webhook_url=str(_get_nested(raw, "slack", "webhook_url", default="")),
        csv_dir=Path(str(_get_nested(raw, "storage", "csv_dir", default=str(DEFAULT_CSV_DIR)))).expanduser(),
        send_time=str(_get_nested(raw, "report", "send_time", default="09:00")),
        interval=str(_get_nested(raw, "report", "interval", default="1d")),
        timezone=str(_get_nested(raw, "general", "timezone", default="Asia/Seoul")),
        server_name=str(_get_nested(raw, "general", "server_name", default="")),
        path=path,
    )
    return cfg


def save_config(config: Config, explicit_path: Optional[str] = None) -> Path:
    path = Path(explicit_path).expanduser() if explicit_path else (config.path or DEFAULT_USER_CONFIG)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_render_toml(config), encoding="utf-8")
    config.path = path
    return path


def _render_toml(config: Config) -> str:
    values = {
        "slack": {"webhook_url": config.webhook_url},
        "storage": {"csv_dir": str(config.csv_dir)},
        "report": {"send_time": config.send_time, "interval": config.interval},
        "general": {"timezone": config.timezone, "server_name": config.server_name},
    }
    lines = []  # type: List[str]
    for section, mapping in values.items():
        lines.append("[{0}]".format(section))
        for key, value in mapping.items():
            lines.append('{0} = "{1}"'.format(key, _escape_string(value)))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def config_to_display_dict(config: Config) -> Dict[str, Any]:
    return {
        "config_path": str(config.path) if config.path else None,
        "slack.webhook_url": _mask_secret(config.webhook_url),
        "storage.csv_dir": str(config.csv_dir),
        "report.send_time": config.send_time,
        "report.interval": config.interval,
        "general.timezone": config.timezone,
        "general.server_name": config.server_name,
    }


def update_config_value(config: Config, key: str, value: str) -> None:
    normalized = key.strip().lower()
    if normalized == "slack.webhook_url":
        config.webhook_url = value.strip()
    elif normalized == "storage.csv_dir":
        config.csv_dir = Path(value.strip()).expanduser()
    elif normalized == "report.send_time":
        config.send_time = value.strip()
    elif normalized == "report.interval":
        config.interval = value.strip()
    elif normalized == "general.timezone":
        config.timezone = value.strip()
    elif normalized == "general.server_name":
        config.server_name = value.strip()
    else:
        raise KeyError("Unknown config key: {0}".format(key))


def _get_nested(data: Dict[str, Any], section: str, key: str, default: Any) -> Any:
    if section not in data:
        return default
    if not isinstance(data[section], dict):
        return default
    return data[section].get(key, default)


def _escape_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 12:
        return "*" * len(value)
    return value[:8] + "..." + value[-4:]
