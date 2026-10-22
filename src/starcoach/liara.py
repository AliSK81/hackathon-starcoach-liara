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

    def request(self, method: str, path: str, params: dict | None = None,
                body: dict | None = None, raw: bytes | None = None,
                content_type: str | None = None, timeout: float | None = None):
        if not self.token:
            raise LiaraError("No Liara token. Set LIARA_API_TOKEN in .env.")
        url = self.base_url + path
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

    def list_apps(self) -> list[dict]:
        return self.request("GET", "/v1/projects").get("projects", [])

    def get_app(self, name: str) -> dict:
        return self.request("GET", f"/v1/projects/{_q(name)}").get("project", {})

    def applets(self, name: str):
        return self.request("GET", f"/v1/projects/{_q(name)}/applets")


def _q(name: str) -> str:
    return urllib.parse.quote(name, safe="")


def _parse(content: bytes):
    if not content:
        return {}
    try:
        return json.loads(content)
    except ValueError:
        return {"error": content[:200].decode("utf-8", "replace")}
