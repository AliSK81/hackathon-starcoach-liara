"""Liara REST API client. Stdlib only. The transport is swappable for offline tests."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable

# transport(method, url, headers, body, timeout) -> (status, body_bytes)
Transport = Callable[[str, str, dict, bytes | None, float], tuple[int, bytes]]

RETRY_STATUS = {429, 500, 502, 503, 504}


def urllib_transport(method, url, headers, body, timeout):
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as err:
        return err.code, err.read()


class LiaraError(Exception):
    """An API failure with a message a non-technical user can act on."""

    def __init__(self, message: str, status: int = 0, code: str = "", detail: str = ""):
        super().__init__(message)
        self.status = status
        self.code = code
        self.detail = detail


def _friendly(status: int, payload: dict, path: str) -> LiaraError:
    # Error bodies look like {statusCode, message, data: {code}} (research 01, section errors).
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    detail = str(payload.get("message") or payload.get("error") or "")
    code = str(data.get("code") or payload.get("code") or (detail if "_" in detail and " " not in detail else ""))
    if status == 401:
        msg = "Liara rejected the API token. Make a new one in the Liara console and set LIARA_API_TOKEN in .env."
    elif status == 402:
        msg = "Not enough account balance on Liara. Top up the account in the console."
    elif code == "frozen_project":
        msg = "The app is frozen because the account balance is low. Top up, then unfreeze it in the console."
    elif status == 403 and code.startswith("free_plan"):
        msg = "The free plan does not allow this. Choose a paid plan."
    elif status == 403:
        msg = "This token has no access to that resource."
    elif status == 404:
        msg = "Not found on Liara. Check the app name (or the team)."
    elif status == 409:
        msg = "Conflict: the name is taken, or another operation on this app is still running."
    elif status == 413:
        msg = "The upload is too large for this plan."
    elif status == 428:
        msg = f"A plan limit was reached ({code or 'limit'})."
    elif status == 429:
        msg = "Liara is rate-limiting us. Try again shortly."
    elif status >= 500:
        msg = "Liara had a server error. Try again shortly."
    else:
        msg = f"Liara refused the request ({status})."
    if detail and status not in (401,):
        msg += f" Liara says: {detail}"
    return LiaraError(msg, status=status, code=code, detail=detail)


@dataclass
class LiaraClient:
    token: str
    base_url: str = "https://api.liara.ir"
    transport: Transport = urllib_transport
    log: object | None = None
    timeout: float = 30.0
    retry_wait: float = 1.0
    team_id: str = ""  # sent as ?teamID= on every call, like the official CLI (F15)

    def request(self, method: str, path: str, params: dict | None = None,
                body: dict | None = None, raw: bytes | None = None,
                content_type: str | None = None, timeout: float | None = None):
        if not self.token:
            raise LiaraError("No Liara token. Set LIARA_API_TOKEN in .env.")
        if self.token.startswith("fake-"):
            raise LiaraError("LIARA_API_TOKEN in .env is still the example placeholder. "
                             "Put your real token from the Liara console (API section) there.")
        url = self.base_url + path
        params = {**(params or {}), **({"teamID": self.team_id} if self.team_id else {})}
        if params:
            url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/json",
                   "User-Agent": "starcoach"}
        data = raw
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        elif content_type:
            headers["Content-Type"] = content_type
        attempts = 3 if method == "GET" else 1
        for attempt in range(attempts):
            start = time.monotonic()
            try:
                status, content = self.transport(method, url, headers, data, timeout or self.timeout)
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                self._log(method, path, 0, start, error=str(exc))
                if attempt + 1 < attempts:
                    time.sleep(self.retry_wait * (attempt + 1))
                    continue
                raise LiaraError("Cannot reach the Liara API. Check the internet connection.",
                                 detail=str(exc)) from exc
            self._log(method, path, status, start)
            if status in RETRY_STATUS and attempt + 1 < attempts:
                time.sleep(self.retry_wait * (attempt + 1))
                continue
            payload = _parse(content)
            if status >= 400:
                raise _friendly(status, payload if isinstance(payload, dict) else {}, path)
            return payload
        raise AssertionError("unreachable")

    def _log(self, method, path, status, start, **extra):
        if self.log is not None:
            ms = int((time.monotonic() - start) * 1000)
            self.log.write("api", method=method, path=path, status=status, ms=ms, **extra)

    # --- read-only calls ---
    def me(self) -> dict:
        return self.request("GET", "/v1/me")

    def billing(self) -> dict:
        """Balance in Toman from GET /v1/billing (F12). In a team the team's wallet pays (F15).
        Only money fields are kept."""
        data = self.request("GET", "/v1/billing")
        wallet = (data.get("team") if self.team_id else None) or data.get("user") or {}
        return {"balance": wallet.get("balance"), "min_credit": wallet.get("minCreditAmount"),
                "account": "team" if self.team_id and data.get("team") else "personal"}

    def teams(self) -> list[dict]:
        """Teams of this token's user: GET /v2/teams (cli@14ec35f:src/commands/team/list.ts:24-25)."""
        saved, self.team_id = self.team_id, ""
        try:
            return [{"id": t.get("_id"), "name": t.get("name")} for t in self.request("GET", "/v2/teams").get("teams", [])]
        finally:
            self.team_id = saved

    def plans(self) -> dict:
        """Plan catalog from /v1/me. Only `plans` is kept: the rest holds personal data and keys."""
        return self.me().get("plans", {}) or {}

    def list_apps(self) -> list[dict]:
        return self.request("GET", "/v1/projects").get("projects", [])

    def get_app(self, name: str) -> dict:
        return self.request("GET", f"/v1/projects/{_q(name)}").get("project", {})

    def applets(self, name: str):
        return self.request("GET", f"/v1/projects/{_q(name)}/applets")

    def networks(self) -> list[dict]:
        return self.request("GET", "/v1/networks").get("networks", [])

    # --- changes (the agent asks the user first) ---
    def restart(self, name: str) -> dict:
        return self.request("POST", f"/v1/projects/{_q(name)}/actions/restart")

    def scale(self, name: str, on: bool) -> dict:
        return self.request("POST", f"/v1/projects/{_q(name)}/actions/scale", body={"scale": 1 if on else 0})

    def resize(self, name: str, plan_id: str) -> dict:
        return self.request("POST", f"/v1/projects/{_q(name)}/resize", body={"planID": plan_id})

    def set_env(self, name: str, key: str, value: str) -> dict:
        """update-envs replaces the whole set and restarts the app (research 01 §4), so we merge.
        If any env is encrypted we stop: its value may be masked on read and would be overwritten."""
        envs = self.get_app(name).get("envs") or []
        if any(e.get("encrypted") for e in envs):
            raise LiaraError("This app has encrypted env vars. To avoid overwriting them, "
                             f"set {key} in the Liara console (Settings → Environment variables).")
        merged = {e["key"]: e.get("value", "") for e in envs if e.get("key")}
        merged[key] = value
        variables = [{"key": k, "value": v} for k, v in merged.items()]
        self.request("POST", "/v1/projects/update-envs", body={"project": name, "variables": variables})
        return {"key": key, "env_count": len(variables)}

    def create_app(self, name: str, platform: str, plan_id: str, bundle_plan_id: str,
                   network: str | None = None) -> dict:
        """POST /v1/projects. Body as the CLI sends it (cli@14ec35f:src/commands/app/create.ts:80-88).
        A network is required; we use the named one or the first one."""
        nets = self.networks()
        chosen = next((n for n in nets if n.get("name") == network), None) if network else (nets[0] if nets else None)
        if chosen is None:
            raise LiaraError("No private network found. Create one in the Liara console (Networks), then try again.")
        body = {"name": name, "planID": plan_id, "platform": platform,
                "bundlePlanID": bundle_plan_id, "network": chosen.get("_id")}
        self.request("POST", "/v1/projects", body=body)
        return {"name": name, "platform": platform, "plan": plan_id, "bundle": bundle_plan_id,
                "network": chosen.get("name")}


def _q(name: str) -> str:
    return urllib.parse.quote(name, safe="")


def _parse(content: bytes):
    if not content:
        return {}
    try:
        return json.loads(content)
    except ValueError:
        return {"error": content[:200].decode("utf-8", "replace")}
