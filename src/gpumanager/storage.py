from __future__ import annotations

import csv
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from gpumanager.collector import GPUSample


CSV_HEADERS = ["timestamp", "gpu_index", "gpu_uuid", "gpu_name", "util_gpu"]
FILENAME_FORMAT = "%Y-%m-%dT%H-%M-%S.csv"


def ensure_storage_dir(csv_dir: Path) -> Path:
    csv_dir.mkdir(parents=True, exist_ok=True)
    return csv_dir


def sample_filename(timestamp: datetime) -> str:
    return timestamp.strftime(FILENAME_FORMAT)


def write_sample_csv(csv_dir: Path, samples: List[GPUSample]) -> Path:
    if not samples:
        raise ValueError("No GPU samples to write")

    ensure_storage_dir(csv_dir)
    target = csv_dir / sample_filename(samples[0].timestamp)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_HEADERS)
        writer.writeheader()
        for sample in samples:
            row = asdict(sample)
            row["timestamp"] = sample.timestamp.isoformat(timespec="seconds")
            writer.writerow(row)
    return target


def iter_csv_files(csv_dir: Path) -> List[Path]:
    if not csv_dir.exists():
        return []
    return sorted(path for path in csv_dir.glob("*.csv") if path.is_file())


def parse_filename_timestamp(path: Path) -> datetime:
    return datetime.strptime(path.name, FILENAME_FORMAT)


def csv_files_in_range(csv_dir: Path, start: datetime, end: datetime) -> List[Path]:
    matching = []  # type: List[Path]
    for path in iter_csv_files(csv_dir):
        try:
            timestamp = parse_filename_timestamp(path)
        except ValueError:
            continue
        if start <= timestamp <= end:
            matching.append(path)
    return matching


def read_samples_from_files(paths: List[Path]) -> List[Dict[str, str]]:
    rows = []  # type: List[Dict[str, str]]
    for path in paths:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            rows.extend(reader)
    return rows


def delete_files(paths: List[Path]) -> int:
    deleted = 0
    for path in paths:
        if path.exists():
            path.unlink()
            deleted += 1
    return deleted
