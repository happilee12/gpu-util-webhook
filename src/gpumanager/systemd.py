from __future__ import annotations

from pathlib import Path
import shlex
import shutil
import subprocess
import sys
from typing import List, Optional

from gpumanager.config import Config


SYSTEMD_USER_DIR = Path.home() / ".config" / "systemd" / "user"
WEEKDAY_NAMES = {
    0: "Sun",
    1: "Mon",
    2: "Tue",
    3: "Wed",
    4: "Thu",
    5: "Fri",
    6: "Sat",
    7: "Sun",
}


def install_user_units(config: Config, python_executable: Optional[str] = None) -> List[Path]:
    SYSTEMD_USER_DIR.mkdir(parents=True, exist_ok=True)
    executable = python_executable or sys.executable
    command = [executable, "-m", "gpumanager"]
    if config.path:
        command.extend(["--config", str(config.path)])

    units = {
        "gpumanager-sample.service": _sample_service(command),
        "gpumanager-sample.timer": _sample_timer(config.sample_interval),
        "gpumanager-report.service": _report_service(command),
        "gpumanager-report.timer": _report_timer(config.report_time, config.timezone),
    }

    written = []  # type: List[Path]
    for name, content in units.items():
        path = SYSTEMD_USER_DIR / name
        path.write_text(content, encoding="utf-8")
        written.append(path)

    _run_systemctl_user("daemon-reload")
    return written




def disable_sample_timer() -> None:
    _run_systemctl_user("disable", "--now", "gpumanager-sample.timer")


def disable_report_timer() -> None:
    _run_systemctl_user("disable", "--now", "gpumanager-report.timer")

def sync_installed_user_units(config: Config, python_executable: Optional[str] = None) -> List[str]:
    sample_timer = SYSTEMD_USER_DIR / "gpumanager-sample.timer"
    report_timer = SYSTEMD_USER_DIR / "gpumanager-report.timer"

    if not sample_timer.exists() and not report_timer.exists():
        return []

    install_user_units(config, python_executable=python_executable)
    return reload_user_units()


def reload_user_units() -> List[str]:
    changed = []  # type: List[str]
    sample_timer = SYSTEMD_USER_DIR / "gpumanager-sample.timer"
    report_timer = SYSTEMD_USER_DIR / "gpumanager-report.timer"

    if not sample_timer.exists() and not report_timer.exists():
        return changed

    _run_systemctl_user("daemon-reload")
    if sample_timer.exists():
        _run_systemctl_user("restart", "gpumanager-sample.timer")
        changed.append("gpumanager-sample.timer")
    if report_timer.exists():
        _run_systemctl_user("restart", "gpumanager-report.timer")
        changed.append("gpumanager-report.timer")
    return changed


def uninstall_user_units() -> List[Path]:
    removed = []  # type: List[Path]
    for unit in ["gpumanager-sample.timer", "gpumanager-report.timer"]:
        _run_systemctl_user("disable", "--now", unit)
    for name in [
        "gpumanager-sample.timer",
        "gpumanager-sample.service",
        "gpumanager-report.timer",
        "gpumanager-report.service",
    ]:
        path = SYSTEMD_USER_DIR / name
        if path.exists():
            path.unlink()
            removed.append(path)
    _run_systemctl_user("daemon-reload")
    return removed


def _run_systemctl_user(*args: str) -> None:
    systemctl = shutil.which("systemctl")
    if not systemctl:
        return
    try:
        subprocess.run([systemctl, "--user", *args], check=False, capture_output=True, text=True)
    except OSError:
        return


def _sample_service(command: List[str]) -> str:
    exec_start = " ".join(shlex.quote(part) for part in [part for part in command] + ["test-sample"])
    return "\n".join(
        [
            "[Unit]",
            "Description=Sample NVIDIA GPU utilization",
            "",
            "[Service]",
            "Type=oneshot",
            "ExecStart={0}".format(exec_start),
            "",
        ]
    ) + "\n"


def _sample_timer(sample_interval: str) -> str:
    seconds = interval_to_seconds(sample_interval)
    return "\n".join(
        [
            "[Unit]",
            "Description=Run gpumanager sampling on a fixed interval",
            "",
            "[Timer]",
            "OnActiveSec=10",
            "OnUnitActiveSec={0}".format(seconds),
            "AccuracySec=1s",
            "Persistent=true",
            "",
            "[Install]",
            "WantedBy=timers.target",
            "",
        ]
    )


def _report_service(command: List[str]) -> str:
    exec_start = " ".join(shlex.quote(part) for part in [part for part in command] + ["test-report"])
    return "\n".join(
        [
            "[Unit]",
            "Description=Send NVIDIA GPU utilization report",
            "",
            "[Service]",
            "Type=oneshot",
            "ExecStart={0}".format(exec_start),
            "",
        ]
    ) + "\n"


def _report_timer(report_time: str, timezone: str) -> str:
    on_calendar = cron_to_on_calendar(report_time, timezone)
    return "\n".join(
        [
            "[Unit]",
            "Description=Run gpumanager report schedule",
            "",
            "[Timer]",
            "OnCalendar={0}".format(on_calendar),
            "Persistent=true",
            "",
            "[Install]",
            "WantedBy=timers.target",
            "",
        ]
    )


def interval_to_seconds(interval: str) -> int:
    value = interval.strip().lower()
    if len(value) < 2 or not value[:-1].isdigit():
        raise ValueError("sample.interval must be a number followed by s, m, h, or d (for example: 11s, 2m, 1h, 1d)")

    amount = int(value[:-1])
    unit = value[-1]
    if amount <= 0:
        raise ValueError("sample.interval must be positive")
    if unit == "s":
        return amount
    if unit == "m":
        return amount * 60
    if unit == "h":
        return amount * 60 * 60
    if unit == "d":
        return amount * 60 * 60 * 24
    raise ValueError("sample.interval must use s, m, h, or d")


def cron_to_on_calendar(report_time: str, timezone: Optional[str] = None) -> str:
    parts = report_time.split()
    if len(parts) != 5:
        raise ValueError("report.report_time must be a 5-field cron string like '0 9 * * *'")

    minute = _convert_numeric_field(parts[0], 0, 59)
    hour = _convert_numeric_field(parts[1], 0, 23)
    day = _convert_numeric_field(parts[2], 1, 31)
    month = _convert_numeric_field(parts[3], 1, 12)
    weekday = _convert_weekday_field(parts[4])

    prefix = ""
    if weekday != "*":
        prefix = weekday + " "

    calendar = "{0}*-{1}-{2} {3}:{4}:00".format(
        prefix,
        _format_calendar_field(month),
        _format_calendar_field(day),
        _format_calendar_field(hour),
        _format_calendar_field(minute),
    )
    if timezone:
        return "{0} {1}".format(calendar, timezone.strip())
    return calendar

def _convert_numeric_field(field: str, minimum: int, maximum: int) -> str:
    if field == "*":
        return "*"

    parts = field.split(",")
    converted = []
    for part in parts:
        converted.append(_convert_numeric_part(part.strip(), minimum, maximum))
    return ",".join(converted)


def _convert_numeric_part(part: str, minimum: int, maximum: int) -> str:
    if not part:
        raise ValueError("Invalid cron field")

    if "/" in part:
        base, step = part.split("/", 1)
        if not step.isdigit() or int(step) <= 0:
            raise ValueError("Invalid cron step: {0}".format(part))
        base_value = "*" if base == "*" else _convert_numeric_part(base, minimum, maximum)
        return "{0}/{1}".format(base_value, step)

    if "-" in part:
        start_text, end_text = part.split("-", 1)
        start = _parse_int_in_range(start_text, minimum, maximum)
        end = _parse_int_in_range(end_text, minimum, maximum)
        if start > end:
            raise ValueError("Invalid cron range: {0}".format(part))
        return "{0}..{1}".format(start, end)

    value = _parse_int_in_range(part, minimum, maximum)
    return str(value)


def _convert_weekday_field(field: str) -> str:
    if field == "*":
        return "*"
    if "/" in field:
        raise ValueError("Weekday steps are not supported in report.report_time")

    parts = field.split(",")
    converted = []
    for part in parts:
        part = part.strip()
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            start = _parse_weekday_value(start_text)
            end = _parse_weekday_value(end_text)
            converted.append("{0}..{1}".format(WEEKDAY_NAMES[start], WEEKDAY_NAMES[end]))
        else:
            converted.append(WEEKDAY_NAMES[_parse_weekday_value(part)])
    return ",".join(converted)


def _parse_weekday_value(value: str) -> int:
    if not value.isdigit():
        raise ValueError("Weekday must be numeric in report.report_time: {0}".format(value))
    number = int(value)
    if number not in WEEKDAY_NAMES:
        raise ValueError("Weekday must be between 0 and 7 in report.report_time: {0}".format(value))
    return number


def _parse_int_in_range(value: str, minimum: int, maximum: int) -> int:
    if not value.isdigit():
        raise ValueError("Invalid cron value: {0}".format(value))
    number = int(value)
    if number < minimum or number > maximum:
        raise ValueError("Cron value out of range: {0}".format(value))
    return number


def _format_calendar_field(value: str) -> str:
    if value.isdigit():
        return "{0:02d}".format(int(value))
    return value
