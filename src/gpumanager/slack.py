from __future__ import annotations

import json
from urllib import request
from urllib.error import HTTPError, URLError


# Slack incoming webhooks accept a small JSON payload with a text field.
def send_slack_message(webhook_url: str, text: str) -> None:
    if not webhook_url:
        raise ValueError("Slack webhook URL is not configured")

    payload = json.dumps({"text": text}).encode("utf-8")
    req = request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=10) as response:
            response.read()
    except HTTPError as exc:
        raise RuntimeError(f"Slack webhook returned HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"Failed to send Slack webhook: {exc.reason}") from exc
