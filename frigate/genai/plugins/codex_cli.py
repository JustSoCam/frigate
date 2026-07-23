"""Codex CLI provider using a saved ChatGPT subscription login."""

import asyncio
import base64
import json
import logging
import os
import shutil
import signal
import subprocess
import tempfile
import threading
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from frigate.config import GenAIConfig, GenAIProviderEnum
from frigate.genai import GenAIClient, register_genai_provider
from frigate.genai.codex_cli_control import (
    build_codex_env,
    list_subscription_models,
)

logger = logging.getLogger(__name__)

_DISABLED_FEATURES = (
    "shell_tool",
    "plugins",
    "apps",
    "browser_use",
    "computer_use",
    "image_generation",
    "multi_agent",
    "goals",
    "hooks",
    "workspace_dependencies",
)
_REASONING_EFFORTS = {"none", "low", "medium", "high", "xhigh", "max"}


@dataclass
class _ProcessResult:
    """Result from a bounded Codex CLI subprocess."""

    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


def _run_subprocess(
    command: list[str],
    prompt: str | None,
    env: dict[str, str],
    cwd: str,
    timeout: int,
) -> _ProcessResult:
    """Run Codex in its own process group and terminate it on timeout."""
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdin=subprocess.PIPE if prompt is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )

    try:
        stdout, stderr = process.communicate(input=prompt, timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
        return _ProcessResult(
            process.returncode or -1,
            stdout,
            stderr,
            timed_out=True,
        )

    return _ProcessResult(process.returncode or 0, stdout, stderr)


def _decode_data_image(url: str) -> bytes | None:
    """Decode an inline image data URL without retaining it in the prompt."""
    if not url.startswith("data:image/") or ";base64," not in url:
        return None

    try:
        return base64.b64decode(url.split(",", 1)[1], validate=True)
    except (ValueError, TypeError):
        return None


def _normalize_chat_messages(
    messages: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[bytes]]:
    """Replace inline chat images with attachment markers."""
    normalized: list[dict[str, Any]] = []
    images: list[bytes] = []

    for message in messages:
        normalized_message = dict(message)
        content = message.get("content")

        if not isinstance(content, list):
            normalized.append(normalized_message)
            continue

        normalized_parts: list[dict[str, Any]] = []
        for part in content:
            if not isinstance(part, dict):
                continue

            if part.get("type") == "text":
                normalized_parts.append(
                    {"type": "text", "text": str(part.get("text", ""))}
                )
                continue

            if part.get("type") != "image_url":
                continue

            image_url = part.get("image_url", {})
            url = image_url.get("url") if isinstance(image_url, dict) else None
            image = _decode_data_image(url) if isinstance(url, str) else None
            if image is None:
                continue

            images.append(image)
            normalized_parts.append(
                {
                    "type": "image",
                    "attachment": f"image_{len(images)}",
                }
            )

        normalized_message["content"] = normalized_parts
        normalized.append(normalized_message)

    return normalized, images


def _chat_output_schema(tool_names: list[str]) -> dict[str, Any]:
    """Build the structured response schema for Frigate Chat."""
    tool_name_schema: dict[str, Any] = {"type": "string"}
    if tool_names:
        tool_name_schema["enum"] = tool_names

    return {
        "type": "object",
        "properties": {
            "content": {"type": ["string", "null"]},
            "tool_calls": {
                "type": ["array", "null"],
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "name": tool_name_schema,
                        "arguments_json": {"type": "string"},
                    },
                    "required": ["id", "name", "arguments_json"],
                    "additionalProperties": False,
                },
            },
            "finish_reason": {
                "type": "string",
                "enum": ["stop", "tool_calls"],
            },
        },
        "required": ["content", "tool_calls", "finish_reason"],
        "additionalProperties": False,
    }


@register_genai_provider(GenAIProviderEnum.codex_cli)
class CodexCLIClient(GenAIClient):
    """Generative AI client backed by non-interactive Codex CLI runs."""

    provider: str

    def __init__(
        self,
        genai_config: GenAIConfig,
        timeout: int = 120,
        validate_model: bool = True,
    ) -> None:
        options = genai_config.provider_options
        max_concurrent = int(options.get("max_concurrent_requests", 1))
        self._request_semaphore = threading.BoundedSemaphore(max(1, max_concurrent))
        self._authenticated = False
        super().__init__(genai_config, timeout, validate_model)

    def _build_env(self) -> dict[str, str]:
        """Build an environment that can only use saved Codex authentication."""
        codex_home = self.genai_config.provider_options.get(
            "codex_home", "/config/codex"
        )
        return build_codex_env(str(codex_home))

    def _check_subscription_login(self, executable: str) -> None:
        """Require a saved ChatGPT login rather than usage-billed API auth."""
        result = _run_subprocess(
            [executable, "login", "status"],
            None,
            self._build_env(),
            tempfile.gettempdir(),
            min(self.timeout, 15),
        )
        status = f"{result.stdout}\n{result.stderr}"
        if result.returncode != 0 or "logged in using chatgpt" not in status.lower():
            raise RuntimeError("Codex CLI is not logged in with a ChatGPT subscription")
        self._authenticated = True

    def _init_provider(self) -> str:
        """Locate Codex and validate its ChatGPT subscription login."""
        configured_path = str(
            self.genai_config.provider_options.get("codex_path", "codex")
        )
        executable = shutil.which(configured_path)
        if not executable:
            raise RuntimeError(f"Codex CLI executable not found: {configured_path}")

        if self.validate_model:
            self._check_subscription_login(executable)
        return executable

    def list_models(self) -> list[str]:
        """Return models available to the saved ChatGPT subscription."""
        if not self._authenticated:
            self._check_subscription_login(self.provider)

        discovered_models = list_subscription_models(
            self.provider,
            self._build_env(),
            min(self.timeout, 15),
        )
        configured_models = self.genai_config.provider_options.get("models", [])
        models = [
            model
            for model in configured_models
            if isinstance(model, str) and model.strip()
        ]
        models.extend(discovered_models)
        current_model = self.genai_config.model.strip()
        if current_model and current_model != "probe":
            models.append(current_model)
        models.append("default")
        return sorted(set(models))

    @property
    def supports_toggleable_thinking(self) -> bool:
        """Codex reasoning effort can be selected for each invocation."""
        return True

    def get_context_size(self) -> int:
        """Return the configured prompt context budget."""
        return int(self.genai_config.provider_options.get("context_size", 128000))

    def _reasoning_effort(self, enable_thinking: bool | None) -> str:
        if enable_thinking is True:
            return "medium"
        if enable_thinking is False:
            return "none"

        configured = str(
            self.genai_config.runtime_options.get("reasoning_effort", "none")
        ).lower()
        return configured if configured in _REASONING_EFFORTS else "none"

    def _build_command(
        self,
        workdir: str,
        output_path: str,
        image_paths: list[str],
        schema_path: str | None,
        reasoning_effort: str,
    ) -> list[str]:
        command = [
            self.provider,
            "exec",
            "--ephemeral",
            "--ignore-user-config",
            "--ignore-rules",
        ]
        for feature in _DISABLED_FEATURES:
            command.extend(["--disable", feature])

        command.extend(
            [
                "-c",
                'web_search="disabled"',
                "-c",
                'approval_policy="never"',
                "-c",
                f'model_reasoning_effort="{reasoning_effort}"',
                "--sandbox",
                "read-only",
                "--skip-git-repo-check",
                "--color",
                "never",
                "-C",
                workdir,
                "-o",
                output_path,
            ]
        )

        model = self.genai_config.model.strip()
        if model and model not in {"default", "auto"}:
            command.extend(["--model", model])
        if schema_path:
            command.extend(["--output-schema", schema_path])
        if image_paths:
            command.append("--image")
            command.extend(image_paths)
        command.append("-")
        return command

    def _run_codex(
        self,
        prompt: str,
        images: list[bytes],
        output_schema: dict[str, Any] | None = None,
        enable_thinking: bool | None = None,
    ) -> str | None:
        """Run one isolated Codex request and return only its final message."""
        if not self.ensure_provider():
            return None

        acquired = self._request_semaphore.acquire(timeout=self.timeout)
        if not acquired:
            logger.warning("Timed out waiting for the Codex CLI request queue")
            return None

        temp_root = self.genai_config.provider_options.get("temp_dir")
        try:
            with tempfile.TemporaryDirectory(
                prefix="frigate-codex-",
                dir=str(temp_root) if temp_root else None,
            ) as temp_dir:
                image_paths: list[str] = []
                for index, image in enumerate(images, start=1):
                    image_path = Path(temp_dir, f"image-{index}.jpg")
                    image_path.write_bytes(image)
                    image_path.chmod(0o600)
                    image_paths.append(str(image_path))

                schema_path: str | None = None
                if output_schema is not None:
                    schema_file = Path(temp_dir, "response-schema.json")
                    schema_file.write_text(
                        json.dumps(output_schema),
                        encoding="utf-8",
                    )
                    schema_file.chmod(0o600)
                    schema_path = str(schema_file)

                output_path = Path(temp_dir, "response.txt")
                command = self._build_command(
                    temp_dir,
                    str(output_path),
                    image_paths,
                    schema_path,
                    self._reasoning_effort(enable_thinking),
                )
                result = _run_subprocess(
                    command,
                    prompt,
                    self._build_env(),
                    temp_dir,
                    self.timeout,
                )

                if result.timed_out:
                    logger.warning("Codex CLI request timed out")
                    return None
                if result.returncode != 0:
                    status = result.stderr.lower()
                    if "not logged in" in status or "authentication" in status:
                        self._authenticated = False
                        logger.warning(
                            "Codex CLI subscription authentication is unavailable"
                        )
                    elif "rate limit" in status or "usage limit" in status:
                        logger.warning("Codex CLI subscription limit was reached")
                    else:
                        logger.warning(
                            "Codex CLI request failed with exit code %s",
                            result.returncode,
                        )
                    return None

                if output_path.exists():
                    response = output_path.read_text(encoding="utf-8")
                else:
                    response = result.stdout
                return response.strip() or None
        finally:
            self._request_semaphore.release()

    def _send(
        self,
        prompt: str,
        images: list[bytes],
        response_format: dict | None = None,
        enable_thinking: bool = False,
    ) -> str | None:
        """Submit a multimodal description request through Codex CLI."""
        output_schema = None
        if response_format and response_format.get("type") == "json_schema":
            output_schema = response_format.get("json_schema", {}).get("schema")

        framed_prompt = (
            "Role: Analyze security-camera evidence for Frigate.\n\n"
            "Goal: Follow the supplied request using only its text and attached "
            "images.\n\n"
            "Constraints:\n"
            "- Do not use tools, files, web search, or outside knowledge.\n"
            "- Do not invent people, objects, actions, or identifying details.\n"
            "- Preserve the requested language and output format.\n\n"
            f"Request:\n{prompt}"
        )
        return self._run_codex(
            framed_prompt,
            images,
            output_schema,
            enable_thinking,
        )

    def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = "auto",
        enable_thinking: bool | None = None,
    ) -> dict[str, Any]:
        """Answer Frigate Chat or request a Frigate function call."""
        normalized_messages, images = _normalize_chat_messages(messages)
        available_tools = tools or []
        tool_names = [
            str(tool.get("function", {}).get("name"))
            for tool in available_tools
            if tool.get("function", {}).get("name")
        ]

        prompt = (
            "Role: Frigate security-camera assistant.\n\n"
            "Goal: Continue the supplied conversation. Answer directly when the "
            "available evidence is sufficient. Otherwise select the smallest "
            "useful Frigate function call.\n\n"
            "Constraints:\n"
            "- Use only the conversation, attached images, and listed Frigate "
            "functions.\n"
            "- Do not use Codex tools, files, web search, or outside knowledge.\n"
            "- Do not claim a camera observation unless an attached image or "
            "tool result supports it.\n"
            f"- Tool choice is {tool_choice or 'auto'}.\n"
            "- Put function arguments in arguments_json as a valid JSON object "
            "encoded as a string.\n"
            "- Return content as null when requesting functions. Return "
            "tool_calls as null when answering.\n\n"
            f"Conversation:\n{json.dumps(normalized_messages, ensure_ascii=False)}"
            f"\n\nAvailable Frigate functions:\n"
            f"{json.dumps(available_tools, ensure_ascii=False)}"
        )
        response = self._run_codex(
            prompt,
            images,
            _chat_output_schema(tool_names),
            enable_thinking,
        )
        if not response:
            return {
                "content": None,
                "reasoning": None,
                "tool_calls": None,
                "finish_reason": "error",
            }

        try:
            parsed = json.loads(response)
        except json.JSONDecodeError:
            logger.warning("Codex CLI returned invalid structured chat output")
            return {
                "content": None,
                "reasoning": None,
                "tool_calls": None,
                "finish_reason": "error",
            }

        parsed_tool_calls: list[dict[str, Any]] = []
        for tool_call in parsed.get("tool_calls") or []:
            name = tool_call.get("name")
            if name not in tool_names:
                continue
            try:
                arguments = json.loads(tool_call.get("arguments_json", "{}"))
            except (json.JSONDecodeError, TypeError):
                arguments = {}
            if not isinstance(arguments, dict):
                arguments = {}
            parsed_tool_calls.append(
                {
                    "id": tool_call.get("id") or f"codex_{uuid.uuid4().hex}",
                    "name": name,
                    "arguments": arguments,
                }
            )

        content = parsed.get("content")
        return {
            "content": content.strip() if isinstance(content, str) else None,
            "reasoning": None,
            "tool_calls": parsed_tool_calls or None,
            "finish_reason": "tool_calls"
            if parsed_tool_calls
            else str(parsed.get("finish_reason", "stop")),
        }

    async def chat_with_tools_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = "auto",
        enable_thinking: bool | None = None,
    ) -> AsyncGenerator[tuple[str, Any], None]:
        """Run Codex off the event loop and emit its final response."""
        message = await asyncio.to_thread(
            self.chat_with_tools,
            messages,
            tools,
            tool_choice,
            enable_thinking,
        )
        content = message.get("content")
        if content:
            yield ("content_delta", content)
        yield ("message", message)
