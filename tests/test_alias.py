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
             patch("builtins.input", return_value=""), \
             patch.object(app, "delete_current_keyring_token") as mock_del, \
             patch("subprocess.run", side_effect=KeyboardInterrupt), \
             patch.object(app, "set_current_keyring_token") as mock_restore:
            app.cmd_add(argparse.Namespace(name="newacc"))

            mock_del.assert_called_once()
            mock_restore.assert_called_once_with(cur_token)

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
