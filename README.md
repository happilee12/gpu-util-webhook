# gpumanager

`gpumanager` is now officially released on PyPI.

- PyPI: https://pypi.org/project/gpumanager/
- Website: https://happilee12.github.io/gpu-util-webhook/
- Release branch: `pip-release`

## Install

```bash
pip install gpumanager
# or
pipx install gpumanager
```

If you install with `pipx`, run:

```bash
pipx ensurepath
source ~/.bashrc
```

## What It Does

`gpumanager` is a lightweight Python CLI for NVIDIA GPU servers.
It samples GPU utilization with `nvidia-smi`, stores one CSV file per sample, aggregates utilization over a configured window, and sends reports through a Slack incoming webhook.

## Quick Start

```bash
gpumanager install-systemd
gpumanager init
gpumanager sample
gpumanager test
```

## Links

- PyPI package: https://pypi.org/project/gpumanager/
- Project website: https://happilee12.github.io/gpu-util-webhook/
- Slack webhook setup guide: https://docs.slack.dev/messaging/sending-messages-using-incoming-webhooks/

