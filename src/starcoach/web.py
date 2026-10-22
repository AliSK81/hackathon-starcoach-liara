"""Local web chat: stdlib HTTP server, SSE for live status, approval cards for risky tools."""

from __future__ import annotations

import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .tools import DANGER

STATIC = Path(__file__).parent / "static"
APPROVAL_TIMEOUT = 600
MAX_HISTORY = 500


class Session:
    """One browser tab: an agent, its event stream, and its pending approvals."""

    def __init__(self, make_agent, log=None):
        # Events are kept with sequence numbers; each SSE connection replays from its last seen id,
        # so a reconnect never loses or steals events.
        self.history: list[dict] = []
        self.seq = 0
        self.changed = threading.Condition()
        self.pending: dict[str, dict] = {}
        self.lock = threading.Lock()
        self.busy = False
        self.log = log
        self.agent = make_agent(approver=self.approve, on_event=self.push)

    def push(self, kind: str, data: dict):
        with self.changed:
            self.seq += 1
            self.history.append({"seq": self.seq, "kind": kind, **data})
            del self.history[:-MAX_HISTORY]
            self.changed.notify_all()

    def events_after(self, seq: int, timeout: float) -> list[dict]:
        with self.changed:
            newer = [e for e in self.history if e["seq"] > seq]
            if not newer:
                self.changed.wait(timeout)
                newer = [e for e in self.history if e["seq"] > seq]
            return newer

    def approve(self, tool, args) -> bool:
        """Called from the agent thread. Blocks until the user answers the card."""
        approval_id = uuid.uuid4().hex[:10]
        done = threading.Event()
        with self.lock:
            self.pending[approval_id] = {"tool": tool.name, "args": args, "risk": tool.risk,
                                         "done": done, "ok": False}
        self.push("approval_card", {"id": approval_id, "tool": tool.name, "risk": tool.risk,
                                    "description": tool.description, "args": tool.safe_args(args),
                                    "type_to_confirm": args.get("app") if tool.risk == DANGER else None})
        answered = done.wait(APPROVAL_TIMEOUT)
        with self.lock:
            item = self.pending.pop(approval_id, None)
        ok = bool(answered and item and item["ok"])
        if not answered:
            self.push("approval_expired", {"id": approval_id, "tool": tool.name})
        return ok

    def answer(self, approval_id: str, approve: bool, typed: str = "") -> tuple[bool, str]:
        with self.lock:
            item = self.pending.get(approval_id)
            if item is None or item["done"].is_set():
                return False, "This approval is no longer open."
            if approve and item["risk"] == DANGER and typed.strip() != str(item["args"].get("app", "")):
                return False, "Type the app name exactly to approve this high-risk action."
            item["ok"] = approve
            item["done"].set()
        if self.log is not None:
            self.log.write("approval", id=approval_id, tool=item["tool"], approved=approve)
        return True, "ok"

    def ask(self, text: str) -> bool:
        with self.lock:
            if self.busy:
                return False
            self.busy = True

        def run():
            try:
                self.agent.ask(text)
            except Exception as exc:  # show the error in the page; keep the server alive
                self.push("error", {"error": str(exc)})
            finally:
                with self.lock:
                    self.busy = False
                self.push("idle", {})

        threading.Thread(target=run, daemon=True).start()
        return True


class App:
    def __init__(self, make_agent, log=None):
        self.make_agent = make_agent
        self.log = log
        self.sessions: dict[str, Session] = {}
        self.lock = threading.Lock()

    def session(self, sid: str) -> Session:
        with self.lock:
            if sid not in self.sessions:
                self.sessions[sid] = Session(self.make_agent, self.log)
            return self.sessions[sid]


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # quiet console; events go to the JSONL log
            pass

        def _json(self, code: int, payload: dict):
            body = json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            try:
                return json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                return {}

        def do_GET(self):
            url = urlparse(self.path)
            if url.path in ("/", "/index.html"):
                body = (STATIC / "index.html").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif url.path == "/api/events":
                query = parse_qs(url.query)
                sid = (query.get("session") or [""])[0]
                after = self.headers.get("Last-Event-ID") or (query.get("after") or ["0"])[0]
                self.stream(app.session(sid), int(after) if str(after).isdigit() else 0)
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self):
            data = self._body()
            sid = str(data.get("session", ""))
            if not sid:
                return self._json(400, {"error": "missing session"})
            if self.path == "/api/chat":
                text = str(data.get("text", "")).strip()
                if not text:
                    return self._json(400, {"error": "empty message"})
                started = app.session(sid).ask(text)
                return self._json(202 if started else 409,
                                  {"ok": started, **({} if started else {"error": "still working"})})
            if self.path == "/api/approve":
                ok, msg = app.session(sid).answer(str(data.get("id", "")), bool(data.get("approve")),
                                                  str(data.get("typed", "")))
                return self._json(200 if ok else 400, {"ok": ok, "message": msg})
            self._json(404, {"error": "not found"})

        def stream(self, session: Session, seq: int):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            try:
                while True:
                    events = session.events_after(seq, timeout=15)
                    chunk = "".join(f"id: {e['seq']}\ndata: {json.dumps(e, ensure_ascii=False, default=str)}\n\n"
                                    for e in events) or ": keep-alive\n\n"
                    if events:
                        seq = events[-1]["seq"]
                    self.wfile.write(chunk.encode())
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                return

    return Handler


def serve(make_agent, host: str = "127.0.0.1", port: int = 8765, log=None) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), make_handler(App(make_agent, log)))
    server.daemon_threads = True
    return server
