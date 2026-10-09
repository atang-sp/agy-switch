"""Backward-compatibility adapter.

All adaptive environment detection and credential storage logic is now
integrated directly into ``agy_switch.py``.
"""

from agy_switch import AdaptiveKeyring, main

AgyFileBackend = AdaptiveKeyring

if __name__ == "__main__":
    main()
