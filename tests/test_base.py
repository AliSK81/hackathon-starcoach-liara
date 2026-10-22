import json

from starcoach import cli
from starcoach.config import load_settings, mask, read_env_file
from starcoach.eventlog import EventLog


def test_version_runs_and_logs(tmp_path, monkeypatch, capsys):
    log_file = tmp_path / "events.jsonl"
    monkeypatch.setenv("STARCOACH_LOG", str(log_file))
    assert cli.main(["version"]) == 0
    assert "starcoach" in capsys.readouterr().out
    kinds = [json.loads(line)["kind"] for line in log_file.read_text().splitlines()]
    assert kinds == ["run", "exit"]


def test_env_file_parsing(tmp_path):
    env = tmp_path / ".env"
    env.write_text('# c\nLIARA_API_TOKEN="abc"\n\nLLM_MODEL=m\nbad line\n', encoding="utf-8")
    assert read_env_file(env) == {"LIARA_API_TOKEN": "abc", "LLM_MODEL": "m"}


def test_settings_from_env_file(tmp_path, monkeypatch):
    monkeypatch.delenv("LIARA_API_TOKEN", raising=False)
    env = tmp_path / ".env"
    env.write_text("LIARA_API_TOKEN=tok123\nLIARA_API_URL=https://x.test/\n", encoding="utf-8")
    s = load_settings(env)
    assert s.liara_token == "tok123"
    assert s.liara_api_url == "https://x.test"


def test_secrets_never_reach_log(tmp_path):
    log = EventLog(tmp_path / "e.jsonl", secrets=["s3cret-token"])
    log.write("call", header="Bearer s3cret-token")
    text = (tmp_path / "e.jsonl").read_text()
    assert "s3cret-token" not in text and "***" in text
    assert mask("a s3cret-token b", ["s3cret-token"]) == "a *** b"
