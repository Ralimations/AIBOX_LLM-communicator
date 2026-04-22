# Offline Agent Demo

This prototype implements the architecture we discussed:

- `linaro` is only the AI host.
- The PC or laptop owns the real workspace and all generated files.
- The server asks for tool actions.
- The client executes those tool actions locally and sends results back.

The server supports two backends:

- `mock`: hardcoded demo behavior
- `openai_compat`: talks to a local OpenAI-compatible model server on `linaro`

That second mode is the real model path.

## Files

- `server.py`: runs on `linaro`
- `client.py`: runs on a Windows PC or laptop

## Demo Flow

1. Start the model server on `linaro`, or use mock mode first.
2. Start `server.py` on `linaro`.
3. Start the client on the PC.
4. Point the client at the `linaro` IP.
5. Choose a local workspace folder on the PC.
6. Ask for a site, for example: `Create a hello world site`
7. The server returns tool requests.
8. The client writes files locally and shows the result in the chat log.

## Protocol

The prototype uses a small JSON-over-HTTP protocol.

### `POST /session/start`

Creates a fresh session.

Request:

```json
{
  "client_name": "Supervisor Laptop",
  "workspace_root": "D:\\Projects\\DemoSite"
}
```

Response:

```json
{
  "session_id": "..."
}
```

### `POST /session/message`

Sends a user message and receives either:

- a plain assistant reply
- one or more tool requests

Request:

```json
{
  "session_id": "...",
  "message": "Create a hello world site"
}
```

Response:

```json
{
  "reply": "I will create a minimal site in your local workspace.",
  "tool_calls": [
    {
      "id": "call-1",
      "name": "write_file",
      "args": {
        "path": "index.html",
        "content": "<!doctype html>..."
      }
    }
  ],
  "done": false
}
```

### `POST /session/tools`

Submits local tool results back to the server.

Request:

```json
{
  "session_id": "...",
  "results": [
    {
      "tool_call_id": "call-1",
      "ok": true,
      "output": "Wrote D:\\Projects\\DemoSite\\index.html"
    }
  ]
}
```

Response:

```json
{
  "reply": "The site files were written to your PC workspace.",
  "tool_calls": [],
  "done": true
}
```

## Design Notes

- The server stores lightweight session state and conversation history.
- The client enforces the workspace boundary.
- All file writes stay inside the selected PC folder.
- The model chooses from a small fixed tool set.
- Destructive operations are not implemented in this prototype.

## Running

### One-Command Setup From The PC

If the project folder already contains:

- `llama.cpp-master.zip`
- the GGUF model file
- `server.py`
- `self_test.py`

then you can do the whole remote setup from Windows with:

```powershell
.\setup_linaro_agent.ps1
```

This script will:

- create the remote directories on `linaro`
- upload the model and agent files
- upload and unpack `llama.cpp`
- apply the ARM/GCC compatibility header
- build `llama-server`
- start the model server
- start the agent server
- run the remote self-test

Optional flags:

```powershell
.\setup_linaro_agent.ps1 -SkipBuild
.\setup_linaro_agent.ps1 -SkipStart
```

### Run The Client

To launch the Windows chat client:

```powershell
.\run_client.ps1
```

The script tries:

- `python client.py`
- `py -3 client.py`

### Mock Mode

Server on `linaro`:

```bash
export AGENT_BACKEND=mock
python3 server.py --host 0.0.0.0 --port 8765
```

Client on the PC:

```bash
python client.py
```

### Real Model Mode

The most practical path on `linaro` is to run a local OpenAI-compatible server,
then point `server.py` at it.

Recommended runtime:

- `llama.cpp` `llama-server`

Why:

- lightweight
- offline
- works with quantized GGUF models
- exposes `/v1/chat/completions`

Backend configuration on `linaro`:

```bash
export AGENT_BACKEND=openai_compat
export MODEL_BASE_URL=http://127.0.0.1:8080
export MODEL_NAME=gemma-3-1b-it
python3 server.py --host 0.0.0.0 --port 8765
```

Example `llama-server` command once a GGUF model exists on the device:

```bash
llama-server -m /home/linaro/models/gemma-3-1b-it-q4.gguf --port 8080
```

Then run the agent server:

```bash
export AGENT_BACKEND=openai_compat
export MODEL_BASE_URL=http://127.0.0.1:8080
export MODEL_NAME=gemma-3-1b-it
python3 server.py --host 0.0.0.0 --port 8765
```

## Suggested Starting Models

Start small. On this hardware the safer targets are:

- Gemma `1B` class GGUF
- Qwen `0.5B` to `1.5B` class GGUF
- TinyLlama `1.1B` GGUF

## What Changed In The Server

`server.py` now handles:

- conversation state
- model backend selection
- OpenAI-compatible model calls
- JSON parsing of model replies
- multi-step tool loop after local tool results come back from the PC

## Next Step For Real Deployment

1. Install or build `llama.cpp` on `linaro`.
2. Place one small GGUF model on the device.
3. Start `llama-server`.
4. Run `server.py` in `openai_compat` mode.
5. Connect from the PC client.

The client does not need major changes when that happens.
