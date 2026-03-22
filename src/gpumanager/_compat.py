from __future__ import annotations

try:
    import tomllib  # type: ignore
except ImportError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

try:
    from zoneinfo import ZoneInfo  # type: ignore
except ImportError:  # pragma: no cover
    from backports.zoneinfo import ZoneInfo  # type: ignore

__all__ = ["tomllib", "ZoneInfo"]
