# gpumanager

`gpumanager` is a lightweight Python CLI tool for sampling NVIDIA GPU utilization, storing minute-by-minute CSV snapshots, aggregating utilization over a reporting window, and sending GPU-wise summaries to Slack.

The installable Python distribution is named `gpumanager`. The CLI entrypoint is `gpumanager`.

## Features

- Samples NVIDIA GPU utilization with `nvidia-smi`
- Stores one CSV file per sample
- Aggregates average utilization by GPU UUID
- Sends reports to Slack via webhook
- Supports interactive configuration
- Installs user-level `systemd` services and timers
- Uses minimal dependencies and stays close to the standard library

## Requirements

- Linux
- Python 3.8+
- NVIDIA GPU
- `nvidia-smi` in `PATH`
- `systemd` recommended

## Installation

Python 3.8 support uses small compatibility dependencies installed automatically by pip:

- `tomli` on Python < 3.11
- `backports.zoneinfo` on Python < 3.9

```bash
pip install .
# or
pipx install .
```

If you install with `pipx`, make sure the `pipx` binary path is added to your shell:

```bash
pipx ensurepath
source ~/.bashrc
```

After publishing:

```bash
pip install gpumanager
# or
pipx install gpumanager
```

After a published `pipx` install, run this once if needed:

```bash
pipx ensurepath
source ~/.bashrc
```

## Quick Start

```bash
gpumanager install-systemd
gpumanager init
```

During `init` and interactive `config set`, the CLI shows the current server time and a few common cron examples so it is easier to enter `report.report_time`.

## Test

```bash
gpumanager sample
gpumanager test
```

If systemd timers are already installed, `gpumanager init` and `gpumanager config set` automatically rewrite and reload the installed timer files so schedule changes take effect immediately.

## Commands

- `gpumanager init`
- `gpumanager config set`
- `gpumanager config show`
- `gpumanager sample`
- `gpumanager report`
- `gpumanager test`
- `gpumanager delete-csv`
- `gpumanager status`
- `gpumanager install-systemd`
- `gpumanager uninstall-systemd`
- `gpumanager disable-sample`
- `gpumanager disable-report`

## Configuration

The tool searches for configuration in this order:

1. Path passed with `--config`
2. `GPUMANAGER_CONFIG`
3. `~/.config/gpumanager/config.toml`
4. `/etc/gpumanager/config.toml`

Example:

```toml
[slack]
webhook_url = "https://hooks.slack.com/services/..."

[storage]
csv_dir = "/var/lib/gpumanager"

[sample]
interval = "1m"

[report]
report_time = "0 9 * * *"
interval = "1h"

[general]
timezone = "Asia/Seoul"
server_name = "AICA_H100"
```

Common `report_time` examples:

- Every day at 09:00: `0 9 * * *`
- Every hour: `0 * * * *`
- Every 10 minutes: `*/10 * * * *`

Sampling examples:

- Every 7 seconds: `7s`
- Every 30 seconds: `30s`
- Every 2 minutes: `2m`
- Every 15 minutes: `15m`
- Every hour: `1h`

## Before Running Reports

A few things must be prepared by the user before `gpumanager` can collect data and send Slack notifications:

- `nvidia-smi` must work on the server
- A valid Slack incoming webhook URL must be configured
- The CSV storage directory must be writable
- If you want automatic collection and reporting, the user-level `systemd` timers must be enabled

Quick manual verification:

```bash
nvidia-smi
gpumanager config show
gpumanager sample
gpumanager test
```

## Automatic Scheduling

`gpumanager` does not start background collection on its own. To run sampling every minute and reporting on the configured cron-style schedule, install and enable the user timers.

Install and enable timer files:

```bash
gpumanager install-systemd
```

Check timer status:

```bash
systemctl --user status gpumanager-sample.timer
systemctl --user status gpumanager-report.timer
```

Disable only sampling:

```bash
gpumanager disable-sample
```

Disable only reporting:

```bash
gpumanager disable-report
```


## Sampling

Each sample creates a CSV file named like:

```text
2026-03-22T16-21-00.csv
```

Each CSV contains one row per GPU:

```csv
timestamp,gpu_index,gpu_uuid,gpu_name,util_gpu
2026-03-22T16:21:00+09:00,0,GPU-aaa,NVIDIA A100,35
2026-03-22T16:21:00+09:00,1,GPU-bbb,NVIDIA A100,2
```

## Report Format

Reports use the configured `general.server_name` as the bracketed name prefix. Average GPU utilization is rounded to two decimal places.

Example:

```text
[AICA_H100] 2025.09.06 16:49:32 KST
Window: last 1h
GPU 0: 31.38%
GPU 1: 29.39%
GPU 2: 31.57%
GPU 3: 56.36%
GPU 4: 61.25%
GPU 5: 61.52%
GPU 6: 59.88%
GPU 7: 63.93%
```

## systemd

`gpumanager install-systemd` installs user services into `~/.config/systemd/user/`:

- `gpumanager-sample.service`
- `gpumanager-sample.timer`
- `gpumanager-report.service`
- `gpumanager-report.timer`


## Notes

- `report.report_time` uses a 5-field cron string such as `0 9 * * *`
- `sample.interval` controls how often GPU utilization is sampled and saved
- `report.interval` controls the aggregation window shown as `Window: last ...` and supports minute-based values such as `1m`
- Missing samples are ignored during aggregation
- The README content is used as the package long description, so this setup guide will also be visible on package index web pages after publishing
