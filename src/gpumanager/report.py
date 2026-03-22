from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union

from gpumanager._compat import ZoneInfo
from gpumanager.config import Config
from gpumanager.storage import csv_files_in_range, read_samples_from_files


@dataclass
class GPUReportRow:
    gpu_uuid: str
    gpu_index: int
    gpu_name: str
    average_util: float
    sample_count: int


@dataclass
class ReportResult:
    server_name: str
    server_time: datetime
    window_label: str
    window_start: datetime
    window_end: datetime
    rows: List[GPUReportRow]
    file_count: int


def parse_interval(interval: str) -> timedelta:
    value = interval.strip().lower()
    if not value:
        raise ValueError("Interval cannot be empty")

    suffix = value[-1]
    number = value[:-1]
    if not number.isdigit():
        raise ValueError("Invalid interval: {0}".format(interval))

    amount = int(number)
    if amount <= 0:
        raise ValueError("Interval must be positive: {0}".format(interval))

    if suffix == "d":
        return timedelta(days=amount)
    if suffix == "h":
        return timedelta(hours=amount)
    if suffix == "m":
        return timedelta(minutes=amount)
    raise ValueError("Unsupported interval unit: {0}".format(interval))


def make_report(config: Config, now: Optional[datetime] = None) -> ReportResult:
    tz = ZoneInfo(config.timezone)
    current = now.astimezone(tz) if now else datetime.now(tz)
    interval = parse_interval(config.interval)
    start = current - interval
    paths = csv_files_in_range(config.csv_dir, start.replace(tzinfo=None), current.replace(tzinfo=None))
    rows = aggregate_rows(read_samples_from_files(paths))
    return ReportResult(
        server_name=config.server_name,
        server_time=current,
        window_label="last {0}".format(config.interval),
        window_start=start,
        window_end=current,
        rows=rows,
        file_count=len(paths),
    )


def aggregate_rows(raw_rows: List[Dict[str, str]]) -> List[GPUReportRow]:
    buckets = {}  # type: Dict[str, Dict[str, Union[float, int, str]]]
    for row in raw_rows:
        gpu_uuid = row["gpu_uuid"]
        bucket = buckets.setdefault(
            gpu_uuid,
            {
                "gpu_index": int(row["gpu_index"]),
                "gpu_name": row["gpu_name"],
                "util_sum": 0.0,
                "sample_count": 0,
            },
        )
        bucket["util_sum"] = float(bucket["util_sum"]) + float(row["util_gpu"])
        bucket["sample_count"] = int(bucket["sample_count"]) + 1

    report_rows = []  # type: List[GPUReportRow]
    for gpu_uuid, bucket in buckets.items():
        sample_count = int(bucket["sample_count"])
        average = float(bucket["util_sum"]) / sample_count if sample_count else 0.0
        report_rows.append(
            GPUReportRow(
                gpu_uuid=gpu_uuid,
                gpu_index=int(bucket["gpu_index"]),
                gpu_name=str(bucket["gpu_name"]),
                average_util=average,
                sample_count=sample_count,
            )
        )
    return sorted(report_rows, key=lambda row: row.gpu_index)


def render_report_message(result: ReportResult, test_mode: bool = False) -> str:
    server_name = result.server_name if result.server_name else "gpumanager"
    lines = [
        "[{0}] {1}".format(server_name, result.server_time.strftime("%Y.%m.%d %H:%M:%S %Z")),
        "Window: {0}".format(result.window_label),
    ]
    if not result.rows:
        lines.append("No GPU samples found in the selected window.")
        return "\n".join(lines)

    for row in result.rows:
        lines.append("GPU {0}: {1:.2f}%".format(row.gpu_index, row.average_util))
    return "\n".join(lines)
