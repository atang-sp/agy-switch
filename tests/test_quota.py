import argparse
import contextlib
import copy
import io
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import agy_switch as app


class QuotaTests(unittest.TestCase):
    def setUp(self):
        self.payload = {"token": {"access_token": "old", "refresh_token": "refresh",
                                  "expiry": "2099-01-01T00:00:00Z"}}
        self.response = {"groups": [{"displayName": "Claude and GPT models", "buckets": [
            {"window": "5h", "remainingFraction": 1},
            {"window": "weekly", "remainingFraction": 0.40326133},
        ]}]}

    def test_distinct_windows_and_missing_values(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            app.print_quota(self.response)
        self.assertIn("100.0% 剩余", output.getvalue())
        self.assertIn("40.3% 剩余", output.getvalue())
        self.assertIn("0.0% 剩余", app.format_bucket({"remainingFraction": 0}))
        self.assertEqual("未提供", app.format_bucket(None))
        self.assertIn("当前不适用", app.format_bucket({"remainingFraction": 0.85, "disabled": True}))
        for value in [None, True, "1", float("nan"), -1, 2]:
            self.assertTrue(app.format_bucket({"remainingFraction": value}).startswith("未提供"))

    def test_expired_token_refresh_does_not_change_credentials(self):
        self.payload["token"]["expiry"] = "2000-01-01T00:00:00Z"
        original = copy.deepcopy(self.payload)
        with patch.object(app, "post_json", side_effect=[{"access_token": "new"}, self.response]) as post:
            self.assertEqual(app.fetch_quota(self.payload), self.response)
        self.assertEqual(post.call_args.args[2]["Authorization"], "Bearer new")
        self.assertEqual(self.payload, original)

    def test_unauthorized_refreshes_and_retries_once(self):
        unauthorized = HTTPError(app.QUOTA_URL, 401, "secret response", {}, None)
        with patch.object(app, "post_json", side_effect=[unauthorized, {"access_token": "new"}, self.response]) as post:
            self.assertEqual(app.fetch_quota(self.payload), self.response)
            self.assertEqual(post.call_count, 3)
        with patch.object(app, "post_json", side_effect=[unauthorized, {"access_token": "new"}, unauthorized]) as post:
            self.assertIn("401", app.fetch_quota(self.payload)["error"])
            self.assertEqual(post.call_count, 3)

    def test_errors_are_safe_and_missing_quota_is_not_zero(self):
        for error in [URLError("secret"), TimeoutError("secret"),
                      HTTPError(app.QUOTA_URL, 403, "secret", {}, None), ValueError("secret")]:
            with patch.object(app, "post_json", side_effect=error):
                result = app.fetch_quota(self.payload)
            self.assertIn("error", result)
            self.assertNotIn("secret", str(result))
        with patch.object(app, "post_json", return_value={}):
            self.assertEqual(app.fetch_quota(self.payload), {"groups": []})
        self.assertIn("error", app.fetch_quota(None))
        with patch.object(app, "post_json", return_value={"groups": [{"buckets": [None]}]}):
            self.assertIn("error", app.fetch_quota(self.payload))

    def test_list_uses_live_credentials_and_isolates_broken_profiles(self):
        meta = {"active": {"email": "live@test"}, "broken": {"email": "bad@test"}}
        output = io.StringIO()
        with patch.object(app, "get_current_keyring_token", return_value=self.payload), \
             patch.object(app, "get_token_summary", return_value={"email": "live@test"}), \
             patch.object(app, "load_meta", return_value=meta), \
             patch.object(app, "get_profile_payload", side_effect=ValueError("broken")), \
             patch.object(app, "post_json", return_value=self.response), \
             contextlib.redirect_stdout(output):
            app.cmd_list(argparse.Namespace(no_quota=False))
        self.assertIn("40.3%", output.getvalue())
        self.assertIn("未找到有效的账号凭证", output.getvalue())
        self.assertNotIn("Token", output.getvalue())
        self.assertNotIn("保存时间", output.getvalue())

    def test_offline_list_never_fetches(self):
        with patch.object(app, "get_current_keyring_token", return_value=None), \
             patch.object(app, "load_meta", return_value={"a": {"email": "a@test"}}), \
             patch.object(app, "get_profile_payload", return_value=self.payload), \
             patch.object(app, "fetch_quota") as fetch, contextlib.redirect_stdout(io.StringIO()):
            app.cmd_list(argparse.Namespace(no_quota=True))
        fetch.assert_not_called()

    def test_timestamp_accepts_go_nanoseconds_and_invalid_values(self):
        self.assertIsNotNone(app.parse_time("2026-09-20T01:00:38.691575783+08:00"))
        self.assertEqual(app.format_reset("bad"), "重置时间未知")
        self.assertIn("已到期", app.format_reset("2000-01-01T00:00:00Z"))


if __name__ == "__main__":
    unittest.main()
