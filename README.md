# gpumanager

`gpumanager` is a lightweight Python CLI tool for sampling NVIDIA GPU utilization, storing minute-by-minute CSV snapshots, aggregating utilization over a reporting window, and sending GPU-wise summaries to Slack. It is designed to work together with a Slack incoming webhook for notifications.

The installable Python distribution is named `gpumanager`. The CLI entrypoint is `gpumanager`.

Website: https://happilee12.github.io/gpu-util-webhook/
Pip Page: https://pypi.org/project/gpumanager/

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

During `init`, the CLI shows the current server time and a few common cron examples so it is easier to enter `report.report_time`.

If you edit the config file manually after timers are installed, run `gpumanager reload` to apply the updated systemd timer settings.

## Troubleshooting

### 4. Test

After finishing the configuration, send a test report.

```bash
gpumanager test-sample
gpumanager test-report
```

If the Slack message arrives normally, the setup is working.

If the message is delivered here but does not arrive at the scheduled time, `gpumanager install-systemd` may not have been run yet. In that case, run `gpumanager status` and check `sample_timer_installed`, `report_timer_installed`, `sample.next_trigger`, and `report.next_trigger`. The next scheduled runs are visible directly in status output, for example `"sample.next_trigger": "Tue 2026-03-24 14:41:35 KST; 9s left"` and `"report.next_trigger": "Tue 2026-03-24 14:42:00 KST; 33s left"`.

If systemd timers are already installed, `gpumanager init` automatically rewrites and reloads the installed timer files so schedule changes take effect immediately. If you edit the config file manually later, run `gpumanager reload`. 

## Commands

- `gpumanager init`
- `gpumanager test-sample`
- `gpumanager test-report`
- `gpumanager delete-csv`
- `gpumanager status`
- `gpumanager install-systemd`
- `gpumanager uninstall-systemd`
- `gpumanager disable-sample`
- `gpumanager disable-report`
- `gpumanager reload`

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

## Recommended Setup

### 1. Realtime report

Check near-realtime GPU activity every 10 minutes.

```toml
[sample]
interval = "1m"

[report]
report_time = "*/10 * * * *"
interval = "1m"
```

### 2. Daily Average report

This matches the current default-style daily setup.

```toml
[sample]
interval = "1m"

[report]
report_time = "0 9 * * *"
interval = "1d"
```

### 3. Weekly report

Send one summary per week and aggregate the last 7 days.

```toml
[sample]
interval = "1m"

[report]
report_time = "0 9 * * 1"
interval = "7d"
```

## Before Running Reports

A few things must be prepared by the user before `gpumanager` can collect data and send Slack notifications through a Slack incoming webhook:

- `nvidia-smi` must work on the server
- A valid Slack incoming webhook URL must be configured
- The CSV storage directory must be writable
- If you want automatic collection and reporting, the user-level `systemd` timers must be enabled

Slack incoming webhook setup reference:

- https://docs.slack.dev/messaging/sending-messages-using-incoming-webhooks/

Quick manual verification:

```bash
nvidia-smi
gpumanager status
gpumanager test-sample
gpumanager test-report
```

## Automatic Scheduling

`gpumanager` does not start background collection on its own. To run sampling every minute and reporting on the configured cron-style schedule, install and enable the user timers.

Install and enable timer files:

```bash
gpumanager install-systemd
```

Check timer status or reload installed timers:

```bash
gpumanager status
gpumanager reload
```

`gpumanager status` shows the next scheduled sample and report times through `sample.next_trigger` and `report.next_trigger`. 

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
