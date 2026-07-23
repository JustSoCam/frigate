"""Tests for structured Codex CLI account and model management."""

import os
import unittest
from unittest.mock import patch

from frigate.genai.codex_cli_control import (
    CodexCLIControl,
    build_codex_env,
    list_subscription_models,
)


class TestCodexCLIControl(unittest.TestCase):
    def test_environment_only_uses_persisted_authentication(self):
        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "api-key",
                "CODEX_API_KEY": "codex-key",
                "CODEX_ACCESS_TOKEN": "access-token",
            },
        ):
            env = build_codex_env("/config/codex")

        self.assertEqual(env["CODEX_HOME"], "/config/codex")
        self.assertNotIn("OPENAI_API_KEY", env)
        self.assertNotIn("CODEX_API_KEY", env)
        self.assertNotIn("CODEX_ACCESS_TOKEN", env)

    def test_model_list_uses_visible_model_identifiers(self):
        with patch(
            "frigate.genai.codex_cli_control.run_app_server_request",
            return_value={
                "data": [
                    {"model": "gpt-visible", "hidden": False},
                    {"model": "gpt-hidden", "hidden": True},
                    {"model": "", "hidden": False},
                ]
            },
        ):
            models = list_subscription_models("/usr/bin/codex", {})

        self.assertEqual(models, ["gpt-visible"])

    def test_status_returns_plan_without_account_identity(self):
        control = CodexCLIControl()
        with patch(
            "frigate.genai.codex_cli_control.run_app_server_request",
            return_value={
                "account": {
                    "type": "chatgpt",
                    "email": "private@example.com",
                    "planType": "pro",
                },
                "requiresOpenaiAuth": True,
            },
        ):
            status = control.get_status(
                "codex",
                "/usr/bin/codex",
                {"CODEX_HOME": "/config/codex"},
            )

        self.assertEqual(
            status,
            {
                "status": "signed_in",
                "auth_type": "chatgpt",
                "plan_type": "pro",
            },
        )

    def test_api_key_login_is_rejected_as_subscription_auth(self):
        control = CodexCLIControl()
        with patch(
            "frigate.genai.codex_cli_control.run_app_server_request",
            return_value={"account": {"type": "apiKey"}},
        ):
            status = control.get_status(
                "codex",
                "/usr/bin/codex",
                {"CODEX_HOME": "/config/codex"},
            )

        self.assertEqual(status["status"], "signed_out")
        self.assertEqual(status["auth_type"], "apiKey")
        self.assertIn("ChatGPT subscription", status["message"])
