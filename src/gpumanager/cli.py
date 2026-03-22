from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import shutil
import sys
from typing import List, Optional

from gpumanager._compat import ZoneInfo
from gpumanager.collector import collect_gpu_samples, nvidia_smi_path
from gpumanager.config import Config, config_to_display_dict, load_config, save_config, update_config_value
from gpumanager.report import make_report, render_report_message
from gpumanager.slack import send_slack_message
from gpumanager.storage import csv_files_in_range, delete_files, write_sample_csv
from gpumanager.systemd import SYSTEMD_USER_DIR, install_user_units, uninstall_user_units


CONFIG_KEYS = [
    "slack.webhook_url",
    "storage.csv_dir",
    "report.send_time",
    "report.interval",
    "general.timezone",
    "general.server_name",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gpumanager", description="GPU utilization sampler and Slack reporter")
    parser.add_argument("--config", help="Path to config.toml")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.required = True

    subparsers.add_parser("init", help="Run interactive initial setup")

    config_parser = subparsers.add_parser("config", help="Manage configuration")
    config_subparsers = config_parser.add_subparsers(dest="config_command")
    config_subparsers.required = True

    config_set = config_subparsers.add_parser("set", help="Update configuration")
    config_set.add_argument("--key", choices=CONFIG_KEYS)
    config_set.add_argument("--value")

    config_subparsers.add_parser("show", help="Show current configuration")

    subparsers.add_parser("sample", help="Collect and store one GPU utilization sample")
    subparsers.add_parser("report", help="Aggregate CSV data and send Slack report")
    subparsers.add_parser("test", help="Send a test report using existing CSV data")

    delete_parser = subparsers.add_parser("delete-csv", help="Delete CSV files by datetime range")
    delete_parser.add_argument("--start", help="Start datetime in YYYY-MM-DD HH:MM:SS")
    delete_parser.add_argument("--end", help="End datetime in YYYY-MM-DD HH:MM:SS")
    delete_parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt")

    subparsers.add_parser("status", help="Show runtime and configuration status")
    subparsers.add_parser("install-systemd", help="Install user-level systemd services and timers")
    subparsers.add_parser("uninstall-systemd", help="Remove user-level systemd services and timers")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "init":
            return command_init(args.config)
        if args.command == "config":
            if args.config_command == "set":
                return command_config_set(args.config, key=args.key, value=args.value)
            if args.config_command == "show":
                return command_config_show(args.config)
        if args.command == "sample":
            return command_sample(args.config)
        if args.command == "report":
            return command_report(args.config, test_mode=False)
        if args.command == "test":
            return command_report(args.config, test_mode=True)
        if args.command == "delete-csv":
            return command_delete_csv(args.config, start=args.start, end=args.end, assume_yes=args.yes)
        if args.command == "status":
            return command_status(args.config)
        if args.command == "install-systemd":
            return command_install_systemd(args.config)
        if args.command == "uninstall-systemd":
            return command_uninstall_systemd()
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
    tz = ZoneInfo(config.timezone)
    now = datetime.now(tz)
    print("Current server time: {0}".format(now.strftime("%Y-%m-%d %H:%M:%S %Z")))
    config.server_name = _prompt("Server name", config.server_name)
    config.webhook_url = _prompt("Slack webhook URL", config.webhook_url)
    config.csv_dir = Path(_prompt("CSV storage directory", str(config.csv_dir))).expanduser()
    config.send_time = _prompt("Report send time (HH:MM)", config.send_time)
    config.interval = _prompt("Report interval (e.g. 1d, 12h, 30m)", config.interval)
    config.timezone = _prompt("Timezone", config.timezone)
    _validate_config(config)
    saved = save_config(config, config_path)
    print("Saved configuration to {0}".format(saved))
    return 0


def command_config_set(config_path: Optional[str], key: Optional[str] = None, value: Optional[str] = None) -> int:
    config = load_config(config_path, allow_missing=True)
    if key and value is not None:
        update_config_value(config, key, value)
        _validate_config(config)
        saved = save_config(config, config_path)
        print("Updated {0} in {1}".format(key, saved))
        return 0

    for item in CONFIG_KEYS:
        current = _get_config_value(config, item)
        answer = _prompt(item, current, allow_empty=True)
        if answer:
            update_config_value(config, item, answer)
    _validate_config(config)
    saved = save_config(config, config_path)
    print("Saved configuration to {0}".format(saved))
    return 0


def command_config_show(config_path: Optional[str]) -> int:
    config = load_config(config_path, allow_missing=True)
    print(json.dumps(config_to_display_dict(config), indent=2))
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
    status = {
        "config_path": str(config.path) if config.path else None,
        "config_exists": bool(config.path and config.path.exists()),
        "slack.webhook_url": config.webhook_url,
        "csv_dir": str(config.csv_dir),
        "csv_dir_exists": config.csv_dir.exists(),
        "nvidia_smi": nvidia_smi_path(),
        "systemctl": shutil.which("systemctl"),
        "sample_timer_installed": sample_timer.exists(),
        "report_timer_installed": report_timer.exists(),
        "general.server_name": config.server_name,
    }
    print(json.dumps(status, indent=2))
    return 0


def command_install_systemd(config_path: Optional[str]) -> int:
    config = load_config(config_path)
    _validate_config(config)
    written = install_user_units(config)
    print("Installed unit files:")
    for path in written:
        print(path)
    print("Enable with: systemctl --user enable --now gpumanager-sample.timer gpumanager-report.timer")
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


def _get_config_value(config: Config, key: str) -> str:
    if key == "slack.webhook_url":
        return config.webhook_url
    if key == "storage.csv_dir":
        return str(config.csv_dir)
    if key == "report.send_time":
        return config.send_time
    if key == "report.interval":
        return config.interval
    if key == "general.timezone":
        return config.timezone
    if key == "general.server_name":
        return config.server_name
    raise KeyError(key)


def _validate_config(config: Config) -> None:
    ZoneInfo(config.timezone)
    datetime.strptime(config.send_time, "%H:%M")
    value = config.interval.strip().lower()
    if len(value) < 2 or not value[:-1].isdigit() or value[-1] not in {"d", "h", "m"}:
        raise ValueError("report.interval must look like 1d, 12h, or 30m")
