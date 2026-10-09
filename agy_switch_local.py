"""Local adapter that bridges agy-switch's credential storage with however the
real ``agy`` binary persists its OAuth token.

On native Linux with D-Bus, agy uses the SecretService system keyring
(go-keyring).  On WSL or headless systems without SecretService, agy falls back
to a plain file at ``~/.gemini/antigravity-cli/antigravity-oauth-token``.

This backend auto-detects which storage agy actually uses for the *active*
credential (service="gemini", username="antigravity") and delegates there.
Profile credentials (service="gemini-accounts") are always stored as local
owner-only files managed by agy-switch itself.
"""

import hashlib
import os
from pathlib import Path
import tempfile

import keyring
from keyring.backend import KeyringBackend
from keyring.errors import PasswordDeleteError

_ACTIVE_TOKEN_FILE = Path.home() / ".gemini/antigravity-cli/antigravity-oauth-token"


def _system_keyring():
    """Return SecretService backend if D-Bus is available, else None."""
    if not os.environ.get("DBUS_SESSION_BUS_ADDRESS"):
        return None
    try:
        from keyring.backends.SecretService import Keyring as SSKeyring
        ss = SSKeyring()
        # Probe that the backend is actually usable (D-Bus connected, etc.)
        ss.get_password("__probe__", "__probe__")
        return ss
    except Exception:
        return None


# Cache the result; the system keyring won't change mid-run.
_cached_system_keyring = None
_system_keyring_probed = False


def _get_system_keyring():
    global _cached_system_keyring, _system_keyring_probed
    if not _system_keyring_probed:
        _cached_system_keyring = _system_keyring()
        _system_keyring_probed = True
    return _cached_system_keyring


class AgyFileBackend(KeyringBackend):
    priority = 1

    # ---- active credential helpers ----

    def _active_get(self):
        """Read agy's active token from whichever store it uses."""
        ss = _get_system_keyring()
        if ss is not None:
            val = ss.get_password("gemini", "antigravity")
            if val is not None:
                return val
        # Fall back to file (WSL / headless, or system keyring empty).
        try:
            return _ACTIVE_TOKEN_FILE.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None

    def _active_set(self, password):
        """Write agy's active token to whichever store it uses."""
        ss = _get_system_keyring()
        if ss is not None:
            try:
                ss.set_password("gemini", "antigravity", password)
            except Exception:
                pass
        # File fallback and synchronization.
        _ACTIVE_TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, temp = tempfile.mkstemp(prefix=".credential-", dir=_ACTIVE_TOKEN_FILE.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(password)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, _ACTIVE_TOKEN_FILE)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)

    def _active_delete(self):
        """Remove agy's active token from whichever store it uses."""
        deleted = False
        ss = _get_system_keyring()
        if ss is not None:
            try:
                ss.delete_password("gemini", "antigravity")
                deleted = True
            except Exception:
                pass
        # Also remove the file if it exists (belt and suspenders).
        try:
            _ACTIVE_TOKEN_FILE.unlink()
            deleted = True
        except FileNotFoundError:
            pass
        if not deleted:
            raise PasswordDeleteError("Credential does not exist")

    # ---- profile credential helpers ----

    def _profile_path(self, username):
        digest = hashlib.sha256(username.encode("utf-8")).hexdigest()
        return Path.home() / ".gemini/agy-switch/credentials" / (digest + ".json")

    # ---- keyring interface ----

    def get_password(self, service, username):
        if service == "gemini" and username == "antigravity":
            return self._active_get()
        if service == "gemini-accounts":
            try:
                return self._profile_path(username).read_text(encoding="utf-8")
            except FileNotFoundError:
                return None
        raise ValueError("Unsupported credential service")

    def set_password(self, service, username, password):
        if service == "gemini" and username == "antigravity":
            self._active_set(password)
            return
        if service == "gemini-accounts":
            path = self._profile_path(username)
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
            return
        raise ValueError("Unsupported credential service")

    def delete_password(self, service, username):
        if service == "gemini" and username == "antigravity":
            self._active_delete()
            return
        if service == "gemini-accounts":
            try:
                self._profile_path(username).unlink()
            except FileNotFoundError as exc:
                raise PasswordDeleteError("Credential does not exist") from exc
            return
        raise ValueError("Unsupported credential service")


def main():
    keyring.set_keyring(AgyFileBackend())
    import agy_switch
    agy_switch.LOCAL_FILE_BACKEND = True
    agy_switch.main()


if __name__ == "__main__":
    main()
