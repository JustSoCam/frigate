"""Tests for the ChatGPT-authenticated Codex CLI GenAI provider."""

import asyncio
import base64
import json
import os
import unittest
from unittest.mock import patch

from frigate.config import GenAIConfig
from frigate.genai.plugins.codex_cli import (
    CodexCLIClient,
    _normalize_chat_messages,
    _ProcessResult,
)


def _client(**overrides):
    config = GenAIConfig(
        provider="codex_cli",
        model=overrides.pop("model", "default"),
        provider_options={
            "codex_path": "/bin/true",
            **overrides.pop("provider_options", {}),
        },
        runtime_options=overrides.pop("runtime_options", {}),
        **overrides,
    )
    return CodexCLIClient(config, timeout=5, validate_model=False)


class TestCodexCLIProvider(unittest.TestCase):
    def test_subscription_status_is_required(self):
        client = _client()
        with patch(
            "frigate.genai.plugins.codex_cli._run_subprocess",
            return_value=_ProcessResult(0, "Logged in using an API key", ""),
        ):
            with self.assertRaisesRegex(RuntimeError, "ChatGPT subscription"):
                client.list_models()

    def test_description_disables_tools_and_strips_api_auth(self):
        client = _client()
        captured = {}

        def fake_run(command, prompt, env, cwd, timeout):
            captured.update(command=command, prompt=prompt, env=env, cwd=cwd)
            return _ProcessResult(0, "camera description", "")

        with (
            patch.dict(
                os.environ,
                {
                    "OPENAI_API_KEY": "api-key",
                    "CODEX_API_KEY": "codex-key",
                    "CODEX_ACCESS_TOKEN": "access-token",
                },
            ),
            patch(
                "frigate.genai.plugins.codex_cli._run_subprocess",
                side_effect=fake_run,
            ),
        ):
            response = client._send("Describe this.", [b"\xff\xd8\xff\xd9"])

        self.assertEqual(response, "camera description")
        self.assertIn("--ephemeral", captured["command"])
        self.assertIn("--ignore-user-config", captured["command"])
        self.assertIn("shell_tool", captured["command"])
        self.assertIn('web_search="disabled"', captured["command"])
        self.assertIn("--image", captured["command"])
        self.assertNotIn("OPENAI_API_KEY", captured["env"])
        self.assertNotIn("CODEX_API_KEY", captured["env"])
        self.assertNotIn("CODEX_ACCESS_TOKEN", captured["env"])
        self.assertIn("Do not use tools", captured["prompt"])

    def test_chat_tool_call_arguments_are_dict(self):
        client = _client()
        response = json.dumps(
            {
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "name": "search_objects",
                        "arguments_json": '{"label":"person"}',
                    }
                ],
                "finish_reason": "tool_calls",
            }
        )
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "search_objects",
                    "description": "Search tracked objects",
                    "parameters": {"type": "object"},
                },
            }
        ]
        with patch(
            "frigate.genai.plugins.codex_cli._run_subprocess",
            return_value=_ProcessResult(0, response, ""),
        ):
            final = client.chat_with_tools(
                [{"role": "user", "content": "Who was here?"}],
                tools,
            )

        self.assertEqual(final["finish_reason"], "tool_calls")
        self.assertEqual(
            final["tool_calls"][0]["arguments"],
            {"label": "person"},
        )

    def test_multimodal_chat_removes_base64_from_prompt(self):
        encoded = base64.b64encode(b"\xff\xd8\xff\xd9").decode()
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What is visible?"},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{encoded}"},
                    },
                ],
            }
        ]

        normalized, images = _normalize_chat_messages(messages)

        self.assertEqual(images, [b"\xff\xd8\xff\xd9"])
        self.assertNotIn(encoded, json.dumps(normalized))
        self.assertEqual(
            normalized[0]["content"][1],
            {"type": "image", "attachment": "image_1"},
        )

    def test_stream_emits_content_and_final_message(self):
        client = _client()
        response = json.dumps(
            {
                "content": "Hello",
                "tool_calls": None,
                "finish_reason": "stop",
            }
        )

        async def collect():
            events = []
            with patch(
                "frigate.genai.plugins.codex_cli._run_subprocess",
                return_value=_ProcessResult(0, response, ""),
            ):
                async for event in client.chat_with_tools_stream(
                    [{"role": "user", "content": "Hello"}],
                    [],
                ):
                    events.append(event)
            return events

        events = asyncio.run(collect())
        self.assertEqual(events[0], ("content_delta", "Hello"))
        self.assertEqual(events[-1][0], "message")

    def test_timeout_returns_none(self):
        client = _client()
        with patch(
            "frigate.genai.plugins.codex_cli._run_subprocess",
            return_value=_ProcessResult(-1, "", "", timed_out=True),
        ):
            self.assertIsNone(client._send("Describe this.", []))
