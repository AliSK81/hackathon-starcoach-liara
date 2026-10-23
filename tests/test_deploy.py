import io
import json
import tarfile

import pytest

from starcoach.deploy import Deployer, is_ignored, pack
from starcoach.liara import LiaraClient, LiaraError


def tree(root, files):
    for name, text in files.items():
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return root


def names(data):
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        return sorted(m.name for m in tar.getmembers())


def test_pack_skips_secrets_and_junk(tmp_path):
    tree(tmp_path, {"server.js": "x", "package.json": "{}", ".env": "SECRET=1", ".env.local": "S=2",
                    ".env.example": "S=", "node_modules/a/index.js": "x", ".git/HEAD": "x",
                    "logs/app.log": "x", "src/keep.js": "x", ".gitignore": "logs/\n*.log\n"})
    data, files = pack(tmp_path)
    assert names(data) == sorted(files) == [".env.example", ".gitignore", "package.json", "server.js", "src/keep.js"]


def test_liaraignore_wins_over_gitignore(tmp_path):
    tree(tmp_path, {"a.txt": "x", "b.txt": "x", ".liaraignore": "a.txt\n", ".gitignore": "b.txt\n"})
    _, files = pack(tmp_path)
    assert "a.txt" not in files and "b.txt" in files


def test_anchored_patterns():
    assert is_ignored("build/out.js", False, ["/build"]) is False  # file inside; dir check happens on walk
    assert is_ignored("build", True, ["/build"]) is True
    assert is_ignored("src/build", True, ["/build"]) is False
    assert is_ignored("src/x.log", False, ["*.log"]) is True


def test_pack_empty_folder_fails(tmp_path):
    with pytest.raises(ValueError):
        pack(tmp_path)


class DeployAPI:
    """Fake Liara for a deploy: build logs arrive over three polls, then READY."""

    def __init__(self, final="READY", scale=1):
        self.final, self.scale = final, scale
        self.calls, self.polls = [], 0

    def __call__(self, method, url, headers, body, timeout):
        path = "/" + url.split("://", 1)[1].split("/", 1)[1]
        self.calls.append((method, path.split("?")[0], headers.get("Content-Type", "")))
        if path.startswith("/v1/projects/shop"):
            return 200, json.dumps({"project": {"type": "node", "scale": self.scale}}).encode()
        if path.endswith("/sources"):
            assert b"source.tar.gz" in body
            return 200, b'{"sourceID": "s1"}'
        if path.endswith("/releases"):
            release = json.loads(body)
            assert release["sourceID"] == "s1" and release["port"] == 3000 and release["type"] == "node"
            return 200, b'{"releaseID": "r1"}'
        if "/build-logs" in path:
            self.polls += 1
            out = {1: [{"line": "npm install", "stream": "STDOUT", "createdAt": "t1"}],
                   2: [{"line": "npm WARN old", "stream": "STDERR", "createdAt": "t2"}]}.get(self.polls, [])
            state = "BUILDING" if self.polls < 3 else self.final
            return 200, json.dumps({"release": {"state": state, "failReason": "boom" if state == "FAILED" else None},
                                    "buildOutput": out}).encode()
        return 404, b"{}"


def make(tmp_path, api):
    tree(tmp_path, {"server.js": "x", "package.json": '{"scripts":{"start":"node server.js"}}'})
    client = LiaraClient("tok", "https://api.test", transport=api, retry_wait=0)
    events = []
    d = Deployer(client, on_event=lambda k, data: events.append(k), sleep=lambda s: None)
    return d, events


def test_build_failure_explained_from_real_npm_output():
    from starcoach.deploy import explain_build_failure
    # Real lines from a failed Liara build (F25); npm prints them in red on STDOUT.
    lines = ["> Running npm install...",
             "\x1b[91mnpm error code E404\nnpm error 404 Not Found - GET http://10.16.100.42/repository/npm-proxy/starcoach-package-that-does-not-exist-xyz\n",
             "\x1b[91mnpm error 404  'starcoach-package-that-does-not-exist-xyz@^9.9.9' is not in this registry.\n",
             "The command '/bin/bash -o pipefail -c chmod +x /usr/local/lib/liara/*.sh' returned a non-zero code: 1"]
    e = explain_build_failure(lines)
    assert "starcoach-package-that-does-not-exist-xyz" in e["cause"] and "package.json" in e["fix"]
    assert explain_build_failure(["all good"]) is None


def test_deploy_success(tmp_path):
    api = DeployAPI()
    d, events = make(tmp_path, api)
    r = d.deploy(tmp_path, "shop")
    assert r.ok and r.release_id == "r1" and r.files == 2
    assert r.error_lines == ["npm WARN old"]
    assert [c[1] for c in api.calls[:3]] == ["/v1/projects/shop", "/v2/projects/shop/sources", "/v2/projects/shop/releases"]
    assert api.calls[1][2].startswith("multipart/form-data; boundary=")
    assert events[:3] == ["packed", "uploaded", "release_created"] and events[-1] == "deploy_done"


def test_deploy_failure_reports_reason(tmp_path):
    d, _ = make(tmp_path, DeployAPI(final="FAILED"))
    r = d.deploy(tmp_path, "shop")
    assert not r.ok and r.state == "FAILED" and r.fail_reason == "boom"


def test_deploy_refuses_stopped_app(tmp_path):
    d, _ = make(tmp_path, DeployAPI(scale=0))
    with pytest.raises(LiaraError, match="turned off"):
        d.deploy(tmp_path, "shop")
