"""Local adapter for WSL agy installations that use file credentials.

Credentials are owner-only files, not encrypted keyring entries. This backend
is enabled only by the local launchers; upstream agy_switch.py stays unchanged.
"""

import hashlib
import os
from pathlib import Path
import tempfile

import keyring
from keyring.backend import KeyringBackend
from keyring.errors import PasswordDeleteError


class AgyFileBackend(KeyringBackend):
    priority = 1

    def _path(self, service, username):
        if service == "gemini" and username == "antigravity":
            return Path.home() / ".gemini/antigravity-cli/antigravity-oauth-token"
        if service == "gemini-accounts":
            digest = hashlib.sha256(username.encode("utf-8")).hexdigest()
            return Path.home() / ".gemini/agy-switch/credentials" / (digest + ".json")
        raise ValueError("Unsupported credential service")

    def get_password(self, service, username):
        path = self._path(service, username)
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None

    def set_password(self, service, username, password):
        path = self._path(service, username)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, temp = tempfile.mkstemp(prefix=".credential-", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(password)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)

    def delete_password(self, service, username):
        try:
            self._path(service, username).unlink()
        except FileNotFoundError as exc:
            raise PasswordDeleteError("Credential does not exist") from exc


def main():
    keyring.set_keyring(AgyFileBackend())
    from agy_switch import main as upstream_main
    upstream_main()


if __name__ == "__main__":
    main()
