"""Settings from environment and `.env`. Secrets never leave this module unmasked."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

SECRET_NAMES = ("LIARA_API_TOKEN", "LLM_API_KEY")
DEFAULT_LIARA_API_URL = "https://api.liara.ir"  # F4


def read_env_file(path: Path) -> dict[str, str]:
    """Parse KEY=VALUE lines. Ignores blanks, comments, and surrounding quotes."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


@dataclass(frozen=True)
class Settings:
    liara_token: str = ""
    liara_api_url: str = DEFAULT_LIARA_API_URL
    liara_team_id: str = ""
    llm_base_url: str = ""
    llm_model: str = ""
    llm_api_key: str = ""

    def secrets(self) -> list[str]:
        return [s for s in (self.liara_token, self.llm_api_key) if s]


def load_settings(env_file: Path | None = None) -> Settings:
    """Real environment wins over `.env`."""
    values = read_env_file(env_file or Path.cwd() / ".env")
    values.update({k: v for k, v in os.environ.items() if v})
    return Settings(
        liara_token=values.get("LIARA_API_TOKEN", ""),
        liara_api_url=values.get("LIARA_API_URL", DEFAULT_LIARA_API_URL).rstrip("/"),
        liara_team_id=values.get("LIARA_TEAM_ID", ""),
        llm_base_url=values.get("LLM_BASE_URL", "").rstrip("/"),
        llm_model=values.get("LLM_MODEL", ""),
        llm_api_key=values.get("LLM_API_KEY", ""),
    )


def mask(text: str, secrets: list[str]) -> str:
    """Replace every secret value in text with a fixed marker."""
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return text
