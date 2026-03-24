from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import List, Optional

from gpumanager._compat import ZoneInfo
from gpumanager.collector import collect_gpu_samples, nvidia_smi_path
from gpumanager.config import Config, load_config, save_config
from gpumanager.report import make_report, render_report_message
from gpumanager.slack import send_slack_message
from gpumanager.storage import csv_files_in_range, delete_files, write_sample_csv
from gpumanager.systemd import (
    SYSTEMD_USER_DIR,
    cron_to_on_calendar,
    disable_report_timer,
    disable_sample_timer,
    install_user_units,
    reload_user_units,
    sync_installed_user_units,
    uninstall_user_units,
)

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gpumanager", description="GPU utilization sampler and Slack reporter")
    parser.add_argument("--config", help="Path to config.toml")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.required = True

    subparsers.add_parser("init", help="Run interactive initial setup")

    subparsers.add_parser("test-sample", help="Collect and store one GPU utilization sample")
    subparsers.add_parser("test-report", help="Aggregate CSV data and send Slack report")

    delete_parser = subparsers.add_parser("delete-csv", help="Delete CSV files by datetime range")
    delete_parser.add_argument("--start", help="Start datetime in YYYY-MM-DD HH:MM:SS")
    delete_parser.add_argument("--end", help="End datetime in YYYY-MM-DD HH:MM:SS")
    delete_parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt")

    subparsers.add_parser("status", help="Show runtime and configuration status")
    subparsers.add_parser("install-systemd", help="Install user-level systemd services and timers")
    subparsers.add_parser("uninstall-systemd", help="Remove user-level systemd services and timers")
    subparsers.add_parser("disable-sample", help="Disable the sample timer")
    subparsers.add_parser("disable-report", help="Disable the report timer")
    subparsers.add_parser("reload", help="Reload user systemd timers for gpumanager")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "init":
            return command_init(args.config)
        if args.command == "test-sample":
            return command_sample(args.config)
        if args.command == "test-report":
            return command_report(args.config, test_mode=False)
        if args.command == "delete-csv":
            return command_delete_csv(args.config, start=args.start, end=args.end, assume_yes=args.yes)
        if args.command == "status":
            return command_status(args.config)
        if args.command == "install-systemd":
            return command_install_systemd(args.config)
        if args.command == "uninstall-systemd":
            return command_uninstall_systemd()
        if args.command == "disable-sample":
            return command_disable_sample()
        if args.command == "disable-report":
            return command_disable_report()
        if args.command == "reload":
            return command_reload()
    except KeyboardInterrupt:
        print("Cancelled.", file=sys.stderr)
        return 130
    except Exception as exc:
        print("Error: {0}".format(exc), file=sys.stderr)
        return 1

    parser.error("Unknown command")
    return 2


def command_init(config_path: Optional[str]) -> int:
    config = load_config(config_path, allow_missing=True)
    now = _print_current_server_time(config.timezone)
    config.server_name = _prompt("Server name", config.server_name)
    config.webhook_url = _prompt("Slack webhook URL", config.webhook_url)
    config.csv_dir = Path(_prompt("CSV storage directory", str(config.csv_dir))).expanduser()
    config.sample_interval = _prompt("Sample interval (e.g. 30s, 2m, 15m, 1h)", config.sample_interval)
    _print_report_time_examples()
    config.report_time = _prompt(
        "Report time cron (minute hour day month weekday)",
        config.report_time or _cron_example(now),
    )
    config.interval = _prompt("Report window (e.g. 1m, 1h, 12h, 1d)", config.interval)
    config.timezone = _prompt("Timezone", config.timezone)
    _validate_config(config)
    saved = save_config(config, config_path)
    synced = sync_installed_user_units(config)
    print("Saved configuration to {0}".format(saved))
    if synced:
        print("Reloaded installed timers: {0}".format(", ".join(synced)))
    return 0


def command_sample(config_path: Optional[str]) -> int:
    config = load_config(config_path)
    _validate_config(config)
    tz = ZoneInfo(config.timezone)
    now = datetime.now(tz)
    samples = collect_gpu_samples(now)
    if not samples:
        print("No GPUs reported by nvidia-smi.")
        return 0
    target = write_sample_csv(config.csv_dir, samples)
    print("Wrote {0} GPU rows to {1}".format(len(samples), target))
    return 0


def command_report(config_path: Optional[str], test_mode: bool) -> int:
    config = load_config(config_path)
    _validate_config(config)
    result = make_report(config)
    message = render_report_message(result, test_mode=test_mode)
    send_slack_message(config.webhook_url, message)
    print(message)
    return 0


def command_delete_csv(config_path: Optional[str], start: Optional[str] = None, end: Optional[str] = None, assume_yes: bool = False) -> int:
    config = load_config(config_path)
    start_text = start or _prompt("Start datetime (YYYY-MM-DD HH:MM:SS)", "")
    end_text = end or _prompt("End datetime   (YYYY-MM-DD HH:MM:SS)", "")
    start_dt = datetime.strptime(start_text, "%Y-%m-%d %H:%M:%S")
    end_dt = datetime.strptime(end_text, "%Y-%m-%d %H:%M:%S")
    if end_dt < start_dt:
        raise ValueError("End datetime must be after start datetime")
    matches = csv_files_in_range(config.csv_dir, start_dt, end_dt)
    print("Deleting {0} files.".format(len(matches)))
    if not assume_yes:
        confirm = input("Continue? [y/N]: ").strip().lower()
        if confirm not in {"y", "yes"}:
            print("Deletion cancelled.")
            return 0
    deleted = delete_files(matches)
    print("Deleted {0} files.".format(deleted))
    return 0


def command_status(config_path: Optional[str]) -> int:
    config = load_config(config_path, allow_missing=True)
    sample_timer = SYSTEMD_USER_DIR / "gpumanager-sample.timer"
    report_timer = SYSTEMD_USER_DIR / "gpumanager-report.timer"
    sample_next_trigger = _read_timer_trigger("gpumanager-sample.timer")
    report_next_trigger = _read_timer_trigger("gpumanager-report.timer")
    status = {
        "config_path": str(config.path) if config.path else None,
        "config_exists": bool(config.path and config.path.exists()),
        "slack.webhook_url": config.webhook_url,
        "csv_dir": str(config.csv_dir),
        "csv_dir_exists": config.csv_dir.exists(),
        "sample.interval": config.sample_interval,
        "report.report_time": config.report_time,
        "report.on_calendar": cron_to_on_calendar(config.report_time, config.timezone),
        "report.interval": config.interval,
        "general.timezone": config.timezone,
        "general.server_name": config.server_name,
        "nvidia_smi": nvidia_smi_path(),
        "systemctl": shutil.which("systemctl"),
        "sample_timer_installed": sample_timer.exists(),
        "report_timer_installed": report_timer.exists(),
        "sample.next_trigger": sample_next_trigger,
        "report.next_trigger": report_next_trigger,
    }
    print(json.dumps(status, indent=2))
    return 0


def _read_timer_trigger(unit_name: str) -> Optional[str]:
    systemctl = shutil.which("systemctl")
    if not systemctl:
        return None
    try:
        result = subprocess.run(
            [systemctl, "--user", "status", unit_name],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None

    output = "\n".join(part for part in [result.stdout, result.stderr] if part)
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("Trigger:"):
            return stripped.partition(":")[2].strip()
    if "could not be found" in output.lower():
        return "not found"
    return None


def command_install_systemd(config_path: Optional[str]) -> int:
    config = load_config(config_path)
    _validate_config(config)
    written = install_user_units(config)
    print("Installed unit files:")
    for path in written:
        print(path)
    print("Enable with: systemctl --user enable --now gpumanager-sample.timer gpumanager-report.timer")
    return 0


def command_disable_sample() -> int:
    disable_sample_timer()
    print("Disabled gpumanager-sample.timer")
    return 0


def command_disable_report() -> int:
    disable_report_timer()
    print("Disabled gpumanager-report.timer")
    return 0


def command_reload() -> int:
    reloaded = reload_user_units()
    if not reloaded:
        print("No installed timers found.")
        return 0
    print("Reloaded timers: {0}".format(", ".join(reloaded)))
    return 0


def command_uninstall_systemd() -> int:
    removed = uninstall_user_units()
    if not removed:
        print("No unit files found.")
        return 0
    print("Removed unit files:")
    for path in removed:
        print(path)
    return 0


def _prompt(label: str, current: str, allow_empty: bool = False) -> str:
    suffix = " [{0}]".format(current) if current else ""
    answer = input("{0}{1}: ".format(label, suffix)).strip()
    if answer:
        return answer
    if allow_empty:
        return ""
    return current


def _validate_config(config: Config) -> None:
    ZoneInfo(config.timezone)
    _validate_duration(config.sample_interval, "sample.interval")
    cron_to_on_calendar(config.report_time, config.timezone)
    value = config.interval.strip().lower()
    if len(value) < 2 or not value[:-1].isdigit() or value[-1] not in {"d", "h", "m"}:
        raise ValueError("report.interval must look like 1d, 12h, or 30m")


def _print_current_server_time(timezone_name: str) -> datetime:
    tz = ZoneInfo(timezone_name)
    now = datetime.now(tz)
    print("Current server time: {0}".format(now.strftime("%Y-%m-%d %H:%M:%S %Z")))
    return now


def _print_report_time_examples() -> None:
    print("Report time examples:")
    print("  Every day at 09:00  -> 0 9 * * *")
    print("  Every hour          -> 0 * * * *")
    print("  Every 10 minutes    -> */10 * * * *")


def _cron_example(now: Optional[datetime]) -> str:
    if not now:
        return "0 9 * * *"
    return "{0} {1} * * *".format(now.minute, now.hour)


def _validate_duration(value: str, label: str) -> None:
    normalized = value.strip().lower()
    if len(normalized) < 2 or not normalized[:-1].isdigit() or normalized[-1] not in {"s", "m", "h", "d"}:
        raise ValueError("{0} must be a number followed by s, m, h, or d (for example: 11s, 2m, 1h, 1d)".format(label))
