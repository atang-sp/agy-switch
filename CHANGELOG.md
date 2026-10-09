# Changelog

## v0.3.0 - 2026-10-09

- **Adaptive Keyring Backend**: Auto-detect Linux D-Bus session and bridge SecretService keyring with owner-only local file storage. Transparent fallback on headless or legacy WSL environments.
- **Robust OAuth Email Resolution**: Automatically fetch user email via Google OAuth tokeninfo API when `id_token` is missing in newer `agy` (v1.1.27+) credential payloads, fixing "unknown email" errors.
- **Environment Doctor (`agy-switch doctor`)**: Added a comprehensive diagnostic subcommand to check OS, WSL detection, D-Bus session, keyring backend, active account, and running `agy` processes.
- **Unified Entry Point**: Integrated local adapter into core `agy_switch.py`, simplifying installation and making CLI launchers work out-of-the-box across Linux, WSL2, macOS, and Windows.
- **Documentation**: Added post-mortem incident report and lessons learned (`LESSONS_LEARNED.md`).

## v0.2.0 - 2026-09-27

- Bind saved accounts to Git projects, with isolated CLI credentials so projects can use different accounts at the same time on the WSL file credential setup.
- Show each account's bound projects and running `agy` sessions alongside its quota in `agy-switch list`.
- Show separate Gemini and Claude/GPT-OSS quota windows and reset times for each saved account.
- Improve account aliases and new account setup, and prevent global credential switches while an `agy` session could overwrite them.
- Fix Python package contents and add tests for account, quota, and project behavior.

Project isolation applies to the WSL file credential adapter and the `agy` CLI. Restart existing `agy` sessions to use a newly selected project account.
