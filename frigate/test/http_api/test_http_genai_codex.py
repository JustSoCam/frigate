from unittest.mock import patch

from frigate.models import Event, Recordings, ReviewSegment
from frigate.test.http_api.base_http_test import AuthTestClient, BaseTestHttp


class TestHttpGenAICodex(BaseTestHttp):
    def setUp(self):
        super().setUp([Event, Recordings, ReviewSegment])
        self.minimal_config["genai"] = {
            "codex": {
                "provider": "codex_cli",
                "model": "default",
                "roles": ["descriptions", "chat"],
                "provider_options": {
                    "codex_path": "/bin/true",
                    "codex_home": "/tmp/frigate-codex-test",
                },
            }
        }

    def test_status_returns_sanitized_account_metadata(self):
        app = super().create_app()
        with (
            patch.object(
                app.codex_cli_control,
                "get_status",
                return_value={
                    "status": "signed_in",
                    "auth_type": "chatgpt",
                    "plan_type": "pro",
                },
            ),
            AuthTestClient(app) as client,
        ):
            response = client.get("/genai/codex/auth?name=codex")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "status": "signed_in",
                "auth_type": "chatgpt",
                "plan_type": "pro",
            },
        )

    def test_device_login_returns_only_user_flow_metadata(self):
        app = super().create_app()
        with (
            patch.object(
                app.codex_cli_control,
                "start_login",
                return_value={
                    "status": "pending",
                    "verification_url": "https://example.com/device",
                    "user_code": "ABCD-EFGH",
                },
            ),
            AuthTestClient(app) as client,
        ):
            response = client.post("/genai/codex/auth/login?name=codex")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "pending")
        self.assertNotIn("access_token", response.json())
        self.assertNotIn("refresh_token", response.json())

    def test_auth_routes_require_admin(self):
        app = super().create_app()
        with AuthTestClient(app) as client:
            response = client.get(
                "/genai/codex/auth?name=codex",
                headers={"remote-user": "viewer", "remote-role": "viewer"},
            )

        self.assertEqual(response.status_code, 403)
