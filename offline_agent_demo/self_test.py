#!/usr/bin/env python3
import json
import os
import sys
import urllib.request


BASE_URL = "http://127.0.0.1:8765"
AGENT_TOKEN = os.environ.get("AGENT_TOKEN", "")


def post(path: str, payload: dict, timeout: int = 240) -> dict:
    headers = {"Content-Type": "application/json"}
    if AGENT_TOKEN:
        headers["X-AIBOX-Token"] = AGENT_TOKEN
    request = urllib.request.Request(
        BASE_URL + path,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    start = post(
        "/session/start",
        {"client_name": "remote-self-test", "workspace_root": "C:/demo"},
    )
    print("START", json.dumps(start))

    message = post(
        "/session/message",
        {
            "session_id": start["session_id"],
            "message": "Create a hello world site",
        },
        timeout=480,
    )
    print("MESSAGE", json.dumps(message))

    results = []
    for call in message.get("tool_calls", []):
        results.append(
            {
                "tool_call_id": call["id"],
                "ok": True,
                "output": f"simulated {call['name']} ok",
            }
        )

    follow_up = post(
        "/session/tools",
        {"session_id": start["session_id"], "results": results},
        timeout=480,
    )
    print("TOOLS", json.dumps(follow_up))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
