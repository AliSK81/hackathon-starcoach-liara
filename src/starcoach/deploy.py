"""Pack a project and deploy it through the Liara API (research 02 §2-3), no Liara CLI needed."""

from __future__ import annotations

import fnmatch
import io
import os
import tarfile
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .liara import LiaraClient, LiaraError, _q
from .recommend import DEFAULT_PORTS

# Always skipped (liara-cloud/cli@14ec35f:src/utils/create-archive.ts:10-21), plus env files and caches.
ALWAYS_IGNORE = [".git", ".idea", ".vscode", ".next", ".dockerignore", "*.*~", "liara.json",
                 "node_modules", "bower_components", ".DS_Store",
                 ".env", ".env.*", "__pycache__", "*.pyc", ".venv", "venv"]
KEEP = {".env.example"}
MAX_SOURCE_BYTES = 256 * 1024 * 1024  # client limit in the CLI (src/constants.ts:29)
FINAL_STATES = {"READY", "FAILED", "UNHEALTHY", "TIMEDOUT", "CANCELED"}


def ignore_patterns(root: Path) -> list[str]:
    """Root ignore file, CLI priority: .liaraignore, then .dockerignore, then .gitignore."""
    for name in (".liaraignore", ".dockerignore", ".gitignore"):
        f = root / name
        if f.is_file():
            lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
            return [l.strip() for l in lines if l.strip() and not l.startswith(("#", "!"))]
    return []


def is_ignored(rel: str, is_dir: bool, patterns: list[str]) -> bool:
    name = rel.rsplit("/", 1)[-1]
    if name in KEEP:
        return False
    for pat in patterns:
        dir_only = pat.endswith("/")
        p = pat.strip("/")
        if dir_only and not is_dir:
            continue
        anchored = pat.startswith("/") or "/" in p
        if anchored and fnmatch.fnmatch(rel, p):
            return True
        if not anchored and fnmatch.fnmatch(name, p):
            return True
    return False


def pack(root: Path) -> tuple[bytes, list[str]]:
    """tar.gz of the project, paths relative to root. Returns (bytes, files included)."""
    root = Path(root).resolve()
    patterns = ALWAYS_IGNORE + ignore_patterns(root)
    files: list[str] = []
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz", compresslevel=9) as tar:
        for dirpath, dirnames, filenames in os.walk(root):
            rel_dir = Path(dirpath).relative_to(root).as_posix()
            rel_dir = "" if rel_dir == "." else rel_dir + "/"
            dirnames[:] = sorted(d for d in dirnames if not is_ignored(rel_dir + d, True, patterns))
            for fn in sorted(filenames):
                rel = rel_dir + fn
                if is_ignored(rel, False, patterns):
                    continue
                tar.add(os.path.join(dirpath, fn), arcname=rel, recursive=False)
                files.append(rel)
    if not files:
        raise ValueError("Nothing to upload: every file is ignored or the folder is empty.")
    data = buf.getvalue()
    if len(data) > MAX_SOURCE_BYTES:
        raise ValueError(f"The package is {len(data) // 2**20} MB. Liara accepts at most 256 MB.")
    return data, files


def multipart(field_name: str, filename: str, data: bytes) -> tuple[bytes, str]:
    boundary = "starcoach" + uuid.uuid4().hex
    head = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field_name}\"; "
            f"filename=\"{filename}\"\r\nContent-Type: application/gzip\r\n\r\n").encode()
    body = head + data + f"\r\n--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


@dataclass
class DeployResult:
    app: str
    release_id: str = ""
    state: str = ""
    fail_reason: str = ""
    files: int = 0
    size_kb: int = 0
    error_lines: list[str] = field(default_factory=list)
    last_lines: list[str] = field(default_factory=list)
    seconds: int = 0
    url: str = ""

    @property
    def ok(self) -> bool:
        return self.state == "READY"

    def to_dict(self) -> dict:
        return {**asdict(self), "ok": self.ok}


class Deployer:
    def __init__(self, client: LiaraClient, on_event=None, poll_seconds: float = 2.0,
                 max_seconds: float = 1500, sleep=time.sleep):
        self.client = client
        self.on_event = on_event or (lambda kind, data: None)
        self.poll_seconds = poll_seconds
        self.max_seconds = max_seconds
        self.sleep = sleep

    def deploy(self, root: Path, app: str, port: int | None = None, message: str = "") -> DeployResult:
        started = time.monotonic()
        result = DeployResult(app=app, url=f"https://{app}.liara.run")
        project = self.client.get_app(app)
        if not project.get("scale"):
            raise LiaraError(f"The app {app} is turned off. Turn it on first, then deploy.")
        platform = project.get("type") or "node"
        port = port or DEFAULT_PORTS.get(platform, 3000)
        data, files = pack(root)
        result.files, result.size_kb = len(files), len(data) // 1024
        self.on_event("packed", {"files": len(files), "size_kb": result.size_kb})
        body, ctype = multipart("file", "source.tar.gz", data)
        up = self.client.request("POST", f"/v2/projects/{_q(app)}/sources", raw=body,
                                 content_type=ctype, timeout=600)
        self.on_event("uploaded", {"source_id": up.get("sourceID")})
        release = {"sourceID": up.get("sourceID"), "type": platform, "port": port,
                   "message": message or "deployed by StarCoach", "build": {"cache": True}}
        rel = self.client.request("POST", f"/v2/projects/{_q(app)}/releases", body=release)
        result.release_id = rel.get("releaseID", "")
        self.on_event("release_created", {"release_id": result.release_id, "port": port, "platform": platform})
        self._follow(result, started)
        result.seconds = int(time.monotonic() - started)
        self.on_event("deploy_done", result.to_dict())
        return result

    def _follow(self, result: DeployResult, started: float):
        since = None
        lines: list[str] = []
        while time.monotonic() - started < self.max_seconds:
            params = {"since": since} if since else None
            resp = self.client.request("GET", f"/v2/releases/{result.release_id}/build-logs", params=params)
            output = resp.get("buildOutput") or []
            state = (resp.get("release") or {}).get("state", "")
            for item in output:
                line = str(item.get("line", "")).rstrip()
                lines.append(line)
                if item.get("stream", "STDOUT") != "STDOUT":
                    result.error_lines.append(line)
                since = item.get("createdAt") or since
            if output:
                self.on_event("build_log", {"lines": [str(i.get("line", "")).rstrip() for i in output][-5:],
                                            "state": state})
            if state != result.state:
                result.state = state
                self.on_event("state", {"state": state})
            if state in FINAL_STATES and not output:
                result.fail_reason = (resp.get("release") or {}).get("failReason") or ""
                break
            self.sleep(self.poll_seconds)
        else:
            result.state = result.state or "TIMEDOUT"
        result.last_lines = lines[-20:]


def release_status(client: LiaraClient, release_id: str) -> dict:
    release = client.request("GET", f"/v1/releases/{release_id}").get("release", {})
    return {"state": release.get("state"), "fail_reason": release.get("failReason"),
            "queue": release.get("queue")}
