#!/usr/bin/env python3
import json
import os
import queue
import socket
import threading
import urllib.error
import urllib.request
from pathlib import Path
from tkinter import (
    END,
    BOTH,
    LEFT,
    RIGHT,
    VERTICAL,
    BooleanVar,
    Button,
    Checkbutton,
    Entry,
    Frame,
    Label,
    Scrollbar,
    StringVar,
    Text,
    Tk,
    filedialog,
    messagebox,
)


MAX_READ_BYTES = 1_000_000
MAX_WRITE_BYTES = 5_000_000
MAX_DIR_ITEMS = 500
MAX_TOOL_ROUNDS = 4


class AgentClientApp:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title("AIBOX Remote Agent")
        self.root.geometry("920x680")

        self.server_url = StringVar(value="http://192.168.150.1:8765")
        self.agent_token = StringVar(value=os.environ.get("AIBOX_AGENT_TOKEN", ""))
        self.workspace = StringVar(value=str(Path.home() / "offline-agent-workspace"))
        self.client_name = StringVar(value=socket.gethostname())
        self.status_text = StringVar(value="Choose a workspace, connect, then send a request.")
        self.show_tool_details = BooleanVar(value=False)
        self.session_id: str | None = None
        self.is_connected = False
        self.is_busy = False
        self.ui_queue: queue.Queue[tuple[str, tuple]] = queue.Queue()

        self.chat_log = Text(root, wrap="word", state="disabled")
        self.chat_log.pack(fill=BOTH, expand=True, padx=12, pady=(12, 0))

        scrollbar = Scrollbar(self.chat_log, orient=VERTICAL, command=self.chat_log.yview)
        scrollbar.pack(side=RIGHT, fill="y")
        self.chat_log.configure(yscrollcommand=scrollbar.set)

        header = Frame(root)
        header.pack(fill="x", padx=12, pady=(10, 6))

        Label(header, text="AIBOX Remote Agent", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        Label(
            header,
            text="Remote AI on linaro, local files on this PC.",
        ).pack(anchor="w")

        controls = Frame(root)
        controls.pack(fill="x", padx=12, pady=6)

        Label(controls, text="Server").grid(row=0, column=0, sticky="w")
        Entry(controls, textvariable=self.server_url, width=44).grid(row=0, column=1, sticky="ew", padx=(6, 8))
        Button(controls, text="Connect", command=self.connect).grid(row=0, column=2, padx=(0, 8))

        Label(controls, text="Token").grid(row=1, column=0, sticky="w")
        Entry(controls, textvariable=self.agent_token, width=44, show="*").grid(row=1, column=1, sticky="ew", padx=(6, 8))

        Label(controls, text="Workspace").grid(row=2, column=0, sticky="w")
        Entry(controls, textvariable=self.workspace, width=44).grid(row=2, column=1, sticky="ew", padx=(6, 8))
        Button(controls, text="Browse", command=self.pick_workspace).grid(row=2, column=2, padx=(0, 8))

        Label(controls, text="Client").grid(row=3, column=0, sticky="w")
        Entry(controls, textvariable=self.client_name, width=44).grid(row=3, column=1, sticky="ew", padx=(6, 8))
        Checkbutton(
            controls,
            text="Show tool details",
            variable=self.show_tool_details,
        ).grid(row=3, column=2, sticky="w")

        controls.columnconfigure(1, weight=1)

        actions = Frame(root)
        actions.pack(fill="x", padx=12, pady=(2, 8))
        Label(actions, text="Quick actions").pack(side=LEFT)
        Button(actions, text="Pretty Hello World", command=lambda: self.queue_prompt("Create a pretty hello world website.")).pack(side=LEFT, padx=(10, 6))
        Button(actions, text="List Workspace", command=lambda: self.queue_prompt("List the files in my workspace.")).pack(side=LEFT, padx=6)
        Button(actions, text="New Session", command=self.connect).pack(side=LEFT, padx=6)

        status_bar = Frame(root)
        status_bar.pack(fill="x", padx=12, pady=(0, 8))
        Label(status_bar, textvariable=self.status_text, anchor="w").pack(fill="x")

        composer = Frame(root)
        composer.pack(fill="x", padx=12, pady=(0, 12))

        self.message_entry = Entry(composer)
        self.message_entry.pack(side=LEFT, fill="x", expand=True)
        self.message_entry.bind("<Return>", lambda event: self.send_message())
        self.send_button = Button(composer, text="Send", command=self.send_message)
        self.send_button.pack(side=LEFT, padx=(8, 0))

        self.append_chat("system", "Select a workspace on this PC, connect to the linaro agent, then describe what you want built or changed.")
        self.root.after(50, self.process_ui_queue)

    def process_ui_queue(self) -> None:
        while True:
            try:
                action, args = self.ui_queue.get_nowait()
            except queue.Empty:
                break
            if action == "chat":
                self.append_chat(*args)
            elif action == "summary":
                self.append_result_summary(*args)
            elif action == "status":
                self.set_status(*args)
            elif action == "busy":
                self.set_busy(*args)
        self.root.after(50, self.process_ui_queue)

    def ui(self, action: str, *args) -> None:
        self.ui_queue.put((action, args))

    def append_chat(self, role: str, message: str) -> None:
        if role == "tool" and not self.show_tool_details.get():
            return
        self.chat_log.configure(state="normal")
        self.chat_log.insert(END, f"[{role}] {message}\n\n")
        self.chat_log.configure(state="disabled")
        self.chat_log.see(END)

    def append_result_summary(self, written_paths: list[str], read_paths: list[str]) -> None:
        lines = []
        if written_paths:
            lines.append("Updated files:")
            for path in written_paths:
                lines.append(f"- {path}")
        if read_paths:
            lines.append("Read files:")
            for path in read_paths:
                lines.append(f"- {path}")
        if not lines:
            return
        self.chat_log.configure(state="normal")
        self.chat_log.insert(END, "[result] " + "\n".join(lines) + "\n\n")
        self.chat_log.configure(state="disabled")
        self.chat_log.see(END)

    def set_status(self, message: str) -> None:
        self.status_text.set(message)

    def set_busy(self, busy: bool, message: str) -> None:
        self.is_busy = busy
        self.send_button.configure(state="disabled" if busy else "normal")
        self.message_entry.configure(state="disabled" if busy else "normal")
        self.set_status(message)
        if busy:
            self.append_chat("system", "Model generating response...")

    def pick_workspace(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.workspace.get() or str(Path.home()))
        if selected:
            self.workspace.set(selected)

    def queue_prompt(self, prompt: str) -> None:
        self.message_entry.delete(0, END)
        self.message_entry.insert(0, prompt)
        self.send_message()

    def connect(self) -> None:
        if self.is_busy:
            return
        workspace_value = self.workspace.get()
        client_name_value = self.client_name.get().strip() or socket.gethostname()
        server_url_value = self.server_url.get().strip()
        token_value = self.agent_token.get().strip()
        self.set_status("Connecting to remote agent...")
        threading.Thread(
            target=self._connect_worker,
            args=(workspace_value, client_name_value, server_url_value, token_value),
            daemon=True,
        ).start()

    def _connect_worker(
        self,
        workspace_value: str,
        client_name_value: str,
        server_url_value: str,
        token_value: str,
    ) -> None:
        workspace = Path(workspace_value).resolve()
        workspace.mkdir(parents=True, exist_ok=True)

        payload = {
            "client_name": client_name_value,
            "workspace_root": str(workspace),
        }
        try:
            response = self.api_post("/session/start", payload, server_url_value, token_value)
        except Exception as exc:
            self.is_connected = False
            self.ui("status", "Connection failed.")
            self.ui("chat", "system", f"Connection failed: {exc}")
            return

        session_id = response.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            self.is_connected = False
            self.ui("status", "Connection failed.")
            self.ui("chat", "system", f"Connection failed: invalid session response {response!r}")
            return
        self.session_id = session_id
        self.is_connected = True
        self.ui("status", f"Connected to {server_url_value.rstrip('/')} with workspace {workspace}")
        self.ui("chat", "system", f"Connected. Workspace locked to: {workspace}")

    def send_message(self) -> None:
        if self.is_busy:
            return
        message = self.message_entry.get().strip()
        if not message:
            return
        self.message_entry.delete(0, END)
        self.append_chat("user", message)
        self.set_busy(True, "Model generating response...")
        server_url_value = self.server_url.get().strip()
        token_value = self.agent_token.get().strip()
        threading.Thread(
            target=self._send_message_worker,
            args=(message, server_url_value, token_value),
            daemon=True,
        ).start()

    def _send_message_worker(self, message: str, server_url_value: str, token_value: str) -> None:
        if not self.session_id:
            self.ui("busy", False, "Not connected.")
            self.ui("chat", "system", "Connect to the server first.")
            return

        payload = {
            "session_id": self.session_id,
            "message": message,
        }
        try:
            response = self.api_post("/session/message", payload, server_url_value, token_value)
            self.handle_server_response(response, server_url_value, token_value)
            self.ui("busy", False, "Ready.")
        except Exception as exc:
            self.ui("busy", False, "Request failed.")
            self.ui("chat", "system", f"Request failed: {exc}")

    def handle_server_response(
        self,
        response: dict,
        server_url_value: str,
        token_value: str,
        round_count: int = 0,
    ) -> None:
        if "error" in response:
            raise RuntimeError(str(response["error"]))
        if round_count >= MAX_TOOL_ROUNDS:
            raise RuntimeError("too many tool rounds from server")

        reply = response.get("reply")
        if reply:
            self.ui("chat", "assistant", str(reply))

        tool_calls = response.get("tool_calls", [])
        if tool_calls:
            results, written_paths, read_paths = self.execute_tool_calls(tool_calls)
            self.ui("summary", written_paths, read_paths)
            follow_up = self.api_post(
                "/session/tools",
                {
                    "session_id": self.session_id,
                    "results": results,
                },
                server_url_value,
                token_value,
            )
            self.handle_server_response(follow_up, server_url_value, token_value, round_count + 1)

    def execute_tool_calls(self, tool_calls: list[dict]) -> tuple[list[dict], list[str], list[str]]:
        results = []
        written_paths: list[str] = []
        read_paths: list[str] = []
        for call in tool_calls:
            result, wrote_path, read_path = self.execute_tool_call(call)
            results.append(result)
            if wrote_path:
                written_paths.append(wrote_path)
            if read_path:
                read_paths.append(read_path)
        return results, written_paths, read_paths

    def execute_tool_call(self, call: dict) -> tuple[dict, str | None, str | None]:
        call_id = call["id"]
        name = call["name"]
        args = call.get("args", {})
        self.ui("chat", "tool", f"{name} {json.dumps(args)}")
        try:
            if not isinstance(args, dict):
                raise ValueError("tool args must be an object")
            if name == "write_file":
                output, written_path = self.write_file(args["path"], args["content"])
                read_path = None
            elif name == "list_dir":
                output = self.list_dir(args.get("path", "."))
                written_path = None
                read_path = None
            elif name == "read_file":
                output, read_path = self.read_file(args["path"])
                written_path = None
            else:
                raise ValueError(f"Unsupported tool: {name}")
            self.ui("chat", "tool", output)
            return {"tool_call_id": call_id, "ok": True, "output": output}, written_path, read_path
        except Exception as exc:
            error = f"{name} failed: {exc}"
            self.ui("chat", "tool", error)
            return {"tool_call_id": call_id, "ok": False, "output": error}, None, None

    def workspace_path(self, relative_path: str) -> Path:
        if not isinstance(relative_path, str) or not relative_path.strip():
            raise ValueError("path must be a non-empty string")
        if "\x00" in relative_path:
            raise ValueError("path contains a null byte")
        root = Path(self.workspace.get()).resolve()
        candidate = (root / relative_path).resolve()
        if root != candidate and root not in candidate.parents:
            raise ValueError("path escapes workspace")
        return candidate

    def write_file(self, relative_path: str, content: str) -> tuple[str, str]:
        if not isinstance(content, str):
            raise ValueError("content must be a string")
        if len(content.encode("utf-8")) > MAX_WRITE_BYTES:
            raise ValueError(f"content exceeds {MAX_WRITE_BYTES} bytes")
        target = self.workspace_path(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Wrote {target}", relative_path

    def list_dir(self, relative_path: str) -> str:
        target = self.workspace_path(relative_path)
        if not target.exists():
            return f"{target} does not exist"
        if not target.is_dir():
            raise NotADirectoryError(str(target))
        children = sorted(target.iterdir(), key=lambda child: (not child.is_dir(), child.name.lower()))
        items = [
            {"name": child.name, "type": "dir" if child.is_dir() else "file"}
            for child in children[:MAX_DIR_ITEMS]
        ]
        if len(children) > MAX_DIR_ITEMS:
            items.append({"name": f"... {len(children) - MAX_DIR_ITEMS} more", "type": "truncated"})
        return json.dumps(items)

    def read_file(self, relative_path: str) -> tuple[str, str]:
        target = self.workspace_path(relative_path)
        if not target.exists():
            raise FileNotFoundError(str(target))
        if not target.is_file():
            raise IsADirectoryError(str(target))
        if target.stat().st_size > MAX_READ_BYTES:
            raise ValueError(f"file exceeds {MAX_READ_BYTES} bytes")
        return target.read_text(encoding="utf-8"), relative_path

    def api_post(self, path: str, payload: dict, server_url_value: str, token_value: str) -> dict:
        if not server_url_value:
            raise RuntimeError("server URL is empty")
        url = f"{server_url_value.rstrip('/')}{path}"
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if token_value:
            headers["X-AIBOX-Token"] = token_value
        request = urllib.request.Request(
            url,
            data=data,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Network error: {exc.reason}") from exc
        return json.loads(body)


def main() -> None:
    root = Tk()
    app = AgentClientApp(root)

    def on_close() -> None:
        if messagebox.askokcancel("Quit", "Close AIBOX Remote Agent?"):
            root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
