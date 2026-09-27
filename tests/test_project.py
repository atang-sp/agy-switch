import argparse
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import agy_switch as app


def token(email):
    import base64
    claim = base64.urlsafe_b64encode(json.dumps({"email": email}).encode()).decode().rstrip("=")
    return {"id_token": "a." + claim + ".c", "token": {"refresh_token": email}}


class ProjectTests(unittest.TestCase):
    def test_agy_binary_resolves_local_launcher_to_real_executable(self):
        with tempfile.TemporaryDirectory() as temp:
            launcher = Path(temp) / "agy"
            real = Path(temp) / "agy-real"
            launcher.write_text("#!/bin/sh\n", encoding="utf-8")
            real.write_bytes(b"binary")
            real.chmod(0o755)
            with patch.dict(app.os.environ, {"AGY_BIN": str(launcher)}):
                self.assertEqual(app.agy_binary(), str(real))

    def test_git_subdirectories_share_project_root(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repo"
            child = root / "src" / "nested"
            child.mkdir(parents=True)
            import subprocess
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            self.assertEqual(app.project_root(child), str(root))

    def test_prepare_project_home_isolates_credentials_and_keeps_refresh(self):
        with tempfile.TemporaryDirectory() as temp:
            real_home = Path(temp) / "real"
            real_home.mkdir()
            (real_home / ".gitconfig").write_text("[user]\n", encoding="utf-8")
            global_auth = real_home / ".gemini" / "antigravity-cli"
            global_auth.mkdir(parents=True)
            global_token = global_auth / "antigravity-oauth-token"
            global_token.write_text(json.dumps(token("global@example.com")), encoding="utf-8")
            with patch.object(app.Path, "home", return_value=real_home), \
                 patch.object(app, "PROJECT_HOMES_DIR", Path(temp) / "homes"):
                home_a = app.prepare_project_home("/project/a", "a@example.com", token("a@example.com"))
                home_b = app.prepare_project_home("/project/b", "b@example.com", token("b@example.com"))
                file_a = home_a / ".gemini/antigravity-cli/antigravity-oauth-token"
                file_b = home_b / ".gemini/antigravity-cli/antigravity-oauth-token"
                self.assertNotEqual(home_a, home_b)
                self.assertEqual(app.get_token_summary(json.loads(file_a.read_text()))["email"], "a@example.com")
                self.assertEqual(app.get_token_summary(json.loads(file_b.read_text()))["email"], "b@example.com")
                self.assertEqual(app.get_token_summary(json.loads(global_token.read_text()))["email"], "global@example.com")
                self.assertTrue((home_a / ".gitconfig").is_symlink())
                self.assertEqual(file_a.stat().st_mode & 0o777, 0o600)
                refreshed = token("a@example.com")
                refreshed["token"]["access_token"] = "new"
                file_a.write_text(json.dumps(refreshed), encoding="utf-8")
                app.prepare_project_home("/project/a", "a@example.com", token("a@example.com"))
                self.assertEqual(json.loads(file_a.read_text())["token"]["access_token"], "new")

    def test_agy_launch_uses_bound_account_without_global_switch(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(app, "project_root", return_value="/project/a"), \
                 patch.object(app, "project_account", return_value="a@example.com"), \
                 patch.object(app, "get_profile_payload", return_value=token("a@example.com")), \
                 patch.object(app, "prepare_project_home", return_value=Path(temp)), \
                 patch.object(app.shutil, "which", return_value="/usr/bin/agy"), \
                 patch.object(app, "set_current_keyring_token") as switch, \
                 patch.object(app.os, "execvpe") as execute:
                app.cmd_run_agy(["--model", "gemini"])
            switch.assert_not_called()
            execute.assert_called_once()
            binary, argv, env = execute.call_args.args
            self.assertEqual(binary, "/usr/bin/agy")
            self.assertEqual(argv, ["/usr/bin/agy", "--model", "gemini"])
            self.assertEqual(env["HOME"], temp)

    def test_agy_launch_without_binding_keeps_global_home(self):
        with patch.object(app, "project_account", return_value=None), \
             patch.object(app.shutil, "which", return_value="/usr/bin/agy"), \
             patch.object(app, "prepare_project_home") as prepare, \
             patch.object(app.os, "execvpe") as execute:
            app.cmd_run_agy(["--help"])
        prepare.assert_not_called()
        self.assertEqual(execute.call_args.args[1], ["/usr/bin/agy", "--help"])
        self.assertEqual(execute.call_args.args[2]["HOME"], app.os.environ["HOME"])

    def test_current_reports_project_account(self):
        output = io.StringIO()
        with patch.object(app, "project_account", return_value="a@example.com"), \
             patch.object(app, "project_root", return_value="/project/a"), \
             patch.object(app, "get_profile_payload", return_value=token("a@example.com")), \
             patch.object(app, "get_current_keyring_token") as global_token, \
             patch.object(app, "load_meta", return_value={"work": {"email": "a@example.com"}}), \
             patch("sys.stdout", output):
            app.cmd_current(argparse.Namespace(no_quota=True))
        global_token.assert_not_called()
        self.assertIn("当前项目账号", output.getvalue())
        self.assertIn("work", output.getvalue())

    def test_switch_binds_current_project_without_changing_global_login(self):
        with tempfile.TemporaryDirectory() as temp:
            projects_file = Path(temp) / "projects.json"
            with patch.object(app, "PROJECTS_FILE", projects_file), \
                 patch.object(app, "project_root", return_value="/project/a"), \
                 patch.object(app, "load_meta", return_value={"work": {"email": "a@example.com"}}), \
                 patch.object(app, "get_profile_payload", return_value=token("a@example.com")), \
                 patch.object(app, "supports_project_accounts", return_value=True), \
                 patch.object(app, "set_current_keyring_token") as global_switch:
                app.cmd_switch(argparse.Namespace(target="work", global_switch=False, default=False))
                self.assertEqual(app.load_projects(), {"/project/a": "a@example.com"})
                self.assertEqual(projects_file.stat().st_mode & 0o777, 0o600)
                app.cmd_switch(argparse.Namespace(target=None, global_switch=False, default=True))
                self.assertEqual(app.load_projects(), {})
            global_switch.assert_not_called()

    def test_explicit_global_switch_keeps_old_behavior(self):
        target = token("work@example.com")
        current = token("global@example.com")
        with patch.object(app, "load_meta", return_value={"work": {"email": "work@example.com"}}), \
             patch.object(app, "get_profile_payload", return_value=target), \
             patch.object(app, "supports_project_accounts", return_value=True), \
             patch.object(app, "get_current_keyring_token", side_effect=[current, target]), \
             patch.object(app, "find_running_agy_processes", return_value=[]), \
             patch.object(app, "save_profile"), \
             patch.object(app, "save_projects") as project_binding, \
             patch.object(app, "set_current_keyring_token") as global_switch:
            app.cmd_switch(argparse.Namespace(target="work", global_switch=True, default=False))
        project_binding.assert_not_called()
        global_switch.assert_called_once_with(target)


if __name__ == "__main__":
    unittest.main()
