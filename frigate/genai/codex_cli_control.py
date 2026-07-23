"""Structured Codex CLI account and model management."""

from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable
from typing import Any

_AUTH_ENV_VARS = ("OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN")
_CLIENT_INFO = {
    "name": "frigate",
    "title": "Frigate",
    "version": "0.1.0",
}


def build_codex_env(codex_home: str) -> dict[str, str]:
    """Build a Codex environment that only uses persisted authentication."""
    env = os.environ.copy()
    for variable in _AUTH_ENV_VARS:
        env.pop(variable, None)
    env["CODEX_HOME"] = os.path.expanduser(codex_home)
    return env


def resolve_codex_executable(configured_path: str) -> str:
    """Resolve the configured Codex CLI path."""
    executable = shutil.which(configured_path)
    if not executable:
        raise RuntimeError(f"Codex CLI executable not found: {configured_path}")
    return executable


def _stop_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)


def run_app_server_request(
    executable: str,
    env: dict[str, str],
    method: str,
    params: dict[str, Any] | None,
    timeout: float = 15,
) -> dict[str, Any]:
    """Run one Codex app-server request and return its structured result."""
    process = subprocess.Popen(
        [executable, "app-server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,
        env=env,
        cwd=tempfile.gettempdir(),
    )
    if process.stdin is None or process.stdout is None:
        _stop_process(process)
        raise RuntimeError("Codex app server streams are unavailable")

    messages: queue.Queue[dict[str, Any] | None] = queue.Queue()

    def read_messages() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(message, dict):
                messages.put(message)
        messages.put(None)

    reader = threading.Thread(target=read_messages, daemon=True)
    reader.start()

    try:
        initialize = {
            "method": "initialize",
            "id": 0,
            "params": {"clientInfo": _CLIENT_INFO},
        }
        request: dict[str, Any] = {"method": method, "id": 1}
        if params is not None:
            request["params"] = params

        for message in (
            initialize,
            {"method": "initialized", "params": {}},
            request,
        ):
            process.stdin.write(f"{json.dumps(message)}\n")
        process.stdin.flush()

        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"Codex app server request timed out: {method}")
            try:
                message = messages.get(timeout=remaining)
            except queue.Empty as queue_error:
                raise TimeoutError(
                    f"Codex app server request timed out: {method}"
                ) from queue_error

            if message is None:
                raise RuntimeError("Codex app server exited before responding")
            if message.get("id") != 1:
                continue
            if "error" in message:
                error_payload = message["error"]
                detail = (
                    error_payload.get("message")
                    if isinstance(error_payload, dict)
                    else None
                )
                raise RuntimeError(detail or "Codex app server request failed")
            result = message.get("result")
            if not isinstance(result, dict):
                raise RuntimeError("Codex app server returned an invalid response")
            return result
    finally:
        _stop_process(process)


def list_subscription_models(
    executable: str,
    env: dict[str, str],
    timeout: float = 15,
) -> list[str]:
    """Return visible model identifiers from the active ChatGPT account."""
    result = run_app_server_request(
        executable,
        env,
        "model/list",
        {"includeHidden": False},
        timeout,
    )
    data = result.get("data")
    if not isinstance(data, list):
        raise RuntimeError("Codex returned an invalid model list")

    models: list[str] = []
    for item in data:
        if not isinstance(item, dict) or item.get("hidden") is True:
            continue
        model = item.get("model")
        if isinstance(model, str) and model.strip():
            models.append(model.strip())
    return models


class _DeviceLoginSession:
    def __init__(
        self,
        executable: str,
        env: dict[str, str],
        on_finished: Callable[[], None],
    ) -> None:
        self._lock = threading.Lock()
        self._ready = threading.Event()
        self._on_finished = on_finished
        self._status = "starting"
        self._error: str | None = None
        self._login_id: str | None = None
        self._verification_url: str | None = None
        self._user_code: str | None = None

        self._process = subprocess.Popen(
            [executable, "app-server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            env=env,
            cwd=tempfile.gettempdir(),
        )
        if self._process.stdin is None or self._process.stdout is None:
            _stop_process(self._process)
            raise RuntimeError("Codex app server streams are unavailable")

        self._reader = threading.Thread(target=self._read_messages, daemon=True)
        self._reader.start()
        try:
            self._send(
                {
                    "method": "initialize",
                    "id": 0,
                    "params": {"clientInfo": _CLIENT_INFO},
                }
            )
            self._send({"method": "initialized", "params": {}})
            self._send(
                {
                    "method": "account/login/start",
                    "id": 1,
                    "params": {"type": "chatgptDeviceCode"},
                }
            )
        except (BrokenPipeError, RuntimeError):
            _stop_process(self._process)
            raise

    def _send(self, message: dict[str, Any]) -> None:
        if self._process.stdin is None or self._process.poll() is not None:
            raise RuntimeError("Codex app server is not running")
        self._process.stdin.write(f"{json.dumps(message)}\n")
        self._process.stdin.flush()

    def _set_error(self, message: str) -> None:
        with self._lock:
            self._status = "error"
            self._error = message
        self._ready.set()

    def _read_messages(self) -> None:
        assert self._process.stdout is not None
        try:
            for line in self._process.stdout:
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(message, dict):
                    continue

                if message.get("id") == 1:
                    if "error" in message:
                        error_payload = message["error"]
                        detail = (
                            error_payload.get("message")
                            if isinstance(error_payload, dict)
                            else None
                        )
                        self._set_error(detail or "Unable to start ChatGPT sign in")
                        return
                    result = message.get("result")
                    if (
                        not isinstance(result, dict)
                        or result.get("type") != "chatgptDeviceCode"
                    ):
                        self._set_error("Codex returned an invalid sign-in response")
                        return
                    with self._lock:
                        self._login_id = result.get("loginId")
                        self._verification_url = result.get("verificationUrl")
                        self._user_code = result.get("userCode")
                        self._status = "pending"
                    self._ready.set()
                    continue

                if message.get("method") == "account/login/completed":
                    params = message.get("params", {})
                    success = isinstance(params, dict) and params.get("success") is True
                    with self._lock:
                        self._status = "signed_in" if success else "error"
                        self._error = (
                            None
                            if success
                            else str(
                                params.get("error")
                                or "ChatGPT sign in was not completed"
                            )
                        )
                    self._ready.set()
                    return
        finally:
            with self._lock:
                if self._status in {"starting", "pending"}:
                    self._status = "error"
                    self._error = "Codex sign-in process ended unexpectedly"
            self._ready.set()
            self._on_finished()

    def wait_until_ready(self, timeout: float) -> dict[str, Any]:
        if not self._ready.wait(timeout):
            self.cancel()
            raise TimeoutError("Codex sign in did not start in time")
        snapshot = self.snapshot()
        if snapshot["status"] == "error":
            raise RuntimeError(snapshot.get("message") or "Unable to start sign in")
        return snapshot

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            result: dict[str, Any] = {"status": self._status}
            if self._status == "pending":
                result.update(
                    {
                        "verification_url": self._verification_url,
                        "user_code": self._user_code,
                    }
                )
            if self._error:
                result["message"] = self._error
            return result

    def cancel(self) -> None:
        with self._lock:
            login_id = self._login_id
            self._status = "signed_out"
            self._error = None
        if login_id and self._process.poll() is None:
            try:
                self._send(
                    {
                        "method": "account/login/cancel",
                        "id": 2,
                        "params": {"loginId": login_id},
                    }
                )
            except (BrokenPipeError, RuntimeError):
                pass
        _stop_process(self._process)

    def close(self) -> None:
        _stop_process(self._process)


class CodexCLIControl:
    """Coordinate Codex account operations without exposing credentials."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, _DeviceLoginSession] = {}

    def _session_finished(self, name: str) -> None:
        with self._lock:
            session = self._sessions.get(name)
            if session and session.snapshot()["status"] == "signed_in":
                session.close()

    def start_login(
        self,
        name: str,
        executable: str,
        env: dict[str, str],
    ) -> dict[str, Any]:
        self.cancel_login(name)
        session = _DeviceLoginSession(
            executable,
            env,
            lambda: self._session_finished(name),
        )
        with self._lock:
            self._sessions[name] = session
        try:
            return session.wait_until_ready(15)
        except (RuntimeError, TimeoutError):
            self.cancel_login(name)
            raise

    def get_status(
        self,
        name: str,
        executable: str,
        env: dict[str, str],
    ) -> dict[str, Any]:
        with self._lock:
            session = self._sessions.get(name)
        if session:
            snapshot = session.snapshot()
            if snapshot["status"] in {"starting", "pending", "error"}:
                return snapshot

        result = run_app_server_request(
            executable,
            env,
            "account/read",
            {"refreshToken": False},
        )
        account = result.get("account")
        if not isinstance(account, dict):
            return {"status": "signed_out"}
        if account.get("type") != "chatgpt":
            return {
                "status": "signed_out",
                "auth_type": str(account.get("type") or "unknown"),
                "message": "Codex must be signed in with a ChatGPT subscription",
            }
        response: dict[str, Any] = {
            "status": "signed_in",
            "auth_type": "chatgpt",
        }
        plan_type = account.get("planType")
        if isinstance(plan_type, str):
            response["plan_type"] = plan_type
        return response

    def cancel_login(self, name: str) -> None:
        with self._lock:
            session = self._sessions.pop(name, None)
        if session:
            session.cancel()

    def logout(
        self,
        name: str,
        executable: str,
        env: dict[str, str],
    ) -> dict[str, str]:
        self.cancel_login(name)
        run_app_server_request(executable, env, "account/logout", None)
        return {"status": "signed_out"}

    def close(self) -> None:
        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions = {}
        for session in sessions:
            session.close()
