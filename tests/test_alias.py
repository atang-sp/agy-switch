import argparse
import io
import json
import unittest
from unittest.mock import patch, MagicMock

import agy_switch as app


class AliasTests(unittest.TestCase):
    def setUp(self):
        self.meta_store = {}
        self.keyring_store = {}

    def test_save_profile_deduplicates_old_aliases(self):
        with patch.object(app, "load_meta", return_value={"renkz2011@gmail.com": {"email": "renkz2011@gmail.com"}}), \
             patch.object(app, "save_meta") as mock_save, \
             patch("keyring.set_password") as mock_keyring:
            app.save_profile("2011", "renkz2011@gmail.com", {"token": "dummy"})

            mock_save.assert_called_once()
            saved_meta = mock_save.call_args[0][0]
            self.assertIn("2011", saved_meta)
            self.assertNotIn("renkz2011@gmail.com", saved_meta)
            self.assertEqual(saved_meta["2011"]["email"], "renkz2011@gmail.com")

    def test_cmd_add_prompts_to_save_current_account(self):
        cur_token = {"id_token": "a.eyJlbWFpbCI6ICJyZW5rejIwMTFAZ21haWwuY29tIn0=.c"}
        with patch.object(app, "get_current_keyring_token", return_value=cur_token), \
             patch.object(app, "load_meta", return_value={}), \
             patch.object(app, "find_running_agy_processes", return_value=[]), \
             patch("builtins.input", return_value="y"), \
             patch.object(app, "save_profile") as mock_save, \
             patch("subprocess.run") as mock_run:
            app.cmd_add(argparse.Namespace(name="2011"))

            mock_save.assert_called_once_with("2011", "renkz2011@gmail.com", cur_token)
            mock_run.assert_not_called()

    def test_cmd_add_recovers_if_login_cancelled(self):
        cur_token = {"id_token": "a.eyJlbWFpbCI6ICJjdXJyZW50QGdtYWlsLmNvbSJ9.c"}
        with patch.object(app, "get_current_keyring_token", side_effect=[cur_token, None]), \
             patch.object(app, "load_meta", return_value={"existing": {"email": "current@gmail.com"}}), \
             patch.object(app, "find_running_agy_processes", return_value=[]), \
             patch("builtins.input", return_value=""), \
             patch.object(app, "delete_current_keyring_token") as mock_del, \
             patch("subprocess.run", side_effect=KeyboardInterrupt), \
             patch.object(app, "set_current_keyring_token") as mock_restore:
            app.cmd_add(argparse.Namespace(name="newacc"))

            mock_del.assert_called_once()
            mock_restore.assert_called_once_with(cur_token)

    def test_cmd_add_refuses_while_agy_is_running(self):
        output = io.StringIO()
        with patch.object(app, "find_running_agy_processes", return_value=[123, 456]), \
             patch.object(app, "delete_current_keyring_token") as mock_del, \
             patch("subprocess.run") as mock_run, \
             patch("sys.stdout", output):
            app.cmd_add(argparse.Namespace(name="newacc"))

        mock_del.assert_not_called()
        mock_run.assert_not_called()
        self.assertIn("PID: 123, 456", output.getvalue())

    def test_cmd_switch_refuses_while_agy_is_running(self):
        current = {"id_token": "a.eyJlbWFpbCI6ICJjdXJyZW50QGdtYWlsLmNvbSJ9.c"}
        target = {"id_token": "a.eyJlbWFpbCI6ICJ0YXJnZXRAZ21haWwuY29tIn0=.c"}
        output = io.StringIO()
        with patch.object(app, "load_meta", return_value={"target": {"email": "target@gmail.com"}}), \
             patch.object(app, "get_profile_payload", return_value=target), \
             patch.object(app, "get_current_keyring_token", return_value=current), \
             patch.object(app, "find_running_agy_processes", return_value=[123]), \
             patch.object(app, "set_current_keyring_token") as mock_set, \
             patch("sys.stdout", output):
            app.cmd_switch(argparse.Namespace(target="target"))

        mock_set.assert_not_called()
        self.assertIn("无法切换账号", output.getvalue())

    def test_cmd_switch_refuses_running_agy_even_if_file_has_target(self):
        target = {"id_token": "a.eyJlbWFpbCI6ICJ0YXJnZXRAZ21haWwuY29tIn0=.c"}
        output = io.StringIO()
        with patch.object(app, "load_meta", return_value={"target": {"email": "target@gmail.com"}}), \
             patch.object(app, "get_profile_payload", return_value=target), \
             patch.object(app, "get_current_keyring_token", return_value=target), \
             patch.object(app, "find_running_agy_processes", return_value=[123]), \
             patch.object(app, "set_current_keyring_token") as mock_set, \
             patch("sys.stdout", output):
            app.cmd_switch(argparse.Namespace(target="target"))

        mock_set.assert_not_called()
        self.assertIn("无法切换账号", output.getvalue())
        self.assertNotIn("当前已经在使用", output.getvalue())

    def test_cmd_switch_verifies_successful_write(self):
        current = {"id_token": "a.eyJlbWFpbCI6ICJjdXJyZW50QGdtYWlsLmNvbSJ9.c"}
        target = {"id_token": "a.eyJlbWFpbCI6ICJ0YXJnZXRAZ21haWwuY29tIn0=.c"}
        output = io.StringIO()
        meta = {
            "current": {"email": "current@gmail.com"},
            "target": {"email": "target@gmail.com"},
        }
        with patch.object(app, "load_meta", return_value=meta), \
             patch.object(app, "get_profile_payload", return_value=target), \
             patch.object(app, "get_current_keyring_token", side_effect=[current, target]), \
             patch.object(app, "find_running_agy_processes", return_value=[]), \
             patch.object(app, "save_profile") as mock_save, \
             patch.object(app, "set_current_keyring_token") as mock_set, \
             patch("sys.stdout", output):
            app.cmd_switch(argparse.Namespace(target="target"))

        mock_save.assert_not_called()
        mock_set.assert_called_once_with(target)
        self.assertIn("成功切换", output.getvalue())

    def test_cmd_switch_rejects_mismatched_profile_payload(self):
        wrong = {"id_token": "a.eyJlbWFpbCI6ICJ3cm9uZ0BnbWFpbC5jb20ifQ==.c"}
        output = io.StringIO()
        with patch.object(app, "load_meta", return_value={"target": {"email": "target@gmail.com"}}), \
             patch.object(app, "get_profile_payload", return_value=wrong), \
             patch.object(app, "set_current_keyring_token") as mock_set, \
             patch("sys.stdout", output):
            app.cmd_switch(argparse.Namespace(target="target"))

        mock_set.assert_not_called()
        self.assertIn("与元数据", output.getvalue())

    def test_cmd_rename_by_email(self):
        initial_meta = {"renkz2011@gmail.com": {"email": "renkz2011@gmail.com", "saved_at": "old"}}
        with patch.object(app, "load_meta", return_value=initial_meta), \
             patch.object(app, "save_meta") as mock_save:
            app.cmd_rename(argparse.Namespace(names=["renkz2011@gmail.com", "2011"]))

            mock_save.assert_called_once()
            saved = mock_save.call_args[0][0]
            self.assertIn("2011", saved)
            self.assertNotIn("renkz2011@gmail.com", saved)
            self.assertEqual(saved["2011"]["email"], "renkz2011@gmail.com")

    def test_cmd_rename_current_account(self):
        cur_token = {"id_token": "a.eyJlbWFpbCI6ICJyZW5rejIwMTFAZ21haWwuY29tIn0=.c"}
        initial_meta = {"renkz2011@gmail.com": {"email": "renkz2011@gmail.com"}}
        with patch.object(app, "get_current_keyring_token", return_value=cur_token), \
             patch.object(app, "load_meta", return_value=initial_meta), \
             patch.object(app, "save_meta") as mock_save:
            app.cmd_rename(argparse.Namespace(names=["2011"]))

            mock_save.assert_called_once()
            saved = mock_save.call_args[0][0]
            self.assertIn("2011", saved)
            self.assertNotIn("renkz2011@gmail.com", saved)


if __name__ == "__main__":
    unittest.main()
