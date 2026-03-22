from __future__ import annotations

from pathlib import Path
import shlex
import shutil
import subprocess
import sys
from typing import List, Optional, Tuple

from gpumanager.config import Config


SYSTEMD_USER_DIR = Path.home() / ".config" / "systemd" / "user"


def install_user_units(config: Config, python_executable: Optional[str] = None) -> List[Path]:
    SYSTEMD_USER_DIR.mkdir(parents=True, exist_ok=True)
    executable = python_executable or sys.executable
    command = [executable, "-m", "gpumanager"]
    if config.path:
        command.extend(["--config", str(config.path)])

    units = {
        "gpumanager-sample.service": _sample_service(command),
        "gpumanager-sample.timer": _sample_timer(),
        "gpumanager-report.service": _report_service(command),
        "gpumanager-report.timer": _report_timer(config.send_time),
    }

    written = []  # type: List[Path]
    for name, content in units.items():
        path = SYSTEMD_USER_DIR / name
        path.write_text(content, encoding="utf-8")
        written.append(path)

    _run_systemctl_user("daemon-reload")
    return written


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
    exec_start = " ".join(shlex.quote(part) for part in [part for part in command] + ["sample"])
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


def _sample_timer() -> str:
    return "\n".join(
        [
            "[Unit]",
            "Description=Run gpumanager sampling every minute",
            "",
            "[Timer]",
            "OnCalendar=*-*-* *:*:00",
            "AccuracySec=1s",
            "Persistent=true",
            "",
            "[Install]",
            "WantedBy=timers.target",
            "",
        ]
    )


def _report_service(command: List[str]) -> str:
    exec_start = " ".join(shlex.quote(part) for part in [part for part in command] + ["report"])
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


def _report_timer(send_time: str) -> str:
    hour, minute = _normalize_send_time(send_time)
    return "\n".join(
        [
            "[Unit]",
            "Description=Run gpumanager report daily",
            "",
            "[Timer]",
            "OnCalendar=*-*-* {0:02d}:{1:02d}:00".format(hour, minute),
            "Persistent=true",
            "",
            "[Install]",
            "WantedBy=timers.target",
            "",
        ]
    )


def _normalize_send_time(send_time: str) -> Tuple[int, int]:
    parts = send_time.split(":")
    if len(parts) != 2:
        raise ValueError("Invalid send_time: {0}".format(send_time))
    hour = int(parts[0])
    minute = int(parts[1])
    if hour not in range(24) or minute not in range(60):
        raise ValueError("Invalid send_time: {0}".format(send_time))
    return hour, minute
