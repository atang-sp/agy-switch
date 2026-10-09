import argparse
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

import agy_switch as app


class AdaptiveEnvironmentTests(unittest.TestCase):
    def test_detect_environment_wsl_detection(self):
        with patch.dict(os.environ, {"WSL_DISTRO_NAME": "Ubuntu"}), \
             patch.object(app, "detect_environment", wraps=app.detect_environment) as wrapped:
            env = app.detect_environment()
            self.assertTrue(env["is_wsl"])

    def test_detect_environment_headless_fallback(self):
        env_clean = os.environ.copy()
        env_clean.pop("DBUS_SESSION_BUS_ADDRESS", None)
        with patch.dict(os.environ, env_clean, clear=True), \
             patch("sys.platform", "linux"):
            env = app.detect_environment()
            self.assertFalse(env["has_dbus"])
            self.assertFalse(env["has_secretservice"])
            self.assertEqual(env["active_backend"], "file")

    def test_adaptive_keyring_file_operations(self):
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            cred_file = temp_path / "antigravity-oauth-token"
            creds_dir = temp_path / "credentials"
            env = {
                "platform": "linux",
                "is_wsl": True,
                "has_dbus": False,
                "has_secretservice": False,
                "active_backend": "file",
            }
            with patch.object(app, "ACTIVE_TOKEN_FILE", cred_file), \
                 patch.object(app, "STANDALONE_TOKEN_FILE", temp_path / "jetski-standalone-oauth-token"), \
                 patch.object(app, "CREDENTIALS_DIR", creds_dir):
                backend = app.AdaptiveKeyring(env=env)

                # Active token
                self.assertIsNone(backend.get_password("gemini", "antigravity"))
                backend.set_password("gemini", "antigravity", '{"token": "test"}')
                self.assertEqual(backend.get_password("gemini", "antigravity"), '{"token": "test"}')
                self.assertTrue(cred_file.is_file())
                self.assertEqual(cred_file.stat().st_mode & 0o777, 0o600)

                backend.delete_password("gemini", "antigravity")
                self.assertIsNone(backend.get_password("gemini", "antigravity"))

                # Profile token
                backend.set_password("gemini-accounts", "user@example.com", '{"profile": 1}')
                self.assertEqual(backend.get_password("gemini-accounts", "user@example.com"), '{"profile": 1}')
                backend.delete_password("gemini-accounts", "user@example.com")
                self.assertIsNone(backend.get_password("gemini-accounts", "user@example.com"))

    def test_cmd_doctor_runs_and_prints_info(self):
        output = io.StringIO()
        with patch.object(app, "detect_environment", return_value={
            "platform": "linux",
            "is_wsl": False,
            "has_dbus": True,
            "dbus_address": "unix:path=/test/bus",
            "has_secretservice": True,
            "secretservice_error": None,
            "active_backend": "secretservice",
        }), patch.object(app, "load_meta", return_value={"work": {"email": "test@gmail.com"}}), \
           patch.object(app, "get_current_keyring_token", return_value={"email": "test@gmail.com"}), \
           patch.object(app, "get_token_summary", return_value={"email": "test@gmail.com"}), \
           patch.object(app, "find_running_agy_processes", return_value=[]), \
           patch("sys.stdout", output):
            app.cmd_doctor(argparse.Namespace())

        text = output.getvalue()
        self.assertIn("=== agy-switch 环境诊断 ===", text)
        self.assertIn("操作系统", text)
        self.assertIn("Linux", text)
        self.assertIn("SecretService (系统密钥环)", text)
        self.assertIn("test@gmail.com", text)


if __name__ == "__main__":
    unittest.main()
