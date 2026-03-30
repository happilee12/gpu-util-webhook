from __future__ import annotations

from pathlib import Path
import getpass
import shlex
import shutil
import subprocess
import sys
import tempfile
from typing import List, Optional

from gpumanager.config import Config


SYSTEMD_SYSTEM_DIR = Path("/etc") / "systemd" / "system"
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


def install_system_units(
    config: Config,
    python_executable: Optional[str] = None,
    run_user: Optional[str] = None,
) -> List[Path]:
    executable = python_executable or sys.executable
    service_user = run_user or getpass.getuser()
    command = [executable, "-m", "gpumanager"]
    if config.path:
        command.extend(["--config", str(config.path)])

    units = {
        "gpumanager-sample.service": _sample_service(command, service_user),
        "gpumanager-sample.timer": _sample_timer(config.sample_interval),
        "gpumanager-report.service": _report_service(command, service_user),
        "gpumanager-report.timer": _report_timer(config.report_time, config.timezone),
    }

    written = []  # type: List[Path]
    with tempfile.TemporaryDirectory(prefix="gpumanager-systemd-") as temp_dir:
        temp_root = Path(temp_dir)
        for name, content in units.items():
            temp_path = temp_root / name
            temp_path.write_text(content, encoding="utf-8")
            target_path = SYSTEMD_SYSTEM_DIR / name
            _run_root_command("install", "-m", "0644", str(temp_path), str(target_path))
            written.append(target_path)

    _run_systemctl("daemon-reload", require_root=True, capture_output=False)
    return written


def disable_sample_timer() -> None:
    _run_systemctl("disable", "--now", "gpumanager-sample.timer", require_root=True, capture_output=False)


def disable_report_timer() -> None:
    _run_systemctl("disable", "--now", "gpumanager-report.timer", require_root=True, capture_output=False)


def enable_system_timers() -> None:
    _run_systemctl(
        "enable",
        "--now",
        "gpumanager-sample.timer",
        "gpumanager-report.timer",
        require_root=True,
        capture_output=False,
    )


def sync_installed_system_units(
    config: Config,
    python_executable: Optional[str] = None,
    run_user: Optional[str] = None,
) -> List[str]:
    sample_timer = SYSTEMD_SYSTEM_DIR / "gpumanager-sample.timer"
    report_timer = SYSTEMD_SYSTEM_DIR / "gpumanager-report.timer"

    if not sample_timer.exists() and not report_timer.exists():
        return []

    install_system_units(config, python_executable=python_executable, run_user=run_user)
    return reload_system_units()


def reload_system_units() -> List[str]:
    changed = []  # type: List[str]
    sample_timer = SYSTEMD_SYSTEM_DIR / "gpumanager-sample.timer"
    report_timer = SYSTEMD_SYSTEM_DIR / "gpumanager-report.timer"

    if not sample_timer.exists() and not report_timer.exists():
        return changed

    _run_systemctl("daemon-reload", require_root=True, capture_output=False)
    if sample_timer.exists():
        _run_systemctl("restart", "gpumanager-sample.timer", require_root=True, capture_output=False)
        changed.append("gpumanager-sample.timer")
    if report_timer.exists():
        _run_systemctl("restart", "gpumanager-report.timer", require_root=True, capture_output=False)
        changed.append("gpumanager-report.timer")
    return changed


def user_unit_paths(home_dir: Optional[Path] = None) -> List[Path]:
    user_home = home_dir or Path.home()
    user_dir = user_home / ".config" / "systemd" / "user"
    return [
        user_dir / "gpumanager-sample.timer",
        user_dir / "gpumanager-sample.service",
        user_dir / "gpumanager-report.timer",
        user_dir / "gpumanager-report.service",
    ]


def find_conflicting_user_units(home_dir: Optional[Path] = None) -> List[Path]:
    return [path for path in user_unit_paths(home_dir) if path.exists()]


def uninstall_system_units() -> List[Path]:
    removed = []  # type: List[Path]
    for unit in ["gpumanager-sample.timer", "gpumanager-report.timer"]:
        _run_systemctl("disable", "--now", unit, require_root=True, capture_output=False)
    for name in [
        "gpumanager-sample.timer",
        "gpumanager-sample.service",
        "gpumanager-report.timer",
        "gpumanager-report.service",
    ]:
        path = SYSTEMD_SYSTEM_DIR / name
        if path.exists():
            _run_root_command("rm", "-f", str(path))
            removed.append(path)
    _run_systemctl("daemon-reload", require_root=True, capture_output=False)
    return removed


def _run_systemctl(*args: str, require_root: bool = False, capture_output: bool = True) -> subprocess.CompletedProcess:
    systemctl = shutil.which("systemctl")
    if not systemctl:
        raise RuntimeError("systemctl not found")
    command = [systemctl, *args]
    if require_root:
        command = _with_sudo(command)
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=capture_output,
            text=True,
        )
    except OSError as exc:
        raise RuntimeError("Failed to run systemctl: {0}".format(exc)) from exc
    if result.returncode != 0:
        output = "\n".join(part.strip() for part in [result.stdout, result.stderr] if part and part.strip())
        if output:
            raise RuntimeError(output)
        raise RuntimeError("systemctl command failed: {0}".format(" ".join(args)))
    return result


def _run_root_command(*args: str) -> None:
    command = _with_sudo(list(args))
    try:
        result = subprocess.run(command, check=False, text=True)
    except OSError as exc:
        raise RuntimeError("Failed to run command: {0}".format(exc)) from exc
    if result.returncode != 0:
        raise RuntimeError("Command failed: {0}".format(" ".join(args)))


def _with_sudo(command: List[str]) -> List[str]:
    sudo = shutil.which("sudo")
    if not sudo:
        raise RuntimeError("sudo not found")
    return [sudo, *command]


def _sample_service(command: List[str], run_user: str) -> str:
    exec_start = " ".join(shlex.quote(part) for part in [part for part in command] + ["test-sample"])
    return "\n".join(
        [
            "[Unit]",
            "Description=Sample NVIDIA GPU utilization",
            "",
            "[Service]",
            "Type=oneshot",
            "User={0}".format(run_user),
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
    ) + "\n"


def _report_service(command: List[str], run_user: str) -> str:
    exec_start = " ".join(shlex.quote(part) for part in [part for part in command] + ["test-report"])
    return "\n".join(
        [
            "[Unit]",
            "Description=Send NVIDIA GPU utilization report",
            "",
            "[Service]",
            "Type=oneshot",
            "User={0}".format(run_user),
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
    ) + "\n"


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
