from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
import shutil
import subprocess
from typing import List, Optional


QUERY_FIELDS = ["index", "uuid", "name", "utilization.gpu"]


@dataclass
class GPUSample:
    timestamp: datetime
    gpu_index: int
    gpu_uuid: str
    gpu_name: str
    util_gpu: float


def nvidia_smi_path() -> Optional[str]:
    return shutil.which("nvidia-smi")


def collect_gpu_samples(now: datetime) -> List[GPUSample]:
    executable = nvidia_smi_path()
    if not executable:
        raise RuntimeError("nvidia-smi not found in PATH")

    command = [
        executable,
        "--query-gpu={0}".format(",".join(QUERY_FIELDS)),
        "--format=csv,noheader,nounits",
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    rows = [line for line in result.stdout.splitlines() if line.strip()]
    if not rows:
        return []

    samples = []  # type: List[GPUSample]
    reader = csv.reader(rows)
    for row in reader:
        if len(row) != 4:
            raise RuntimeError("Unexpected nvidia-smi row: {0!r}".format(row))
        gpu_index, gpu_uuid, gpu_name, util_gpu = [item.strip() for item in row]
        samples.append(
            GPUSample(
                timestamp=now,
                gpu_index=int(gpu_index),
                gpu_uuid=gpu_uuid,
                gpu_name=gpu_name,
                util_gpu=float(util_gpu),
            )
        )
    return samples
